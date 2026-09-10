"""Stage 2a: chunking — splits Stage 1 text output into TextNode chunks.

Deliberately separate from Stage 2b (graph extraction/LLM propositions and
topics) — see docs/adr/0001-lower-level-graphrag-toolkit-usage.md for why.
Chunking is embedding-heavy and slow; if extraction subsequently fails,
chunks already produced are untouched in the ChunkStore, so a retry
doesn't have to redo this stage.

Only documents not already present in the ChunkStore (per
ChunkStore.present(), keyed by document key + version) get chunked - a
newly added or modified document is chunked on its own; unchanged
documents are never re-embedded. force=True re-chunks everything
regardless.

Uses IngestionPipeline.arun(), not .run(num_workers=...). Chunking is
network-bound (Bedrock embedding calls), not CPU-bound, so async
concurrency (one process, many in-flight requests, bounded by
ExtractionConfig.embed_concurrency) is the right tool - not multiple
processes. This also sidesteps the multiprocessing 'spawn' path entirely,
which previously required credentials to be resolved once per worker
process.

In particular, no IdRewriter: it exists to give the toolkit's own
IdGenerator deterministic content-hash IDs for incremental graph updates,
which we don't use. Without it, chunk IDs are llama_index's default random
ids, and node.relationships[SOURCE].node_id still resolves correctly all
the way back to the original document's doc_id (verified directly against
real Bedrock-produced chunks and by tracing llama_index's own
NodeParser._postprocess_parsed_nodes) - and to_document() already sets
doc_id=output.key, so that relationship is a stable, meaningful value for
free.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import NodeParser, SentenceSplitter
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser
from llama_index.core.schema import BaseNode

from dia.config import ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.pipeline.chunk_store import ChunkStore
from dia.pipeline.graph_extraction_adapter import to_document
from dia.pipeline.graph_extraction_source import TextExtractionOutputSource
from dia.pipeline.logging import PIPELINE_LOGGER_NAME, setup_pipeline_logging
from dia.pipeline.models import TextExtractionOutput

logger = logging.getLogger(PIPELINE_LOGGER_NAME)


def _build_chunking_pipeline(chunking: ChunkingConfig, extraction_config: ExtractionConfig) -> list[NodeParser]:
    """ChunkingConfig -> the ordered NodeParsers documents are chunked with."""
    parsers: list[NodeParser] = [
        SentenceSplitter(
            chunk_size=chunking.sentence_chunk_size_tokens,
            chunk_overlap=chunking.sentence_chunk_overlap_tokens,
        )
    ]
    if chunking.use_semantic_splitting:
        parsers.append(
            SemanticSplitterNodeParser(
                buffer_size=chunking.semantic_buffer_size,
                breakpoint_percentile_threshold=chunking.semantic_breakpoint_threshold,
                embed_model=extraction_config.to_embedding_model(),
            )
        )
    return parsers


def _group_by_document(nodes: list[BaseNode]) -> dict[str, list[BaseNode]]:
    """Group chunks by their source document key (metadata['key'], set by
    to_document() and inherited through chunking) so they can be written to
    the ChunkStore one document at a time.

    A document that produces zero chunks (e.g. empty extracted text) has no
    entry here, so it never becomes "present" - it would be retried on
    every future run. Not handled here: real documents with actual text
    always produce at least one chunk in practice.
    """
    grouped: dict[str, list[BaseNode]] = defaultdict(list)
    for node in nodes:
        grouped[node.metadata["key"]].append(node)
    return grouped


@dataclass(frozen=True)
class ChunkingResult:
    """Result of a chunking run.

    total: total documents found in Stage 1 output for this source.
    processed: documents actually chunked this run.
    skipped: documents already present in the ChunkStore (unchanged since
        their last chunking run), so left untouched.
    total_chunks: chunks produced *this run* (not the store's total).
    """

    total: int
    processed: int
    skipped: int
    total_chunks: int
    duration_seconds: float = 0.0


class ChunkingRunner:
    """Orchestrates Stage 2a: load Stage 1 output, chunk, persist to a ChunkStore.

    Injection-friendly: all dependencies passed via constructor, matching
    TextExtractionRunner/GraphExtractionRunner's shape.
    """

    def __init__(
        self,
        source_name: str,
        document_type: DocumentType,
        output_source: TextExtractionOutputSource,
        chunk_store: ChunkStore,
        extraction_config: ExtractionConfig,
        force: bool = False,
        log_dir: str | None = None,
    ) -> None:
        self._source_name = source_name
        self._document_type = document_type
        self._output_source = output_source
        self._chunk_store = chunk_store
        self._extraction_config = extraction_config
        self._force = force
        self._log_file = setup_pipeline_logging(self._source_name, log_dir=log_dir)

    def run(self) -> ChunkingResult:
        """Sync public interface — runs the async pipeline internally."""
        return asyncio.run(self._run_async())

    def _pending_outputs(self, outputs: list[TextExtractionOutput]) -> list[TextExtractionOutput]:
        """Outputs that need chunking: everything, if force; otherwise only
        those not already present in the ChunkStore under the current
        (source, key, version)."""
        if self._force:
            return outputs

        present = self._chunk_store.present(self._source_name)
        return [output for output in outputs if (output.key, output.version) not in present]

    async def _run_async(self) -> ChunkingResult:
        """Chunk whichever Stage 1 outputs for this source aren't already
        chunked, and persist the result.

        A document already present in the ChunkStore (same key + version)
        is skipped - the whole point of persisting chunks is so adding or
        modifying one document doesn't force re-chunking (slow,
        embedding-heavy) every other unchanged document too. Use
        force=True to re-chunk everything regardless.
        """
        start_time = time.perf_counter()

        logger.info("Starting chunking: source=%r document_type=%s", self._source_name, self._document_type)

        outputs = self._output_source.list_outputs(self._source_name)
        total = len(outputs)
        logger.info("Loaded %d text-extraction outputs for source", total)

        if not outputs:
            logger.info("Nothing to chunk - no text-extraction outputs found")
            duration = time.perf_counter() - start_time
            return ChunkingResult(total=0, processed=0, skipped=0, total_chunks=0, duration_seconds=duration)

        pending = self._pending_outputs(outputs)
        skipped = total - len(pending)
        logger.info("Chunking: skipped=%d (already chunked) pending=%d", skipped, len(pending))

        if not pending:
            logger.info("Nothing to chunk - all documents already chunked")
            duration = time.perf_counter() - start_time
            return ChunkingResult(total=total, processed=0, skipped=skipped, total_chunks=0, duration_seconds=duration)

        documents = [to_document(output) for output in pending]

        parsers = _build_chunking_pipeline(self._document_type.chunking, self._extraction_config)
        pipeline = IngestionPipeline(transformations=parsers)
        nodes = await pipeline.arun(documents=documents)

        total_chunks = 0
        for doc_key, doc_nodes in _group_by_document(nodes).items():
            version = doc_nodes[0].metadata["version"]
            total_chunks += self._chunk_store.write(self._source_name, doc_key, version, doc_nodes)

        duration = time.perf_counter() - start_time
        logger.info(
            "Finished chunking: processed=%d skipped=%d chunks=%d duration=%.1fs",
            len(pending),
            skipped,
            total_chunks,
            duration,
        )

        return ChunkingResult(
            total=total,
            processed=len(pending),
            skipped=skipped,
            total_chunks=total_chunks,
            duration_seconds=duration,
        )
