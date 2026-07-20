"""Pipeline runner — orchestrates document extraction end-to-end.

Flow:
    source.list_documents()                      -> all refs
    filters (department, etc.)                   -> filtered refs
    ledger.get_unprocessed(filtered, source)     -> pending refs
    for ref in pending:
        content = source.load_document(ref)
        text = get_extractor(ref.content_type).extract(content)
        # stub: GraphRAG extraction goes here
        ledger.mark_processed(ref, source_name)
    -> return PipelineResult
"""

import logging
import time
from dataclasses import dataclass, field

from dia.extractors import get_extractor
from dia.filters.protocol import DocumentFilter
from dia.ledger.protocol import ProcessingLedger
from dia.pipeline.logging import PIPELINE_LOGGER_NAME, setup_pipeline_logging
from dia.sources.protocol import DocumentSource

logger = logging.getLogger(PIPELINE_LOGGER_NAME)


@dataclass(frozen=True)
class PipelineResult:
    """Result of a pipeline run.

    Attributes:
        total: Total documents discovered by the source.
        processed: Successfully processed this run.
        skipped: Already in ledger (previously processed).
        failed: Failed during this run (logged, will retry next run).
        filtered_out: Removed by filters before processing.
        failed_keys: Keys of documents that failed (for CLI output).
        duration_seconds: Wall-clock time for the run.
    """

    total: int
    processed: int
    skipped: int
    failed: int
    filtered_out: int = 0
    failed_keys: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class PipelineRunner:
    """Orchestrates the extraction pipeline for a single source.

    Injection-friendly: all dependencies passed via constructor.
    No globals, no singletons, fully testable.
    """

    def __init__(
        self,
        source: DocumentSource,
        ledger: ProcessingLedger,
        source_name: str,
        filters: list[DocumentFilter] | None = None,
        log_dir: str | None = None,
    ) -> None:
        self._source = source
        self._ledger = ledger
        self._source_name = source_name
        self._filters = filters or []
        self._log_file = setup_pipeline_logging(source_name, log_dir=log_dir)

    def run(self) -> PipelineResult:
        """Execute the pipeline: list, filter, extract, record.

        Returns:
            PipelineResult summarising what happened.
        """
        start_time = time.perf_counter()

        # --- Discover ---
        logger.info(
            "Starting extraction: source=%r document_type=%s",
            self._source_name,
            self._source.data_source.document_type,
        )

        all_refs = self._source.list_documents()
        total = len(all_refs)
        logger.info("Discovered %d documents in source", total)

        # --- Apply filters ---
        filtered_refs = all_refs
        for f in self._filters:
            before = len(filtered_refs)
            filtered_refs = f.filter(filtered_refs)
            removed = before - len(filtered_refs)
            if removed:
                logger.info(
                    "Filter %s removed %d documents",
                    type(f).__name__,
                    removed,
                )

        filtered_out = total - len(filtered_refs)
        if filtered_out:
            logger.info("Filters removed %d documents total, %d remain", filtered_out, len(filtered_refs))

        # --- Ledger filter ---
        pending = self._ledger.get_unprocessed(filtered_refs, self._source_name)
        skipped = len(filtered_refs) - len(pending)
        logger.info(
            "Ledger: skipped=%d (already processed) pending=%d",
            skipped,
            len(pending),
        )

        if not pending:
            logger.info("Nothing to process — all documents already in ledger")
            duration = time.perf_counter() - start_time
            return PipelineResult(
                total=total,
                processed=0,
                skipped=skipped,
                failed=0,
                filtered_out=filtered_out,
                duration_seconds=duration,
            )

        # --- Process ---
        processed = 0
        failed = 0
        failed_keys: list[str] = []

        for idx, ref in enumerate(pending, start=1):
            progress = f"[{idx}/{len(pending)}]"

            logger.info(
                "%s Processing: key=%r version=%r content_type=%r",
                progress,
                ref.key,
                ref.version,
                ref.content_type,
            )
            logger.debug("%s Full reference: %s", progress, ref)

            try:
                doc_start = time.perf_counter()

                # Load document bytes
                content = self._source.load_document(ref)
                logger.debug("%s Downloaded: %d bytes", progress, len(content))

                # Extract text
                extractor = get_extractor(ref.content_type)
                text = extractor.extract(content)
                logger.info("%s Extracted: chars=%d", progress, len(text))
                logger.debug("%s Text preview: %r", progress, text[:200])

                # TODO: GraphRAG extraction goes here (stub for now)
                logger.debug(
                    "%s [STUB] Would run GraphRAG extraction on %d chars",
                    progress,
                    len(text),
                )

                # Record success
                self._ledger.mark_processed(ref, self._source_name)
                processed += 1

                doc_duration = time.perf_counter() - doc_start
                logger.info("%s Complete: duration=%.1fs", progress, doc_duration)

            except Exception:
                failed += 1
                failed_keys.append(ref.key)
                logger.warning("%s Failed: key=%r", progress, ref.key, exc_info=True)

        # --- Summary ---
        duration = time.perf_counter() - start_time
        logger.info(
            "Finished: processed=%d failed=%d skipped=%d filtered_out=%d duration=%.1fs",
            processed,
            failed,
            skipped,
            filtered_out,
            duration,
        )

        if failed_keys:
            logger.warning("Failed documents: %s", failed_keys)

        return PipelineResult(
            total=total,
            processed=processed,
            skipped=skipped,
            failed=failed,
            filtered_out=filtered_out,
            failed_keys=failed_keys,
            duration_seconds=duration,
        )
