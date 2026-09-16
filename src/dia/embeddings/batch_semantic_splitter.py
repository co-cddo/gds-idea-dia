"""Batched semantic splitting: decomposes SemanticSplitterNodeParser's
embed-then-cut logic into record -> batch-embed -> replay, using Bedrock
batch inference for the embedding step (measured this session as ~97% of
total chunking time) instead of one call per sentence window.

Verified this session that this decomposition produces byte-identical
output to calling SemanticSplitterNodeParser.build_semantic_nodes_from_documents
directly, given the same embeddings - the three private methods used here
(_build_sentence_groups, _calculate_distances_between_sentence_groups,
_build_node_chunks) are exactly what that method calls internally; this
module only replaces *how* the embeddings for each sentence window are
obtained, not any of the grouping/distance/cut logic.

Below Bedrock's batch minimum (BEDROCK_MIN_BATCH_SIZE, 100 records), falls
back to on-demand embedding via `embed_model` directly - loudly (a WARNING
log), since it's a real behaviour change (slower) the caller should be
able to notice, not a silent degradation.
"""

import asyncio
import logging
from collections.abc import Sequence

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser.node_utils import build_nodes_from_splits
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
from llama_index.core.schema import BaseNode, TextNode

from dia.embeddings.bedrock_batch_client import (
    BEDROCK_MIN_BATCH_SIZE,
    DEFAULT_MAX_BYTES_PER_JOB,
    DEFAULT_MAX_RECORDS_PER_JOB,
    BatchEmbeddingRequest,
    submit_and_await_batch_embeddings,
)

logger = logging.getLogger(__name__)


def _token(doc_index: int, window_index: int) -> str:
    return f"{doc_index}:{window_index}"


async def batch_semantic_split(
    documents: Sequence[BaseNode],
    *,
    embed_model: BaseEmbedding,
    model_id: str,
    role_arn: str,
    bucket: str,
    key_prefix: str,
    buffer_size: int = 1,
    breakpoint_percentile_threshold: int = 95,
    bedrock_client=None,
    s3_client=None,
    max_records_per_job: int = DEFAULT_MAX_RECORDS_PER_JOB,
    max_bytes_per_job: int = DEFAULT_MAX_BYTES_PER_JOB,
    poll_interval_seconds: float = 30.0,
) -> list[TextNode]:
    """Semantically split `documents` (already sentence-split, i.e. the
    stage-1 SentenceSplitter's output - not raw source text) into TextNode
    chunks, embedding sentence windows via Bedrock batch inference rather
    than one on-demand call per window.

    `embed_model` is used for two things: computing cosine similarity
    between sentence-group embeddings once they've been obtained (pure
    local numpy, via BaseEmbedding.similarity - not a network call), and
    as the on-demand fallback if the total window count falls under
    Bedrock's batch minimum. A PooledBedrockEmbedding instance is a
    reasonable choice - reused for both purposes, no separate embed model
    needed for the fallback path.

    Raises:
        RuntimeError: any sentence window failed to embed. Not tolerated
            as a partial result - a missing embedding for even one window
            corrupts the distance calculation for its whole containing
            document, so this fails loudly rather than silently degrading
            chunk quality for that document.
    """
    splitter = SemanticSplitterNodeParser(
        embed_model=embed_model,
        buffer_size=buffer_size,
        breakpoint_percentile_threshold=breakpoint_percentile_threshold,
    )

    # Build every document's sentence-group windows locally - no
    # embedding calls yet, this is the same cheap local step measured at
    # 6.6s/20 docs this session.
    per_document_sentences: list[list[dict]] = [
        splitter._build_sentence_groups(splitter.sentence_splitter(doc.text)) for doc in documents
    ]

    requests = [
        BatchEmbeddingRequest(token=_token(doc_index, window_index), text=sentence["combined_sentence"])
        for doc_index, sentences in enumerate(per_document_sentences)
        for window_index, sentence in enumerate(sentences)
    ]

    if not requests:
        return []

    if len(requests) < BEDROCK_MIN_BATCH_SIZE:
        logger.warning(
            "Falling back to on-demand embedding for %d sentence windows "
            "(below Bedrock's %d-record batch minimum) - this will be "
            "noticeably slower than the batch path. Consider combining "
            "with other documents if this recurs often.",
            len(requests),
            BEDROCK_MIN_BATCH_SIZE,
        )
        embeddings = await embed_model.aget_text_embedding_batch([r.text for r in requests])
        token_to_embedding = {r.token: embedding for r, embedding in zip(requests, embeddings, strict=True)}
    else:
        results = await asyncio.to_thread(
            submit_and_await_batch_embeddings,
            requests,
            model_id=model_id,
            role_arn=role_arn,
            bucket=bucket,
            key_prefix=key_prefix,
            bedrock_client=bedrock_client,
            s3_client=s3_client,
            max_records_per_job=max_records_per_job,
            max_bytes_per_job=max_bytes_per_job,
            poll_interval_seconds=poll_interval_seconds,
        )
        failed = [r for r in results if r.embedding is None]
        if failed:
            raise RuntimeError(
                f"{len(failed)} of {len(results)} sentence windows failed to embed "
                f"via Bedrock batch inference - first error: {failed[0].error}"
            )
        token_to_embedding = {r.token: r.embedding for r in results}

    all_nodes: list[TextNode] = []
    for doc_index, (doc, sentences) in enumerate(zip(documents, per_document_sentences, strict=True)):
        if not sentences:
            continue

        for window_index, sentence in enumerate(sentences):
            sentence["combined_sentence_embedding"] = token_to_embedding[_token(doc_index, window_index)]

        distances = splitter._calculate_distances_between_sentence_groups(sentences)
        chunks = splitter._build_node_chunks(sentences, distances)
        all_nodes.extend(build_nodes_from_splits(chunks, doc, id_func=splitter.id_func))

    return all_nodes
