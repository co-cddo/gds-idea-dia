"""Tests for dia.embeddings.batch_semantic_splitter."""

import hashlib
import logging

import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
from llama_index.core.schema import Document, NodeRelationship

from dia.embeddings import batch_semantic_splitter as splitter_module
from dia.embeddings.batch_semantic_splitter import batch_semantic_split
from dia.embeddings.bedrock_batch_client import BatchEmbeddingResult

MODEL_ID = "amazon.titan-embed-text-v2:0"
ROLE_ARN = "arn:aws:iam::123456789012:role/batch-embedding-role"
BUCKET = "test-bucket"


def _vec(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [b / 255 for b in digest[:16]]


class _FakeEmbedding(BaseEmbedding):
    """Deterministic, offline stand-in for a real embedding model - both
    sync and async, so it works for the fallback path (async) and as the
    embed_model handed to the internal SemanticSplitterNodeParser (whose
    .similarity() calls are synchronous local numpy either way)."""

    _sync_calls: int = PrivateAttr(default=0)
    _async_calls: int = PrivateAttr(default=0)

    def _get_query_embedding(self, query):
        self._sync_calls += 1
        return _vec(query)

    def _get_text_embedding(self, text):
        self._sync_calls += 1
        return _vec(text)

    async def _aget_query_embedding(self, query):
        self._async_calls += 1
        return _vec(query)

    async def _aget_text_embedding(self, text):
        self._async_calls += 1
        return _vec(text)


def _fake_submit_and_await(requests, **kwargs):
    """Stands in for submit_and_await_batch_embeddings - already tested in
    isolation (test_embeddings_bedrock_batch_client.py). Uses the same
    deterministic _vec() as _FakeEmbedding so cross-path output comparisons
    are meaningful."""
    return [BatchEmbeddingResult(token=r.token, embedding=_vec(r.text)) for r in requests]


_MANY_SENTENCES_TEXT = "".join(f"Sentence number {i} discusses a slightly different point. " for i in range(150))
_FEW_SENTENCES_TEXT = "First sentence here. Second sentence follows. Third sentence concludes."


@pytest.mark.asyncio
async def test_batch_path_matches_stock_splitter_output(monkeypatch):
    """The core correctness claim: given the same embeddings, the batch
    decomposition must produce byte-identical output to calling
    SemanticSplitterNodeParser directly - this is the same guarantee
    verified manually earlier this session, now pinned as a regression
    test."""
    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _fake_submit_and_await)

    doc = Document(doc_id="files/report.pdf", text=_MANY_SENTENCES_TEXT, metadata={"key": "files/report.pdf"})
    embed_model = _FakeEmbedding()

    stock_splitter = SemanticSplitterNodeParser(
        embed_model=embed_model, buffer_size=1, breakpoint_percentile_threshold=95
    )
    expected_nodes = stock_splitter.build_semantic_nodes_from_documents([doc])

    actual_nodes = await batch_semantic_split(
        [doc],
        embed_model=embed_model,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
        buffer_size=1,
        breakpoint_percentile_threshold=95,
    )

    assert [n.text for n in actual_nodes] == [n.text for n in expected_nodes]
    assert len(actual_nodes) > 1  # sanity: real breakpoints were found, not one giant chunk


@pytest.mark.asyncio
async def test_batch_path_preserves_source_relationship(monkeypatch):
    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _fake_submit_and_await)
    doc = Document(doc_id="files/report.pdf", text=_MANY_SENTENCES_TEXT, metadata={"key": "files/report.pdf"})

    nodes = await batch_semantic_split(
        [doc],
        embed_model=_FakeEmbedding(),
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
    )

    for node in nodes:
        assert node.relationships[NodeRelationship.SOURCE].node_id == "files/report.pdf"


@pytest.mark.asyncio
async def test_multiple_documents_each_chunked_independently(monkeypatch):
    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _fake_submit_and_await)
    docs = [
        Document(doc_id=f"doc-{i}.pdf", text=_MANY_SENTENCES_TEXT, metadata={"key": f"doc-{i}.pdf"}) for i in range(3)
    ]

    nodes = await batch_semantic_split(
        docs,
        embed_model=_FakeEmbedding(),
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
    )

    represented = {n.relationships[NodeRelationship.SOURCE].node_id for n in nodes}
    assert represented == {"doc-0.pdf", "doc-1.pdf", "doc-2.pdf"}


@pytest.mark.asyncio
async def test_empty_document_produces_no_chunks(monkeypatch):
    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _fake_submit_and_await)
    empty_doc = Document(doc_id="empty.pdf", text="", metadata={"key": "empty.pdf"})
    real_doc = Document(doc_id="real.pdf", text=_MANY_SENTENCES_TEXT, metadata={"key": "real.pdf"})

    nodes = await batch_semantic_split(
        [empty_doc, real_doc],
        embed_model=_FakeEmbedding(),
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
    )

    assert all(n.relationships[NodeRelationship.SOURCE].node_id == "real.pdf" for n in nodes)


@pytest.mark.asyncio
async def test_no_documents_returns_empty_list():
    nodes = await batch_semantic_split(
        [],
        embed_model=_FakeEmbedding(),
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
    )
    assert nodes == []


@pytest.mark.asyncio
async def test_batch_failure_raises_runtime_error(monkeypatch):
    def _failing_submit(requests, **kwargs):
        results = [BatchEmbeddingResult(token=r.token, embedding=_vec(r.text)) for r in requests]
        results[0] = BatchEmbeddingResult(token=results[0].token, embedding=None, error="boom")
        return results

    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _failing_submit)
    doc = Document(doc_id="files/report.pdf", text=_MANY_SENTENCES_TEXT, metadata={"key": "files/report.pdf"})

    with pytest.raises(RuntimeError, match="boom"):
        await batch_semantic_split(
            [doc],
            embed_model=_FakeEmbedding(),
            model_id=MODEL_ID,
            role_arn=ROLE_ARN,
            bucket=BUCKET,
            key_prefix="test",
        )


# --- sub-minimum fallback ---


@pytest.mark.asyncio
async def test_below_minimum_falls_back_to_on_demand(monkeypatch, caplog):
    """A document with only a handful of sentences never reaches Bedrock's
    100-record batch minimum - must use embed_model directly, and must
    log loudly that it's doing so."""

    def _exploding_submit(requests, **kwargs):
        raise AssertionError("submit_and_await_batch_embeddings should not be called below the batch minimum")

    monkeypatch.setattr(splitter_module, "submit_and_await_batch_embeddings", _exploding_submit)

    doc = Document(doc_id="files/short.pdf", text=_FEW_SENTENCES_TEXT, metadata={"key": "files/short.pdf"})
    embed_model = _FakeEmbedding()

    with caplog.at_level(logging.WARNING):
        nodes = await batch_semantic_split(
            [doc],
            embed_model=embed_model,
            model_id=MODEL_ID,
            role_arn=ROLE_ARN,
            bucket=BUCKET,
            key_prefix="test",
        )

    assert len(nodes) >= 1
    assert embed_model._async_calls > 0
    assert any("Falling back to on-demand embedding" in record.message for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.asyncio
async def test_fallback_path_matches_stock_splitter_output():
    """Same correctness guarantee as the batch path, for the fallback."""
    doc = Document(doc_id="files/short.pdf", text=_FEW_SENTENCES_TEXT, metadata={"key": "files/short.pdf"})
    embed_model = _FakeEmbedding()

    stock_splitter = SemanticSplitterNodeParser(
        embed_model=embed_model, buffer_size=1, breakpoint_percentile_threshold=95
    )
    expected_nodes = stock_splitter.build_semantic_nodes_from_documents([doc])

    actual_nodes = await batch_semantic_split(
        [doc],
        embed_model=embed_model,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test",
        buffer_size=1,
        breakpoint_percentile_threshold=95,
    )

    assert [n.text for n in actual_nodes] == [n.text for n in expected_nodes]
