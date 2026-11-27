"""One-time import of the old pipeline's ledger into the pipeline ledger. Dev only.

The old code ingested some GATS documents into the dev graph and kept a JSON file mapping
each document's `file_reference` number to its file name. Those documents are already in the
graph, so the new pipeline should not ingest them again. This marks each of them as done, for
every stage, at the version the document has now.

    uv run python scripts/import_legacy_ledger.py output/metadata/file_reference_mapping_new_v2.json
    uv run python scripts/import_legacy_ledger.py output/metadata/file_reference_mapping_new_v2.json --write

Run it with dev credentials. It reads the documents bucket through the cross-account role and
writes only to the dev pipeline ledger. It is a dry run unless given `--write`, and it asks
before writing. A document or stage that already has a record is left alone, so it can be run
again. Entries whose file is not in the bucket are skipped and listed in
`./output/ledger/legacy-import-not-found.csv`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import typer
from gds_idea_cdk_constructs import DeploymentEnvironment

from dia.cli_helpers import current_names
from dia.naming import REGION
from dia.pipeline_ledger import DynamoLedger, LedgerRecord, PipelineLedger, Stage, document_version
from dia.preflight import source_s3_client
from dia.runtime_config import RuntimeConfig
from dia.sources.definitions import SOURCES
from dia.sources.models import resolve

SOURCE = "gats_business_cases"
LEGACY_CODE_VERSION = "legacy-import"
NOT_FOUND_REPORT = Path("output/ledger/legacy-import-not-found.csv")


@dataclass(frozen=True)
class ImportResult:
    """What an import did or would do.

    Attributes:
        entries: Entries in the mapping file.
        found: Entries whose file is in the bucket.
        not_found: File names of the entries whose file is not in the bucket.
        to_write: Records that were missing from the ledger.
        already_present: Records the ledger already had, which are left alone.
        written: Records written. Zero for a dry run.
    """

    entries: int
    found: int
    not_found: list[str]
    to_write: int
    already_present: int
    written: int


def read_mapping(path: Path) -> dict[str, str]:
    """Read the old ledger file: `file_reference` to file name.

    Raises:
        ValueError: If the file is not an object of text to text.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError(f"{path} is not a map of file_reference to file name")
    return data


def list_versions(s3_client: Any, bucket: str, prefix: str) -> dict[str, str]:
    """Each object under `prefix`, by key, with its current version."""
    versions: dict[str, str] = {}
    for page in s3_client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            versions[item["Key"]] = document_version(item["LastModified"])
    return versions


def run(
    mapping: Mapping[str, str],
    versions: Mapping[str, str],
    ledger: PipelineLedger,
    *,
    prefix: str,
    write: bool,
    confirm: Callable[[str], bool],
) -> ImportResult:
    """Work out what is missing from the ledger, and with `write` and a yes, record it.

    Args:
        mapping: The old ledger, `file_reference` to file name.
        versions: Each document in the bucket, by key, with its current version.
        ledger: The ledger to read, and to write to when `write` is set.
        prefix: Where the documents are in the bucket, for example `files/`.
        write: Write the missing records. Without it nothing is written.
        confirm: Asked once, with the number of records, before writing. A no writes nothing.
    """
    names = list(mapping.values())
    found = [name for name in names if prefix + name in versions]
    not_found = [name for name in names if prefix + name not in versions]

    wanted = [
        LedgerRecord.done(SOURCE, stage, prefix + name, versions[prefix + name], code_version=LEGACY_CODE_VERSION)
        for stage in Stage
        for name in found
    ]
    present = {stage: {(r.document_key, r.version) for r in ledger.records(SOURCE, stage)} for stage in Stage}
    missing = [r for r in wanted if (r.document_key, r.version) not in present[r.stage]]

    written = 0
    if write and missing and confirm(f"Write {len(missing)} records to the ledger?"):
        ledger.record(missing)
        written = len(missing)

    return ImportResult(
        entries=len(mapping),
        found=len(found),
        not_found=not_found,
        to_write=len(missing),
        already_present=len(wanted) - len(missing),
        written=written,
    )


def write_not_found(names: list[str], path: Path = NOT_FOUND_REPORT) -> None:
    """Save the names of files that are not in the bucket, on this machine."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["file_name"])
        writer.writerows([name] for name in names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mapping", type=Path, help="The old ledger: a JSON map of file_reference to file name.")
    parser.add_argument("--write", action="store_true", help="Write the missing records, after asking.")
    parser.add_argument("--yes", action="store_true", help="With --write, do not ask first.")
    args = parser.parse_args(argv)

    try:
        names = current_names()
    except typer.Exit:  # it has already said why
        return 1
    if names.environment != DeploymentEnvironment.DEVELOPMENT:
        print("Error: this imports into the dev ledger only. Run it with dev credentials.")
        return 1

    location = resolve(SOURCES[SOURCE].location, names.environment)
    role_arn = RuntimeConfig.load(names).cross_account_role_arn if location.cross_account else None
    s3 = source_s3_client(role_arn, boto3.client("sts", region_name=REGION), session_name="dia-ledger-import")

    mapping = read_mapping(args.mapping)
    versions = list_versions(s3, location.bucket, location.prefix)
    ledger = DynamoLedger.from_names(names)

    def confirm(question: str) -> bool:
        return args.yes or input(f"{question} [y/N] ").strip().lower() == "y"

    result = run(mapping, versions, ledger, prefix=location.prefix, write=args.write, confirm=confirm)
    write_not_found(result.not_found)

    print(f"Entries in the old ledger:        {result.entries}")
    print(f"  file found in the bucket:       {result.found}")
    print(f"  file not in the bucket:         {len(result.not_found)} (skipped, listed in {NOT_FOUND_REPORT})")
    print(f"Records already in the ledger:    {result.already_present}")
    print(f"Records to write:                 {result.to_write}")
    if result.written:
        print(f"Written: {result.written}")
    elif args.write and result.to_write:
        print("Nothing written.")
    elif not args.write:
        print("Dry run: nothing was written. Pass --write to record them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
