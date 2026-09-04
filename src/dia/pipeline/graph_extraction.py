"""Graph extraction runner — Stage 2 of the extraction pipeline.

Reads Stage 1's output, converts it into LlamaIndex Documents, runs it
through graphrag_toolkit's LexicalGraphIndex.extract() using a domain-tuned
prompt, and writes raw chunk-level output. Stops there — no Neptune/AOSS
load, that's a separate, later stage.
"""

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from graphrag_toolkit.lexical_graph import LexicalGraphIndex
from graphrag_toolkit.lexical_graph.indexing import NodeHandler
from graphrag_toolkit.lexical_graph.indexing.build import Checkpoint
from graphrag_toolkit.lexical_graph.indexing.extract import BatchConfig
from graphrag_toolkit.lexical_graph.lexical_graph_index import ExtractionConfig as ToolkitExtractionConfig
from graphrag_toolkit.lexical_graph.lexical_graph_index import IndexingConfig
from llama_index.core.node_parser import NodeParser, SemanticSplitterNodeParser, SentenceSplitter

from dia.config import ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.ledger.protocol import ProcessingLedger
from dia.pipeline.graph_extraction_adapter import to_document
from dia.pipeline.graph_extraction_prompts import TOPIC_EXTRACTION_PROMPT
from dia.pipeline.graph_extraction_source import TextExtractionOutputSource
from dia.pipeline.logging import PIPELINE_LOGGER_NAME, setup_pipeline_logging
from dia.types import DocumentReference

logger = logging.getLogger(PIPELINE_LOGGER_NAME)

STAGE = "graph"

# Neither store is ever real Neptune/AOSS at this stage — extraction only,
# no build/load. "dummy://" is the toolkit's own no-op connection string;
# graph_store=None does NOT work the same way (raises, since the Neptune
# factory tries .startswith() on it before the dummy factory gets a turn).
_DUMMY_STORE = "dummy://"

# Matches graphrag_toolkit.lexical_graph.indexing.build.checkpoint.SAVEPOINT_ROOT_DIR
_CHECKPOINT_SAVEPOINT_DIR = "save_points"


def _checkpoint_name(source_name: str) -> str:
    """Stable checkpoint name for a source.

    Stable (not timestamped) so a retry after a failure only redoes chunks
    the toolkit's own Checkpoint hasn't already marked complete, rather than
    the whole batch.
    """
    return f"dia-graph-extraction-{source_name}"


def clear_checkpoint_dir(source_name: str, output_dir: str | Path = "output") -> None:
    """Delete the checkpoint directory for a source.

    Used when force=True: reusing the same checkpoint name on a forced
    re-run would make the toolkit silently skip chunks it already
    completed, defeating the point of forcing a fresh run.
    """
    path = Path(output_dir) / _CHECKPOINT_SAVEPOINT_DIR / _checkpoint_name(source_name)
    shutil.rmtree(path, ignore_errors=True)


def _build_chunking_pipeline(chunking: ChunkingConfig, extraction_config: ExtractionConfig) -> list[NodeParser]:
    """ChunkingConfig -> the ordered NodeParsers LexicalGraphIndex chunks documents with."""
    parsers: list[NodeParser] = [
        SentenceSplitter(
            chunk_size=chunking.sentence_chunk_size,
            chunk_overlap=chunking.sentence_chunk_overlap,
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
class GraphExtractionResult:
    """Result of a graph extraction run.

    Unlike TextExtractionResult, failed here doesn't mean "confirmed
    broken" — LexicalGraphIndex.extract() isn't per-document fault
    isolated (the toolkit uses plain asyncio.gather, no
    return_exceptions), so a single bad chunk aborts the whole call.
    failed_keys means "not confirmed complete this run"; some of those
    chunks may already be checkpointed and won't be redone next run.
    """

    total: int
    processed: int
    skipped: int
    failed: int
    failed_keys: list[str] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0


class GraphExtractionRunner:
    """Orchestrates Stage 2: read Stage 1 output, extract topics/entities/relationships.

    Injection-friendly like TextExtractionRunner. Never touches Neptune or
    AOSS — graph_store/vector_store are always the toolkit's dummy no-op
    stores, since this stage stops at raw extraction.
    """

    def __init__(
        self,
        source_name: str,
        document_type: DocumentType,
        output_source: TextExtractionOutputSource,
        ledger: ProcessingLedger,
        extraction_config: ExtractionConfig,
        graph_output_handler: NodeHandler,
        batch_config: BatchConfig | None = None,
        force: bool = False,
        log_dir: str | None = None,
    ) -> None:
        self._source_name = source_name
        self._document_type = document_type
        self._output_source = output_source
        self._ledger = ledger
        self._extraction_config = extraction_config
        self._graph_output_handler = graph_output_handler
        self._batch_config = batch_config
        self._force = force
        self._log_file = setup_pipeline_logging(self._source_name, log_dir=log_dir)

    def run(self) -> GraphExtractionResult:
        """Sync public interface, matching TextExtractionRunner's shape."""
        start_time = time.perf_counter()

        logger.info("Starting graph extraction: source=%r document_type=%s", self._source_name, self._document_type)

        outputs = self._output_source.list_outputs(self._source_name)
        total = len(outputs)
        logger.info("Loaded %d text-extraction outputs for source", total)

        outputs_by_key = {output.key: output for output in outputs}
        refs = [
            DocumentReference(key=output.key, content_type=output.content_type, version=output.version)
            for output in outputs
        ]

        if self._force:
            pending_refs = refs
            skipped = 0
            clear_checkpoint_dir(self._source_name, output_dir=self._extraction_config.local_output_dir)
            logger.info("Force enabled — cleared checkpoint, reprocessing all %d documents", len(pending_refs))
        else:
            pending_refs = self._ledger.get_unprocessed(refs, self._source_name, STAGE)
            skipped = len(refs) - len(pending_refs)
            logger.info("Ledger: skipped=%d (already processed) pending=%d", skipped, len(pending_refs))

        if not pending_refs:
            logger.info("Nothing to process — all documents already in ledger")
            duration = time.perf_counter() - start_time
            return GraphExtractionResult(total=total, processed=0, skipped=skipped, failed=0, duration_seconds=duration)

        documents = [to_document(outputs_by_key[ref.key]) for ref in pending_refs]
        self._extraction_config.apply_to_graphrag_config()
        graph_index = self._build_index()
        checkpoint = Checkpoint(
            _checkpoint_name(self._source_name), output_dir=self._extraction_config.local_output_dir
        )

        try:
            graph_index.extract(
                documents,
                handler=self._graph_output_handler,
                checkpoint=checkpoint,
                show_progress=True,
            )
        except Exception as exc:
            duration = time.perf_counter() - start_time
            failed_keys = [ref.key for ref in pending_refs]
            logger.warning("Graph extraction failed: source=%r error=%s", self._source_name, exc)
            return GraphExtractionResult(
                total=total,
                processed=0,
                skipped=skipped,
                failed=len(pending_refs),
                failed_keys=failed_keys,
                error=str(exc),
                duration_seconds=duration,
            )

        entries = [(ref, outputs_by_key[ref.key].metadata.get("department")) for ref in pending_refs]
        self._ledger.mark_processed_many(entries, self._source_name, STAGE)

        duration = time.perf_counter() - start_time
        logger.info("Finished: processed=%d skipped=%d duration=%.1fs", len(pending_refs), skipped, duration)

        return GraphExtractionResult(
            total=total,
            processed=len(pending_refs),
            skipped=skipped,
            failed=0,
            duration_seconds=duration,
        )

    def _build_index(self) -> LexicalGraphIndex:
        """Construct the LexicalGraphIndex for this run, wired from our own configs."""
        chunking = self._document_type.chunking
        indexing_config = IndexingConfig(
            chunking=_build_chunking_pipeline(chunking, self._extraction_config),
            extraction=ToolkitExtractionConfig(
                preferred_entity_classifications=self._document_type.entity_classifications,
                extract_topics_prompt_template=TOPIC_EXTRACTION_PROMPT,
                extraction_llm=self._extraction_config.to_llm(),
            ),
            batch_config=self._batch_config,
        )
        return LexicalGraphIndex(
            graph_store=_DUMMY_STORE,
            vector_store=_DUMMY_STORE,
            indexing_config=indexing_config,
        )
