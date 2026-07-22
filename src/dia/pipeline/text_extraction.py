"""Text extraction runner — Stage 1 of the extraction pipeline.

Downloads documents in parallel (async), extracts text using existing
extractors (offloaded to threads), writes JSON to the text-extracted
bucket, and records success in the ledger.

Processes in configurable batches with checkpointing after each batch.
If the process dies, at most one batch of work is lost — the ledger
knows exactly what's been completed.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import aioboto3

from dia.config import TextExtractionConfig
from dia.extractors import get_extractor
from dia.filters.protocol import DocumentFilter
from dia.ledger.protocol import ProcessingLedger
from dia.pipeline.logging import PIPELINE_LOGGER_NAME, setup_pipeline_logging
from dia.sources.protocol import DocumentSource
from dia.types import DocumentReference

logger = logging.getLogger(PIPELINE_LOGGER_NAME)

STAGE = "text"


@dataclass(frozen=True)
class TextExtractionResult:
    """Result of a text extraction run."""

    total: int
    processed: int
    skipped: int
    failed: int
    filtered_out: int = 0
    failed_keys: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class TextExtractionRunner:
    """Orchestrates Stage 1: download + extract text + write to bucket.

    Injection-friendly: all dependencies passed via constructor.
    Public interface is sync (def run()), async internals are hidden.
    """

    def __init__(
        self,
        source: DocumentSource,
        ledger: ProcessingLedger,
        config: TextExtractionConfig,
        output_bucket: str | None = None,
        output_dir: Path | str | None = None,
        output_s3_client=None,
        filters: list[DocumentFilter] | None = None,
        log_dir: str | None = None,
    ) -> None:
        if bool(output_bucket) == bool(output_dir):
            msg = "Provide exactly one of output_bucket or output_dir"
            raise ValueError(msg)

        self._source = source
        self._ledger = ledger
        self._config = config
        self._output_bucket = output_bucket
        self._output_dir = Path(output_dir) if output_dir else None
        self._output_s3_client = output_s3_client
        self._filters = filters or []
        self._source_name = source.data_source.name
        self._log_file = setup_pipeline_logging(self._source_name, log_dir=log_dir)

    def run(self) -> TextExtractionResult:
        """Sync public interface — runs the async pipeline internally."""
        return asyncio.run(self._run_async())

    async def _run_async(self) -> TextExtractionResult:
        """Internal async implementation: list → filter → batch → process."""
        start_time = time.perf_counter()

        # --- Discover ---
        logger.info(
            "Starting text extraction: source=%r document_type=%s",
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
                logger.info("Filter %s removed %d documents", type(f).__name__, removed)

        filtered_out = total - len(filtered_refs)

        # --- Ledger filter ---
        pending = self._ledger.get_unprocessed(filtered_refs, self._source_name, STAGE)
        skipped = len(filtered_refs) - len(pending)
        logger.info("Ledger: skipped=%d (already processed) pending=%d", skipped, len(pending))

        if not pending:
            logger.info("Nothing to process — all documents already in ledger")
            duration = time.perf_counter() - start_time
            return TextExtractionResult(
                total=total,
                processed=0,
                skipped=skipped,
                failed=0,
                filtered_out=filtered_out,
                duration_seconds=duration,
            )

        # --- Process in batches ---
        processed = 0
        failed = 0
        failed_keys: list[str] = []
        batch_size = self._config.batch_size

        batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
        logger.info("Processing %d documents in %d batches (batch_size=%d)", len(pending), len(batches), batch_size)

        session = aioboto3.Session()

        for batch_idx, batch in enumerate(batches, start=1):
            logger.info("Batch %d/%d: processing %d documents", batch_idx, len(batches), len(batch))

            batch_results = await self._process_batch(session, batch)

            # Checkpoint: write results + update ledger
            for ref, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    failed += 1
                    failed_keys.append(ref.key)
                    logger.warning("Failed: key=%r error=%s", ref.key, result)
                else:
                    # Write JSON to output bucket
                    await self._write_output(session, ref, result)
                    self._ledger.mark_processed(ref, self._source_name, STAGE)
                    processed += 1

            logger.info(
                "Batch %d/%d complete: processed=%d failed=%d",
                batch_idx,
                len(batches),
                processed,
                failed,
            )

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

        return TextExtractionResult(
            total=total,
            processed=processed,
            skipped=skipped,
            failed=failed,
            filtered_out=filtered_out,
            failed_keys=failed_keys,
            duration_seconds=duration,
        )

    async def _process_batch(self, session: aioboto3.Session, batch: list[DocumentReference]) -> list[str | Exception]:
        """Process a batch of documents concurrently.

        Downloads via source.load_document() and extracts text, capped by max_concurrency.
        Returns a list of extracted text strings or Exception objects (in order).
        """
        semaphore = asyncio.Semaphore(self._config.max_concurrency)

        async def _process_one(ref: DocumentReference) -> str:
            async with semaphore:
                # Download via the source (handles its own S3/credentials)
                content = await asyncio.to_thread(self._source.load_document, ref)
                text = await asyncio.to_thread(self._extract_text, content, ref.content_type)
                logger.debug("Extracted: key=%r chars=%d", ref.key, len(text))
                return text

        tasks = [_process_one(ref) for ref in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return list(results)

    def _extract_text(self, content: bytes, content_type: str) -> str:
        """Extract text using the appropriate extractor (runs in thread)."""
        extractor = get_extractor(content_type)
        return extractor.extract(content)

    async def _write_output(self, session: aioboto3.Session, ref: DocumentReference, text: str) -> None:
        """Write extracted text as JSON to the configured output (local disk or S3)."""
        output_key = f"{self._source_name}/{ref.key}.json"
        payload = {
            "key": ref.key,
            "source_name": self._source_name,
            "content_type": ref.content_type,
            "version": ref.version,
            "text": text,
            "chars": len(text),
            "extracted_at": datetime.now(tz=UTC).isoformat(),
            "code_version": version("dia"),
        }
        body = json.dumps(payload, ensure_ascii=False)

        if self._output_dir is not None:
            await asyncio.to_thread(self._write_local, output_key, body)
        elif self._output_s3_client:
            # Sync client injected for testing — run in thread
            await asyncio.to_thread(
                self._output_s3_client.put_object,
                Bucket=self._output_bucket,
                Key=output_key,
                Body=body.encode(),
                ContentType="application/json",
            )
        else:
            async with session.client("s3") as s3:
                await s3.put_object(
                    Bucket=self._output_bucket,
                    Key=output_key,
                    Body=body.encode(),
                    ContentType="application/json",
                )

    def _write_local(self, output_key: str, body: str) -> None:
        """Write JSON output to local disk, mirroring the S3 key structure."""
        output_path = self._output_dir / output_key
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")
