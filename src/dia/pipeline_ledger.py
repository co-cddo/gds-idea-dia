"""The pipeline ledger: what each stage has done to each version of each document.

A stage asks `pending` which documents it still has to do, does them, writes each one's
output, and only then records it as done. Documents already done at their current version
are skipped, so a run over a whole department only does the new and changed ones.

    ledger = DynamoLedger.from_names(current_names())
    todo = pending(versions, ledger.records("gats_business_cases", Stage.TEXT))
    ...  # process each document in `todo` and write its output
    ledger.record([LedgerRecord.done(...)])   # only after the output is written

**Record a document as done only after its output is safely written.** If the run stops
before that, there is no record and the document is done again next time. A record written
ahead of the work would make a document with no output look finished, and it would be
skipped for good.

A record is identified by source, stage, document key and version. A document's version is
its S3 `LastModified` (`document_version`): when the file is replaced, it has a new version,
so it is not found in the ledger and is done again. Records of older versions stay.
Recording the same document and version twice replaces the earlier record, so a document
that failed and is later done ends up done.

Stored in DynamoDB (`DynamoLedger`) with partition key `source#stage` and sort key
`document_key#version`, so one query gives a stage's records for a source. `LocalLedger`
keeps the same records in JSON files, for runs on a laptop.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from dia.naming import Names


class Stage(StrEnum):
    """The stages of the graph pipeline, in order."""

    TEXT = "text"
    CHUNK = "chunk"
    PROPOSITIONS = "propositions"
    TOPICS = "topics"
    VALIDATE = "validate"
    EMBED = "embed"
    LOAD = "load"


class Status(StrEnum):
    """How a stage ended for a document."""

    DONE = "done"
    FAILED = "failed"


class LedgerError(Exception):
    """A ledger could not be read."""


def document_version(last_modified: dt.datetime) -> str:
    """The version of a document: when it was last changed, as UTC text such as `2026-11-24T10:15:00Z`.

    Args:
        last_modified: The object's S3 `LastModified`. It must have a timezone.

    Raises:
        ValueError: If `last_modified` has no timezone.
    """
    if last_modified.tzinfo is None:
        raise ValueError("last_modified needs a timezone")
    return last_modified.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LedgerRecord:
    """One stage's result for one version of one document. Build it with `done` or `failed`.

    Attributes:
        source: The source's key, for example `gats_business_cases`.
        stage: The stage that ran.
        document_key: The document's key in its bucket.
        version: The document's version, from `document_version`.
        status: Done or failed.
        code_version: The version of this code that did the work.
        reason: Why it failed. Set only when it failed.
        output_location: Where the stage wrote its output, such as an S3 URI. Set when it is done.
        recorded_at: When the record was made.
    """

    source: str
    stage: Stage
    document_key: str
    version: str
    status: Status
    code_version: str
    reason: str | None = None
    output_location: str | None = None
    recorded_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))

    def __post_init__(self) -> None:
        if not (self.source and self.document_key and self.version):
            raise ValueError("a record needs a source, a document key and a version")
        if self.status is Status.FAILED and not self.reason:
            raise ValueError("a failed record needs a reason")
        if self.status is Status.DONE and self.reason:
            raise ValueError("a done record has no reason")

    @classmethod
    def done(
        cls,
        source: str,
        stage: Stage,
        document_key: str,
        version: str,
        *,
        code_version: str,
        output_location: str | None = None,
    ) -> LedgerRecord:
        """A record that the stage finished and its output is written."""
        return cls(source, stage, document_key, version, Status.DONE, code_version, output_location=output_location)

    @classmethod
    def failed(
        cls, source: str, stage: Stage, document_key: str, version: str, *, code_version: str, reason: str
    ) -> LedgerRecord:
        """A record that the stage failed, and why."""
        return cls(source, stage, document_key, version, Status.FAILED, code_version, reason=reason)

    @property
    def partition(self) -> str:
        """Which records this one is listed with: the source and stage."""
        return _partition(self.source, self.stage)

    @property
    def sort(self) -> str:
        """What identifies it within its partition: the document and its version."""
        return f"{self.document_key}#{self.version}"


def _partition(source: str, stage: Stage) -> str:
    return f"{source}#{stage.value}"


def _to_item(record: LedgerRecord) -> dict[str, str]:
    """The record as stored: only the fields that are set, all text."""
    item = {
        "pk": record.partition,
        "sk": record.sort,
        "source": record.source,
        "stage": record.stage.value,
        "document_key": record.document_key,
        "version": record.version,
        "status": record.status.value,
        "code_version": record.code_version,
        "recorded_at": record.recorded_at.isoformat(),
    }
    if record.reason is not None:
        item["reason"] = record.reason
    if record.output_location is not None:
        item["output_location"] = record.output_location
    return item


def _from_item(item: Mapping[str, Any]) -> LedgerRecord:
    return LedgerRecord(
        source=item["source"],
        stage=Stage(item["stage"]),
        document_key=item["document_key"],
        version=item["version"],
        status=Status(item["status"]),
        code_version=item["code_version"],
        reason=item.get("reason"),
        output_location=item.get("output_location"),
        recorded_at=dt.datetime.fromisoformat(item["recorded_at"]),
    )


def pending(versions: Mapping[str, str], records: Iterable[LedgerRecord], *, retry_failed: bool = False) -> list[str]:
    """The documents a stage still has to do.

    Args:
        versions: Each document's key to its current version.
        records: The stage's records for the source, from `PipelineLedger.records`.
        retry_failed: Do documents that failed at their current version again.

    Returns:
        The keys to do, in the order of `versions`. A document is left out if it is done at its
        current version, or failed at it and `retry_failed` is not set.
    """
    skip = {Status.DONE} if retry_failed else {Status.DONE, Status.FAILED}
    settled = {(record.document_key, record.version) for record in records if record.status in skip}
    return [key for key, version in versions.items() if (key, version) not in settled]


class PipelineLedger(Protocol):
    """Where a stage's records are kept."""

    def records(self, source: str, stage: Stage) -> list[LedgerRecord]:
        """Every record of this source and stage, whatever the document or version."""
        ...

    def record(self, records: Iterable[LedgerRecord]) -> None:
        """Save records. One for the same source, stage, document and version replaces the earlier one."""
        ...


class DynamoLedger:
    """The ledger in a DynamoDB table with string keys `pk` and `sk`."""

    def __init__(self, table: Any) -> None:
        """Use a boto3 DynamoDB `Table` (the pipeline ledger table)."""
        self._table = table

    @classmethod
    def from_names(cls, names: Names) -> DynamoLedger:
        """The ledger table of the deployment `names` is for, using the active AWS credentials."""
        import boto3

        from dia.naming import REGION

        return cls(boto3.resource("dynamodb", region_name=REGION).Table(names("pipeline-ledger")))

    def records(self, source: str, stage: Stage) -> list[LedgerRecord]:
        """Every record of this source and stage, read in one consistent query, following its pages."""
        from boto3.dynamodb.conditions import Key

        found: list[LedgerRecord] = []
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(_partition(source, stage)),
            "ConsistentRead": True,
        }
        while True:
            page = self._table.query(**query)
            found += [_from_item(item) for item in page["Items"]]
            if "LastEvaluatedKey" not in page:
                return found
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def record(self, records: Iterable[LedgerRecord]) -> None:
        """Save records in batches. A later one for the same key in the same call wins."""
        with self._table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
            for record in records:
                batch.put_item(Item=_to_item(record))


class LocalLedger:
    """The ledger in JSON files in a directory, one per source and stage, for runs on this machine."""

    def __init__(self, directory: Path) -> None:
        """Keep the files in `directory`, which is created when something is first recorded."""
        self._directory = directory

    def _path(self, source: str, stage: Stage) -> Path:
        return self._directory / f"{source}__{stage.value}.json"

    def _read(self, path: Path) -> dict[str, dict[str, str]]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise LedgerError(f"{path} is not a ledger file: {error}") from error

    def records(self, source: str, stage: Stage) -> list[LedgerRecord]:
        """Every record of this source and stage."""
        return [_from_item(item) for item in self._read(self._path(source, stage)).values()]

    def record(self, records: Iterable[LedgerRecord]) -> None:
        """Save records. Each file is replaced whole, so a stopped run leaves the old file or the new one."""
        by_partition: dict[tuple[str, Stage], list[LedgerRecord]] = {}
        for record in records:
            by_partition.setdefault((record.source, record.stage), []).append(record)

        self._directory.mkdir(parents=True, exist_ok=True)
        for (source, stage), group in by_partition.items():
            path = self._path(source, stage)
            items = self._read(path)
            items.update({record.sort: _to_item(record) for record in group})
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(items, indent=1), encoding="utf-8")
            os.replace(temporary, path)
