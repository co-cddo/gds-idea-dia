"""Tests for dia.pipeline.chunking — Stage 2a: chunking Stage 1 output."""

import hashlib

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
from llama_index.core.schema import NodeRelationship

from dia.config import ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.pipeline.chunk_store import InMemoryChunkStore
from dia.pipeline.chunking import ChunkingRunner, _build_chunking_pipeline
from dia.pipeline.models import TextExtractionOutput


class _FakeEmbedding(BaseEmbedding):
    """Deterministic, offline stand-in for BedrockEmbedding.

    Module-level (not nested/local) so it survives pickling into
    multiprocessing worker processes — a lambda or a class defined inside a
    test function can't be pickled for the 'spawn' start method.
    """

    def _get_query_embedding(self, query):
        return self._vec(query)

    def _get_text_embedding(self, text):
        return self._vec(text)

    async def _aget_query_embedding(self, query):
        return self._vec(query)

    async def _aget_text_embedding(self, text):
        return self._vec(text)

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
    "The first sentence sets the scene. The second sentence follows on. "
    "The third sentence continues the thought. "
) * 6

_MANY_SENTENCES_TEXT = "".join(f"Sentence number {i} discusses a slightly different point. " for i in range(150))


def _extraction_config(monkeypatch, **overrides) -> ExtractionConfig:
    """ExtractionConfig wired to return _FakeEmbedding instead of a real
    BedrockEmbedding, so tests never touch AWS."""
    monkeypatch.setattr(ExtractionConfig, "to_embedding_model", lambda self: _FakeEmbedding())
    return ExtractionConfig(**overrides)


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
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore()

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total_documents == 1
    assert result.total_chunks > 0
    assert result.skipped is False
    assert chunk_store.exists("test-source") is True
    assert len(chunk_store.read("test-source")) == result.total_chunks


def test_runner_preserves_source_relationship(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    output_source = _FakeOutputSource([_output("files/report.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore()

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
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    chunk_store = InMemoryChunkStore()

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource([]),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total_documents == 0
    assert result.total_chunks == 0
    assert result.skipped is False
    assert chunk_store.exists("test-source") is False


def test_runner_skips_if_chunks_already_exist(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore()

    first = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    first_result = first.run()

    # Second run: same output source, but the *result* of calling it must not
    # matter, since a skip must not even list_outputs — swap in an output
    # source that would fail if touched.
    class _ExplodingOutputSource:
        def list_outputs(self, source_name):
            raise AssertionError("list_outputs should not be called when skipping")

    second = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_ExplodingOutputSource(),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    second_result = second.run()

    assert second_result.skipped is True
    assert second_result.total_documents == 0
    assert second_result.total_chunks == first_result.total_chunks


def test_runner_force_rechunks_even_if_chunks_exist(monkeypatch, tmp_path):
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _LONG_TEXT)])
    chunk_store = InMemoryChunkStore()

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

    assert second_result.skipped is False
    assert second_result.total_documents == 1


def test_runner_without_semantic_splitting_produces_fewer_larger_chunks(monkeypatch, tmp_path):
    """CONTRACT_FINDER disables semantic splitting - sentence splitting alone
    should produce fewer, larger chunks than BUSINESS_CASE's two-stage split
    for the same input text (enough sentences for the semantic splitter's
    97th-percentile breakpoint threshold to reliably fire more than once)."""
    config = _extraction_config(monkeypatch, chunking_num_workers=1)
    output_source = _FakeOutputSource([_output("doc-1.pdf", _MANY_SENTENCES_TEXT)])

    semantic_store = InMemoryChunkStore()
    ChunkingRunner(
        source_name="s",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        chunk_store=semantic_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    ).run()

    sentence_only_store = InMemoryChunkStore()
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


def test_runner_uses_multiple_workers(monkeypatch, tmp_path):
    """Real multiprocessing (spawn), not mocked - proves the embedding model
    and parsers survive being pickled to worker processes and chunks come
    back correctly attributed to their source document."""
    config = _extraction_config(monkeypatch, chunking_num_workers=3)
    outputs = [_output(f"doc-{i}.pdf", _LONG_TEXT) for i in range(6)]
    chunk_store = InMemoryChunkStore()

    runner = ChunkingRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=_FakeOutputSource(outputs),
        chunk_store=chunk_store,
        extraction_config=config,
        log_dir=str(tmp_path),
    )
    result = runner.run()

    assert result.total_documents == 6
    nodes = chunk_store.read("test-source")
    assert len(nodes) == result.total_chunks
    represented_keys = {n.relationships[NodeRelationship.SOURCE].node_id for n in nodes}
    assert represented_keys == {f"doc-{i}.pdf" for i in range(6)}
