"""Work out which sidecars the GATS export would produce, given what is in the bucket.

Pure code: it takes the export rows and the keys found in the bucket, and returns counts
and the sidecars to write. It does no S3 work and writes nothing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dia.sources.gats_sidecars import (
    choose_documents,
    documents_for_row,
    is_test_row,
    unmatched_departments,
    unreadable_date,
    unrecognised_submitter,
)
from dia.sources.sidecar import Sidecar, is_sidecar_key, sidecar_key


@dataclass(frozen=True)
class SidecarPlan:
    """What a run would do. Each count is of documents unless it says rows.

    Attributes:
        rows_read: Rows in the export.
        test_rows_ignored: Rows whose submitter is test data. They are left out of every
            other count.
        rows_without_documents: Rows that list no files.
        unrecognised_submitters: Submitter as written to the number of rows that have it,
            for submitters in neither the department nor the ALB list.
        unreadable_dates: Date text as written to the number of rows that have it, for rows
            that list files and have a date that could not be read. An empty date is not
            counted: it is in `listed_without_date`.
        unmatched_departments: Requested departments that no listed document belongs to.
        listed: Different files the export lists. A file listed by two rows counts once.
        listed_without_date: Listed files with no date, whether it was empty or unreadable.
        chosen: Files picked after the department filter and the limit.
        chosen_not_in_bucket: Chosen files with no object in the bucket.
        chosen_already_labelled: Chosen files in the bucket that already have a label.
        bucket_not_listed: Documents in the bucket that the export does not list.
        new: Sidecars to write where there is no label yet, by sidecar key.
        replacements: Sidecars that would replace a label, by sidecar key.
    """

    rows_read: int
    test_rows_ignored: int
    rows_without_documents: int
    unrecognised_submitters: dict[str, int]
    unreadable_dates: dict[str, int]
    unmatched_departments: list[str]
    listed: int
    listed_without_date: int
    chosen: int
    chosen_not_in_bucket: int
    chosen_already_labelled: int
    bucket_not_listed: int
    new: dict[str, Sidecar]
    replacements: dict[str, Sidecar]

    @property
    def would_write_new(self) -> int:
        """Labels written when nothing is replaced."""
        return len(self.new)

    @property
    def would_write_with_overwrite(self) -> int:
        """Labels written when existing ones are replaced too."""
        return len(self.new) + len(self.replacements)


def _is_document_key(key: str) -> bool:
    """Whether a key in the bucket is a document: not a sidecar and not any other `.json` file."""
    return not is_sidecar_key(key) and not key.lower().endswith(".json")


def plan(
    rows: Iterable[Mapping[str, Any]],
    bucket_keys: Iterable[str],
    *,
    prefix: str,
    limit: int | None = None,
    departments: list[str] | None = None,
) -> SidecarPlan:
    """Work out what labelling the newest documents of an export would do.

    Args:
        rows: The export rows.
        bucket_keys: Every key found under `prefix` in the bucket.
        prefix: Where the documents are, for example `files/`. A file name from the export
            is looked for at `prefix` plus the name.
        limit: Label at most this many documents.
        departments: Label only documents of these departments.

    Returns:
        The counts, and the sidecars to write.
    """
    listed: dict[str, Sidecar] = {}
    rows_read = 0
    rows_without_documents = 0
    test_rows_ignored = 0
    unrecognised: Counter[str] = Counter()
    unreadable: Counter[str] = Counter()

    for row in rows:
        rows_read += 1
        if is_test_row(row):
            test_rows_ignored += 1
            continue
        documents: dict[str, Sidecar] = documents_for_row(row)
        if not documents:
            rows_without_documents += 1
        elif (date_text := unreadable_date(row)) is not None:
            unreadable[date_text] += 1
        if (submitter := unrecognised_submitter(row)) is not None:
            unrecognised[submitter] += 1
        listed.update(documents)

    keys = set(bucket_keys)
    labels = {key for key in keys if is_sidecar_key(key)}
    bucket_documents = {key for key in keys if _is_document_key(key)}

    chosen: dict[str, Sidecar] = choose_documents(listed, limit, departments)

    chosen_not_in_bucket = 0
    chosen_already_labelled = 0
    new: dict[str, Sidecar] = {}
    replacements: dict[str, Sidecar] = {}
    for file_name, sidecar in chosen.items():
        document_key = prefix + file_name
        if document_key not in bucket_documents:
            chosen_not_in_bucket += 1
            continue
        label_key = sidecar_key(document_key)
        if label_key in labels:
            chosen_already_labelled += 1
            replacements[label_key] = sidecar
        else:
            new[label_key] = sidecar

    return SidecarPlan(
        rows_read=rows_read,
        test_rows_ignored=test_rows_ignored,
        rows_without_documents=rows_without_documents,
        unrecognised_submitters=dict(unrecognised),
        unreadable_dates=dict(unreadable),
        unmatched_departments=[] if departments is None else unmatched_departments(listed, departments),
        listed=len(listed),
        listed_without_date=sum(1 for sidecar in listed.values() if sidecar.date is None),
        chosen=len(chosen),
        chosen_not_in_bucket=chosen_not_in_bucket,
        chosen_already_labelled=chosen_already_labelled,
        bucket_not_listed=len(bucket_documents - {prefix + name for name in listed}),
        new=new,
        replacements=replacements,
    )
