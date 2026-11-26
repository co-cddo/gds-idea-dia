"""Write the sidecars of a `SidecarPlan` to the bucket.

This is the only place that changes the GATS bucket. A new label is written only if none
exists (`IfNoneMatch="*"`), so a label that appeared since planning is never replaced. A
label that holds something different is replaced only with `overwrite`, and its old text is
saved on this machine first, because the bucket has no versioning.
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from dia.sources.sidecar import Sidecar, SidecarError, to_json
from dia.sources.sidecar_plan import SidecarPlan

WORKERS = 16
REPORT_COLUMNS = ["label", "status"]
# S3 answers a losing conditional write with 412, or 409 if two writes to a key race.
_LABEL_EXISTS_CODES = ("PreconditionFailed", "ConditionalRequestConflict")


class _Status(StrEnum):
    """How writing one label ended."""

    WRITTEN = "written"
    EXISTS = "exists"
    FAILED = "failed"


@dataclass(frozen=True)
class _Job:
    """One label to write. `is_new` is true if no label should exist at `key` yet."""

    key: str
    sidecar: Sidecar
    is_new: bool


@dataclass(frozen=True)
class _Done:
    """The end of writing one label. `reason` is set only when it failed."""

    key: str
    is_new: bool
    status: _Status
    reason: str = ""


@dataclass(frozen=True)
class Selection:
    """The labels a write will touch, given whether it may overwrite.

    Attributes:
        new: Sidecars to write where there is no label, by sidecar key.
        replace: Sidecars that will replace a different label, by sidecar key. Empty
            unless overwriting.
        left_alone: Labels that differ from the plan and will not be replaced, because
            overwriting is off.
    """

    new: dict[str, Sidecar]
    replace: dict[str, Sidecar]
    left_alone: int

    @property
    def total(self) -> int:
        """Labels that will be written."""
        return len(self.new) + len(self.replace)


def select(plan: SidecarPlan, *, overwrite: bool) -> Selection:
    """Say which of a plan's labels a write will touch. `write_plan` writes exactly this."""
    if overwrite:
        return Selection(new=dict(plan.new), replace=dict(plan.replacements), left_alone=0)
    return Selection(new=dict(plan.new), replace={}, left_alone=len(plan.replacements))


class BackupError(Exception):
    """A label that would be replaced could not be saved first. Nothing was written to S3."""


@dataclass
class WriteResult:
    """What a write did.

    Attributes:
        written_new: Labels written where there was none.
        written_replaced: Labels that replaced a different one.
        skipped_exists: New labels not written because one had appeared since planning.
        failed: Label key to the reason it could not be written.
        backup_dir: Where the old text of the labels to be replaced was saved, or `None`
            if nothing was saved. Set before any label is written, so it holds even if
            some replacements failed.
    """

    written_new: list[str] = field(default_factory=list)
    written_replaced: list[str] = field(default_factory=list)
    skipped_exists: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    backup_dir: Path | None = None


def _backup(plan: SidecarPlan, keys: list[str], backup_dir: Path) -> None:
    """Save the text of each label in `keys` under `backup_dir`, at its S3 key.

    Raises:
        BackupError: If a label has no saved text or a file cannot be written.
    """
    for key in keys:
        text = plan.replaced_text.get(key)
        if text is None:
            raise BackupError(f"no saved text for {key}")
        path = backup_dir / key
        if not path.resolve().is_relative_to(backup_dir.resolve()):
            raise BackupError(f"{key} would be saved outside {backup_dir}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as e:
            raise BackupError(f"could not save {key} to {path}: {e}") from e


def _write_report(result: WriteResult, path: Path) -> None:
    """Write the keys written, skipped and failed to a CSV file. Keys only, no label content."""
    rows = (
        [(key, "new") for key in result.written_new]
        + [(key, "replaced") for key in result.written_replaced]
        + [(key, "skipped_exists") for key in result.skipped_exists]
        + [(key, "failed") for key in result.failed]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(REPORT_COLUMNS)
        writer.writerows(rows)


def _put_label(s3_client: Any, bucket: str, job: _Job) -> _Done:
    """Write one label. A new label is written only if none exists, so it never replaces one."""
    try:
        body = to_json(job.sidecar).encode("utf-8")
        extra = {"IfNoneMatch": "*"} if job.is_new else {}
        s3_client.put_object(Bucket=bucket, Key=job.key, Body=body, ContentType="application/json", **extra)
    except ClientError as e:
        if job.is_new and e.response.get("Error", {}).get("Code") in _LABEL_EXISTS_CODES:
            return _Done(job.key, job.is_new, _Status.EXISTS)
        return _Done(job.key, job.is_new, _Status.FAILED, str(e))
    except (SidecarError, BotoCoreError) as e:
        return _Done(job.key, job.is_new, _Status.FAILED, str(e))
    return _Done(job.key, job.is_new, _Status.WRITTEN)


def write_plan(
    s3_client: Any,
    bucket: str,
    plan: SidecarPlan,
    *,
    overwrite: bool,
    backup_dir: Path,
    report_path: Path,
) -> WriteResult:
    """Write the new labels of a plan, and with `overwrite` the replacements too.

    Writes exactly what `select(plan, overwrite=overwrite)` returns, `WORKERS` labels at a
    time. A failure on one label is counted and the rest go on. The report is written even
    if some labels failed.

    Args:
        s3_client: A client that may write to `bucket`. Needs `WORKERS` or more connections.
        bucket: The documents bucket.
        plan: What to write.
        overwrite: Also replace labels that hold something different.
        backup_dir: Where each replaced label's old text is saved first.
        report_path: Where the CSV of keys written is saved.

    Returns:
        What was written, skipped and failed, and where old labels were saved.

    Raises:
        BackupError: If a replaced label could not be saved. Nothing has been written then.
    """
    chosen = select(plan, overwrite=overwrite)
    replace = sorted(chosen.replace)
    _backup(plan, replace, backup_dir)

    jobs = [_Job(key, chosen.new[key], True) for key in sorted(chosen.new)]
    jobs += [_Job(key, chosen.replace[key], False) for key in replace]

    result = WriteResult(backup_dir=backup_dir if replace else None)
    with ThreadPoolExecutor(WORKERS) as pool:
        for done in pool.map(partial(_put_label, s3_client, bucket), jobs):
            if done.status is _Status.WRITTEN:
                (result.written_new if done.is_new else result.written_replaced).append(done.key)
            elif done.status is _Status.EXISTS:
                result.skipped_exists.append(done.key)
            else:
                result.failed[done.key] = done.reason

    _write_report(result, report_path)
    return result
