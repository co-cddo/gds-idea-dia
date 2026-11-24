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
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from dia.sources.sidecar import SidecarError, to_json
from dia.sources.sidecar_plan import SidecarPlan

WORKERS = 16
REPORT_COLUMNS = ["label", "status"]


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
    """

    written_new: list[str] = field(default_factory=list)
    written_replaced: list[str] = field(default_factory=list)
    skipped_exists: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


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


def write_plan(
    s3_client: Any,
    bucket: str,
    plan: SidecarPlan,
    *,
    overwrite: bool,
    backup_dir: Path,
    report_path: Path,
    workers: int = WORKERS,
) -> WriteResult:
    """Write the new labels of a plan, and with `overwrite` the replacements too.

    A failure on one label is counted and the rest go on. The report is written even if
    some labels failed.

    Args:
        s3_client: A client that may write to `bucket`. Needs `workers` or more connections.
        bucket: The documents bucket.
        plan: What to write.
        overwrite: Also replace labels that hold something different.
        backup_dir: Where each replaced label's old text is saved first.
        report_path: Where the CSV of keys written is saved.
        workers: How many labels to write at a time.

    Returns:
        What was written, skipped and failed.

    Raises:
        BackupError: If a replaced label could not be saved. Nothing has been written then.
    """
    replace = sorted(plan.replacements) if overwrite else []
    _backup(plan, replace, backup_dir)

    jobs = [(key, plan.new[key], True) for key in sorted(plan.new)]
    jobs += [(key, plan.replacements[key], False) for key in replace]

    def put(job: tuple[str, Any, bool]) -> tuple[str, bool, str]:
        key, sidecar, is_new = job
        try:
            body = to_json(sidecar).encode("utf-8")
            extra = {"IfNoneMatch": "*"} if is_new else {}
            s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json", **extra)
        except SidecarError as e:
            return key, is_new, f"failed: {e}"
        except ClientError as e:
            if is_new and e.response.get("Error", {}).get("Code") == "PreconditionFailed":
                return key, is_new, "exists"
            return key, is_new, f"failed: {e}"
        except BotoCoreError as e:
            return key, is_new, f"failed: {e}"
        return key, is_new, "written"

    result = WriteResult()
    with ThreadPoolExecutor(workers) as pool:
        for key, is_new, status in pool.map(put, jobs):
            if status == "written":
                (result.written_new if is_new else result.written_replaced).append(key)
            elif status == "exists":
                result.skipped_exists.append(key)
            else:
                result.failed[key] = status.removeprefix("failed: ")

    _write_report(result, report_path)
    return result
