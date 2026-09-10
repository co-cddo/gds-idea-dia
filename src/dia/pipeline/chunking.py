"""Stage 2a: chunking — splits Stage 1 text output into TextNode chunks.

Deliberately separate from Stage 2b (graph extraction/LLM propositions and
topics) — see docs/adr/0001-lower-level-graphrag-toolkit-usage.md for why.
Chunking is embedding-heavy and slow (~20-30 min for 100 documents); if
extraction subsequently fails, chunks already produced are untouched in the
ChunkStore, so a retry doesn't have to redo this stage.

Uses llama_index's own IngestionPipeline + num_workers directly, not
graphrag_toolkit's ExtractionPipeline/run_pipeline — llama_index's version
does exactly the same thing (spawn a process pool, batch nodes across
workers) with no extra machinery we need. In particular, no IdRewriter: it
exists to give the toolkit's own IdGenerator deterministic content-hash IDs
for incremental graph updates, which we don't use. Without it, chunk IDs are
llama_index's default random ids, and node.relationships[SOURCE].node_id
still resolves correctly all the way back to the original document's doc_id
(verified directly against real Bedrock-produced chunks and by tracing
llama_index's own NodeParser._postprocess_parsed_nodes) - and to_document()
already sets doc_id=output.key, so that relationship is a stable, meaningful
value for free.
"""

import logging
import time
from dataclasses import dataclass

from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import NodeParser, SentenceSplitter
from llama_index.core.node_parser.text.semantic_splitter import SemanticSplitterNodeParser

from dia.config import ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.pipeline.chunk_store import ChunkStore
from dia.pipeline.graph_extraction_adapter import to_document
from dia.pipeline.graph_extraction_source import TextExtractionOutputSource
from dia.pipeline.logging import PIPELINE_LOGGER_NAME, setup_pipeline_logging

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


@dataclass(frozen=True)
class ChunkingResult:
    """Result of a chunking run."""

    total_documents: int
    total_chunks: int
    skipped: bool = False
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
        """Chunk every Stage 1 output for this source and persist the result.

        If chunks already exist for this source and force is False, skips
        chunking entirely - the whole point of persisting chunks is so a
        failed extraction stage doesn't force redoing this (slow,
        embedding-heavy) one. Use force=True to re-chunk from scratch.
        """
        start_time = time.perf_counter()

        logger.info("Starting chunking: source=%r document_type=%s", self._source_name, self._document_type)

        if not self._force and self._chunk_store.exists(self._source_name):
            logger.info("Chunks already exist for %r - skipping (use force=True to re-chunk)", self._source_name)
            duration = time.perf_counter() - start_time
            existing = len(self._chunk_store.read(self._source_name))
            return ChunkingResult(total_documents=0, total_chunks=existing, skipped=True, duration_seconds=duration)

        outputs = self._output_source.list_outputs(self._source_name)
        total_documents = len(outputs)
        logger.info("Loaded %d text-extraction outputs for source", total_documents)

        if not outputs:
            logger.info("Nothing to chunk - no text-extraction outputs found")
            duration = time.perf_counter() - start_time
            return ChunkingResult(total_documents=0, total_chunks=0, duration_seconds=duration)

        documents = [to_document(output) for output in outputs]

        parsers = _build_chunking_pipeline(self._document_type.chunking, self._extraction_config)
        pipeline = IngestionPipeline(transformations=parsers)
        nodes = pipeline.run(documents=documents, num_workers=self._extraction_config.chunking_num_workers)

        total_chunks = self._chunk_store.write(self._source_name, nodes)

        duration = time.perf_counter() - start_time
        logger.info(
            "Finished chunking: documents=%d chunks=%d duration=%.1fs", total_documents, total_chunks, duration
        )

        return ChunkingResult(total_documents=total_documents, total_chunks=total_chunks, duration_seconds=duration)
