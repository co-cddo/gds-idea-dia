"""Tests for dia.pipeline.chunking — Stage 2a: chunking Stage 1 output."""

import hashlib

import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
from llama_index.core.schema import NodeRelationship

from dia.config import BatchConfig, ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.embeddings import batch_semantic_splitter as batch_splitter_module
from dia.embeddings.bedrock_batch_client import BatchEmbeddingResult
from dia.pipeline import chunking as chunking_module
from dia.pipeline.chunk_store import InMemoryChunkStore
from dia.pipeline.chunking import ChunkingRunner, _build_chunking_pipeline
from dia.pipeline.models import TextExtractionOutput

FINGERPRINT = "test-fingerprint"


class _FakeEmbedding(BaseEmbedding):
    """Deterministic, offline stand-in for BedrockEmbedding.

    Implements both sync and async methods so tests can assert on which
    path IngestionPipeline.arun() actually exercises.
    """

    _sync_calls: int = PrivateAttr(default=0)
    _async_calls: int = PrivateAttr(default=0)

    def _get_query_embedding(self, query):
        self._sync_calls += 1
        return self._vec(query)

    def _get_text_embedding(self, text):
        self._sync_calls += 1
        return self._vec(text)

    async def _aget_query_embedding(self, query):
        self._async_calls += 1
        return self._vec(query)

    async def _aget_text_embedding(self, text):
        self._async_calls += 1
        return self._vec(text)

    async def aclose(self) -> None:
        """No-op - real PooledBedrockEmbedding holds a connection to
        release; this fake holds nothing. Present so it can stand in for
        to_pooled_embedding_model() too (_chunk_via_batch always calls
        aclose() on whatever it gets back)."""

    @staticmethod
    def _vec(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255 for b in digest[:8]]


class _FakeOutputSource:
    """Returns a fixed list of TextExtractionOutput, ignoring source_name."""

    def __init__(self, outputs: list[TextExtractionOutput]) -> None:
        self._outputs = outputs

    def list_outputs(self, source_name: str) -> list[TextExtractionOutput]:
        return self._outputs


def _output(key: str, text: str, **overrides) -> TextExtractionOutput:
    defaults = dict(
        key=key,
        source_name="test-source",
        content_type="application/pdf",
        version="v1",
        text=text,
        chars=len(text),
        metadata={"department": "Home Office"},
        extracted_at="2026-01-01T00:00:00+00:00",
        code_version="0.1.0",
    )
    defaults.update(overrides)
    return TextExtractionOutput(**defaults)


_LONG_TEXT = (
    "The first sentence sets the scene. The second sentence follows on. The third sentence continues the thought. "
) * 6

_MANY_SENTENCES_TEXT = "".join(f"Sentence number {i} discusses a slightly different point. " for i in range(150))


def _extraction_config(monkeypatch, embedding: "_FakeEmbedding | None" = None, **overrides) -> ExtractionConfig:
    """ExtractionConfig wired to return _FakeEmbedding instead of a real
    BedrockEmbedding, so tests never touch AWS.

    Pass an explicit `embedding` instance to inspect its call counts after
    a run - to_embedding_model() always returns that same instance rather
    than constructing a fresh one each call.
    """
    embedding = embedding or _FakeEmbedding()
    monkeypatch.setattr(ExtractionConfig, "to_embedding_model", lambda self: embedding)
    monkeypatch.setattr(ExtractionConfig, "to_pooled_embedding_model", lambda self: embedding)
    return ExtractionConfig(**overrides)


def _batch_config(**overrides) -> BatchConfig:
    defaults = dict(role_arn="arn:aws:iam::123456789012:role/batch-role", bucket="test-batch-bucket")
    defaults.update(overrides)
    return BatchConfig(**defaults)


def _low_batch_threshold(monkeypatch, document_type: DocumentType, threshold: int = 2) -> None:
    """Patch DocumentType.chunking so a test can exercise the batch path
    with a handful of documents instead of needing semantic_batch_
    threshold_documents' real default (100) worth of fixtures."""
    patched = document_type.chunking.model_copy(update={"semantic_batch_threshold_documents": threshold})
    monkeypatch.setattr(DocumentType, "chunking", property(lambda self: patched))


def _fake_submit_and_await(requests, **kwargs):
    """Stands in for submit_and_await_batch_embeddings - already tested in
    isolation (test_embeddings_bedrock_batch_client.py). Uses the same
    deterministic _vec() as _FakeEmbedding so cross-path output
    comparisons (batch vs on-demand) are meaningful."""
    return [BatchEmbeddingResult(token=r.token, embedding=_FakeEmbedding._vec(r.text)) for r in requests]


# --- _build_chunking_pipeline ---


def test_build_pipeline_with_semantic_splitting(monkeypatch):
    config = _extraction_config(monkeypatch)
    chunking = ChunkingConfig(use_semantic_splitting=True)

    parsers = _build_chunking_pipeline(chunking, config)

    assert len(parsers) == 2
    assert isinstance(parsers[0], SentenceSplitter)
    assert isinstance(parsers[1], SemanticSplitterNodeParser)


def test_build_pipeline_without_semantic_splitting(monkeypatch):
    config = _extraction_config(monkeypatch)
    chunking = ChunkingConfig(use_semantic_splitting=False)

    parsers = _build_chunking_pipeline(chunking, config)

    assert len(parsers) == 1
    assert isinstance(parsers[0], SentenceSplitter)


def test_build_pipeline_uses_chunking_config_values(monkeypatch):
    config = _extraction_config(monkeypatch)
    chunking = ChunkingConfig(
        sentence_chunk_size_tokens=500,
        sentence_chunk_overlap_tokens=10,
        semantic_buffer_size=2,
        semantic_breakpoint_threshold=90,
    )

    parsers = _build_chunking_pipeline(chunking, config)

    sentence_splitter = parsers[0]
    assert sentence_splitter.chunk_size == 500
    assert sentence_splitter.chunk_overlap == 10

    semantic_splitter = parsers[1]
    assert semantic_splitter.buffer_size == 2
    assert semantic_splitter.breakpoint_percentile_threshold == 90


# --- ChunkingRunner ---


def test_runner_produces_chunks(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 1
    assert result.processed == 1
    assert result.skipped == 0
    assert result.total_chunks > 0
    assert len(chunk_store.read("test-source")) == result.total_chunks
    assert chunk_store.present("test-source") == {("doc-1.pdf", "v1")}


def test_runner_preserves_source_relationship(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch)
    output_source = _FakeOutputSource([_output("files/report.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    runner.run()

    nodes = chunk_store.read("test-source")
    assert len(nodes) > 0
    for node in nodes:
        source = node.relationships[NodeRelationship.SOURCE]
        assert source.node_id == "files/report.pdf"
        assert node.metadata["key"] == "files/report.pdf"
        assert node.metadata["department"] == "Home Office"


def test_runner_no_outputs_is_a_noop(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch)
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 0
    assert result.processed == 0
    assert result.skipped == 0
    assert result.total_chunks == 0
    assert chunk_store.present("test-source") == set()


def test_runner_skips_unchanged_documents(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    first = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    first_result = first.run()

    # Second run: same output source, but the embedding model must not be
    # touched again for this document - swap in a poisoned embedding model
    # that fails if called, so any re-chunking is caught immediately.
    def _exploding_embedding_model(self):
        raise AssertionError("to_embedding_model should not be called - nothing to chunk")

    monkeypatch.setattr(ExtractionConfig, "to_embedding_model", _exploding_embedding_model)

    second = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    second_result = second.run()

    assert second_result.total == 1
    assert second_result.processed == 0
    assert second_result.skipped == 1
    assert second_result.total_chunks == 0
    assert len(chunk_store.read("test-source")) == first_result.total_chunks


def test_runner_chunks_only_new_document_alongside_unchanged_one(monkeypatch, tmp_path):
    """Adding a new document to a source must not force re-chunking
    documents that haven't changed - this is the whole point of
    per-document (rather than per-source) tracking in the ChunkStore."""
    config = _extraction_config(monkeypatch)
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    first = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    first.run()
    chunks_after_first = chunk_store.read("test-source")

    second = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT), _output("doc-2.pdf", _LONG_TEXT)]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    second_result = second.run()

    assert second_result.total == 2
    assert second_result.processed == 1  # only doc-2.pdf
    assert second_result.skipped == 1  # doc-1.pdf untouched
    assert chunk_store.present("test-source") == {("doc-1.pdf", "v1"), ("doc-2.pdf", "v1")}

    # doc-1.pdf's chunks are byte-identical to before - never re-chunked.
    doc_1_chunks_before = [n for n in chunks_after_first if n.metadata["key"] == "doc-1.pdf"]
    doc_1_chunks_after = [n for n in chunk_store.read("test-source") if n.metadata["key"] == "doc-1.pdf"]
    assert {n.node_id for n in doc_1_chunks_before} == {n.node_id for n in doc_1_chunks_after}


def test_runner_rechunks_modified_document(monkeypatch, tmp_path):
    """A document whose version changed (e.g. a new S3 ETag after a
    re-upload) must be re-chunked, even without force=True."""
    config = _extraction_config(monkeypatch)
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    first = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT, version="v1")]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    first.run()

    second = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT, version="v2")]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    second_result = second.run()

    assert second_result.processed == 1
    assert second_result.skipped == 0
    assert chunk_store.present("test-source") == {("doc-1.pdf", "v2")}


def test_runner_force_rechunks_even_if_unchanged(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    first = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
        force=True,
    )
    first.run()

    second = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
        force=True,
    )
    second_result = second.run()

    assert second_result.processed == 1
    assert second_result.skipped == 0


def test_runner_without_semantic_splitting_produces_fewer_larger_chunks(monkeypatch, tmp_path):
    """CONTRACT_FINDER disables semantic splitting - sentence splitting alone
    should produce fewer, larger chunks than BUSINESS_CASE's two-stage split
    for the same input text (enough sentences for the semantic splitter's
    97th-percentile breakpoint threshold to reliably fire more than once)."""
    config = _extraction_config(monkeypatch)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _MANY_SENTENCES_TEXT)])

    semantic_store = InMemoryChunkStore(FINGERPRINT)
    ChunkingRunner(
        source_name="s",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=semantic_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    ).run()

    sentence_only_store = InMemoryChunkStore(FINGERPRINT)
    ChunkingRunner(
        source_name="s",
        document_type=DocumentType.CONTRACT_FINDER,
        output_source=output_source,
        chunk_store=sentence_only_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    ).run()

    semantic_chunks = semantic_store.read("s")
    sentence_only_chunks = sentence_only_store.read("s")

    assert len(sentence_only_chunks) < len(semantic_chunks)


def test_runner_uses_async_embedding_path(monkeypatch, tmp_path):
    """IngestionPipeline.arun() should exercise the embedding model's async
    methods, not the sync ones - that's the whole point of the switch away
    from multiprocessing (concurrency via asyncio.Semaphore instead of
    worker processes)."""
    embedding = _FakeEmbedding()
    config = _extraction_config(monkeypatch, embedding=embedding)
    outputs = [_output(f"doc-{i}.pdf", _LONG_TEXT) for i in range(6)]
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total == 6
    assert result.processed == 6
    nodes = chunk_store.read("test-source")
    assert len(nodes) == result.total_chunks
    represented_keys = {n.relationships[NodeRelationship.SOURCE].node_id for n in nodes}
    assert represented_keys == {f"doc-{i}.pdf" for i in range(6)}

    assert embedding._async_calls > 0
    assert embedding._sync_calls == 0


# --- Batch inference path (semantic_batch_threshold_documents) ---


def test_runner_stays_on_demand_below_batch_threshold(monkeypatch, tmp_path):
    """Below the (default: 100) document threshold, chunking must never
    touch the batch path at all - not even to check whether it could."""

    def _exploding_batch_split(*args, **kwargs):
        raise AssertionError("batch_semantic_split should not be called below the batch threshold")

    monkeypatch.setattr(chunking_module, "batch_semantic_split", _exploding_batch_split)

    config = _extraction_config(monkeypatch)
    outputs = [_output(f"doc-{i}.pdf", _LONG_TEXT) for i in range(3)]
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.processed == 3
    assert result.total_chunks > 0


def test_runner_uses_batch_path_at_or_above_threshold(monkeypatch, tmp_path):
    """At/above the threshold, chunking must use batch_semantic_split
    (via Bedrock batch inference), not the on-demand IngestionPipeline
    path - proven two ways: the low-level batch submit function is
    actually invoked, and to_embedding_model() (only used by the
    on-demand path) is never touched.

    Also the integration-level check that metadata and the SOURCE
    relationship survive the batch path end-to-end through
    ChunkingRunner - the unit-level byte-identical-to-on-demand
    guarantee for this lives in dia.embeddings' own test suite
    (test_embeddings_batch_semantic_splitter.py), since batch_semantic_
    split() handles it natively now; this just proves ChunkingRunner
    wires it through without dropping anything on the way to the
    ChunkStore."""
    _low_batch_threshold(monkeypatch, DocumentType.BUSINESS_CASE, threshold=2)

    submit_calls = []

    def _counting_submit(requests, **kwargs):
        submit_calls.append(len(requests))
        return _fake_submit_and_await(requests, **kwargs)

    monkeypatch.setattr(batch_splitter_module, "submit_and_await_batch_embeddings", _counting_submit)

    def _exploding_on_demand(self):
        raise AssertionError("to_embedding_model (on-demand path) should not be called at/above the batch threshold")

    monkeypatch.setattr(ExtractionConfig, "to_embedding_model", _exploding_on_demand)
    monkeypatch.setattr(ExtractionConfig, "to_pooled_embedding_model", lambda self: _FakeEmbedding())

    config = ExtractionConfig()
    outputs = [_output(f"doc-{i}.pdf", _MANY_SENTENCES_TEXT) for i in range(2)]
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        batch_config=_batch_config(),
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.processed == 2
    assert result.total_chunks > 0
    assert len(submit_calls) == 1  # one real batch job submitted
    assert submit_calls[0] > 100  # well above Bedrock's minimum - not the internal fallback

    nodes = chunk_store.read("test-source")
    represented_keys = {n.metadata["key"] for n in nodes}
    assert represented_keys == {"doc-0.pdf", "doc-1.pdf"}
    for node in nodes:
        assert node.metadata["department"] == "Home Office"  # _output()'s default metadata, merged in correctly
        assert node.metadata["version"] == "v1"
        assert node.relationships[NodeRelationship.SOURCE].node_id == node.metadata["key"]


def test_runner_batch_path_requires_batch_config(monkeypatch, tmp_path):
    """Crossing the threshold with no BatchConfig provided must fail
    loudly and clearly, not with some deep, confusing AttributeError from
    inside _chunk_via_batch."""
    _low_batch_threshold(monkeypatch, DocumentType.BUSINESS_CASE, threshold=2)
    config = _extraction_config(monkeypatch)
    outputs = [_output(f"doc-{i}.pdf", _MANY_SENTENCES_TEXT) for i in range(2)]
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        batch_config=None,
        log_dir=str(tmp_path),
    )

    with pytest.raises(RuntimeError, match="BatchConfig"):
        runner.run()


def test_runner_without_semantic_splitting_never_uses_batch(monkeypatch, tmp_path):
    """CONTRACT_FINDER (use_semantic_splitting=False) has no embedding
    step at all, regardless of document count - the batch/on-demand
    distinction only applies to semantic splitting's embedding calls."""

    def _exploding_batch_split(*args, **kwargs):
        raise AssertionError("batch_semantic_split should not be called - no semantic splitting configured")

    monkeypatch.setattr(chunking_module, "batch_semantic_split", _exploding_batch_split)
    _low_batch_threshold(monkeypatch, DocumentType.CONTRACT_FINDER, threshold=2)

    config = _extraction_config(monkeypatch)
    outputs = [_output(f"doc-{i}.pdf", _LONG_TEXT) for i in range(3)]
    chunk_store = InMemoryChunkStore(FINGERPRINT)

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.CONTRACT_FINDER,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.processed == 3
    assert result.total_chunks > 0
