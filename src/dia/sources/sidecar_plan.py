"""Work out which sidecars the GATS exports would produce, given what is in the bucket.

Pure code: it takes the export rows, the keys found in the bucket and a function that reads
existing labels, and returns counts and the sidecars to write. It does no S3 work itself and
writes nothing.

Every document in the bucket gets one outcome:

- the export lists the file: a full label from the export row;
- it is not listed, and its old label names a case the exports have: a full label rebuilt from
  that case's row;
- it is not listed, and its case is not in the exports: the old label is kept, or fixed if it
  is in the old script's format, or left alone if it cannot be fixed;
- it is not listed and has no label: a label with only `document_type` for the file types
  the text stage reads, and nothing yet for the others.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from dia.sources.definitions import SOURCES
from dia.sources.gats_sidecars import (
    SOURCE_NAME,
    choose_documents,
    documents_for_row,
    fix_old_label,
    is_test_row,
    old_label_spend_id,
    row_sidecar,
    unmatched_departments,
    unreadable_date,
    unrecognised_submitter,
)
from dia.sources.sidecar import Sidecar, SidecarError, from_json, is_sidecar_key, sidecar_key

# The file types the text stage reads. Other types get no label of their own until a step reads them.
BASIC_LABEL_EXTENSIONS = (".pdf", ".docx")


class Outcome(StrEnum):
    """What a document gets."""

    FROM_EXPORT = "from_export"
    REBUILT_FROM_CASE = "rebuilt_from_case"
    OLD_LABEL_KEPT = "old_label_kept"
    OLD_LABEL_FIXED = "old_label_fixed"
    OLD_LABEL_UNFIXABLE = "old_label_unfixable"
    BASIC_LABEL = "basic_label"
    WAITING = "waiting_for_new_step"


# What a document gets: the outcome, and the sidecar to write (none when there is nothing to write).
_Target = tuple[Outcome, Sidecar | None]


@dataclass(frozen=True)
class SidecarPlan:
    """What a run would do. Each count is of documents unless it says rows.

    Attributes:
        rows_read: Rows in the exports.
        test_rows_ignored: Rows whose submitter is test data. They are left out of every
            other count.
        rows_without_documents: Rows that list no files.
        unrecognised_submitters: Submitter as written to the number of rows that have it,
            for submitters in neither the department nor the ALB list.
        unreadable_dates: Date text as written to the number of rows that have it, for rows
            that list files and have a date that could not be read. An empty date is not
            counted: it is in `listed_without_date`.
        unmatched_departments: Requested departments that no listed document belongs to.
        listed: Different files the exports list. A file listed by two rows counts once.
        listed_without_date: Listed files with no date, whether it was empty or unreadable.
        chosen: Listed files picked after the department filter and the limit.
        not_in_bucket: Chosen files with no object in the bucket, as document keys.
        chosen_already_labelled: Chosen files in the bucket that already have a label.
        bucket_not_listed: Documents in the bucket that the exports do not list.
        outside_run: Bucket documents this run leaves alone, because a limit or departments
            were given and so only the chosen files are labelled.
        outcomes: What each document in this run gets, by document key.
        unchanged: Documents whose label already holds what they would get.
        new: Sidecars to write where there is no label yet, by sidecar key.
        replacements: Sidecars that would replace a label that holds something different.
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
    not_in_bucket: list[str]
    chosen_already_labelled: int
    bucket_not_listed: int
    outside_run: int
    outcomes: dict[str, Outcome]
    unchanged: int
    new: dict[str, Sidecar]
    replacements: dict[str, Sidecar]

    @property
    def chosen_not_in_bucket(self) -> int:
        """How many chosen files have no object in the bucket."""
        return len(self.not_in_bucket)

    @property
    def would_write_new(self) -> int:
        """Labels written when nothing is replaced."""
        return len(self.new)

    @property
    def would_write_with_overwrite(self) -> int:
        """Labels written when labels that hold something different are replaced too."""
        return len(self.new) + len(self.replacements)

    def count(self, outcome: Outcome) -> int:
        """How many documents got this outcome."""
        return sum(1 for value in self.outcomes.values() if value is outcome)


def _is_document_key(key: str) -> bool:
    """Whether a key in the bucket is a document: not a sidecar and not any other `.json` file."""
    return not is_sidecar_key(key) and not key.lower().endswith(".json")


def _classify_old_label(text: str | None, cases: Mapping[str, Sidecar]) -> _Target:
    """Decide what a document with an existing label, that no export lists, gets."""
    if text is None:
        return Outcome.OLD_LABEL_UNFIXABLE, None

    case = cases.get(old_label_spend_id(text) or "")
    if case is not None:
        return Outcome.REBUILT_FROM_CASE, case

    try:
        return Outcome.OLD_LABEL_KEPT, from_json(text)
    except SidecarError:
        pass
    try:
        return Outcome.OLD_LABEL_FIXED, fix_old_label(text)
    except SidecarError:
        return Outcome.OLD_LABEL_UNFIXABLE, None


@dataclass(frozen=True)
class _ExportRows:
    """What reading the export rows found. See `SidecarPlan` for what each field means."""

    rows_read: int
    test_rows_ignored: int
    rows_without_documents: int
    unrecognised: Counter[str]
    unreadable: Counter[str]
    listed: dict[str, Sidecar]
    cases: dict[str, Sidecar]


def _read_export_rows(rows: Iterable[Mapping[str, Any]]) -> _ExportRows:
    """Go through the rows once: count the oddities, and gather the listed files and the cases by spend ID."""
    listed: dict[str, Sidecar] = {}
    cases: dict[str, Sidecar] = {}
    rows_read = 0
    test_rows_ignored = 0
    rows_without_documents = 0
    unrecognised: Counter[str] = Counter()
    unreadable: Counter[str] = Counter()

    for row in rows:
        rows_read += 1
        if is_test_row(row):
            test_rows_ignored += 1
            continue
        case = row_sidecar(row)
        documents = documents_for_row(row, case)
        if not documents:
            rows_without_documents += 1
        elif (date_text := unreadable_date(row)) is not None:
            unreadable[date_text] += 1
        if (submitter := unrecognised_submitter(row)) is not None:
            unrecognised[submitter] += 1
        if case.spend_id:
            cases[case.spend_id] = case
        listed.update(documents)

    return _ExportRows(
        rows_read=rows_read,
        test_rows_ignored=test_rows_ignored,
        rows_without_documents=rows_without_documents,
        unrecognised=unrecognised,
        unreadable=unreadable,
        listed=listed,
        cases=cases,
    )


def _targets_from_export(
    chosen: Mapping[str, Sidecar], bucket_documents: set[str], prefix: str
) -> tuple[dict[str, _Target], list[str]]:
    """Match the chosen files to objects in the bucket.

    Returns:
        The target of each chosen file that is in the bucket, by document key, and the document
        keys of those that are not.
    """
    targets: dict[str, _Target] = {}
    not_in_bucket: list[str] = []
    for file_name, sidecar in chosen.items():
        document_key = prefix + file_name
        if document_key in bucket_documents:
            targets[document_key] = (Outcome.FROM_EXPORT, sidecar)
        else:
            not_in_bucket.append(document_key)
    return targets, not_in_bucket


def _read_old_labels(
    document_keys: Iterable[str],
    labels: set[str],
    read_labels: Callable[[list[str]], Mapping[str, str]] | None,
) -> dict[str, str]:
    """Read the labels that exist for these documents, by sidecar key. Reads nothing if there is no reader."""
    wanted = sorted(sidecar_key(key) for key in document_keys if sidecar_key(key) in labels)
    return dict(read_labels(wanted)) if read_labels is not None and wanted else {}


def _targets_for_unlisted(
    unlisted: Iterable[str], labels: set[str], old_labels: Mapping[str, str], cases: Mapping[str, Sidecar]
) -> dict[str, _Target]:
    """Decide what each document no export lists gets, by document key."""
    targets: dict[str, _Target] = {}
    for document_key in sorted(unlisted):
        label_key = sidecar_key(document_key)
        if label_key in labels:
            targets[document_key] = _classify_old_label(old_labels.get(label_key), cases)
        elif document_key.lower().endswith(BASIC_LABEL_EXTENSIONS):
            targets[document_key] = (Outcome.BASIC_LABEL, Sidecar(document_type=SOURCES[SOURCE_NAME].document_type))
        else:
            targets[document_key] = (Outcome.WAITING, None)
    return targets


def _split_writes(
    targets: Mapping[str, _Target], labels: set[str], old_labels: Mapping[str, str]
) -> tuple[dict[str, Sidecar], dict[str, Sidecar], int]:
    """Sort the targets into labels to create, labels to replace, and labels that already hold the target.

    Returns:
        The new sidecars and the replacements, each by sidecar key, and the count unchanged.
    """
    new: dict[str, Sidecar] = {}
    replacements: dict[str, Sidecar] = {}
    unchanged = 0
    for document_key, (_, target) in targets.items():
        if target is None:
            continue
        label_key = sidecar_key(document_key)
        if label_key not in labels:
            new[label_key] = target
            continue
        try:
            current = from_json(old_labels[label_key]) if label_key in old_labels else None
        except SidecarError:
            current = None
        if current == target:
            unchanged += 1
        else:
            replacements[label_key] = target
    return new, replacements, unchanged


def plan(
    rows: Iterable[Mapping[str, Any]],
    bucket_keys: Iterable[str],
    *,
    prefix: str,
    read_labels: Callable[[list[str]], Mapping[str, str]] | None = None,
    limit: int | None = None,
    departments: list[str] | None = None,
) -> SidecarPlan:
    """Work out what labelling the documents of the exports would do.

    With no limit and no departments, every document in the bucket is in the run. With either,
    only the chosen listed files are, and the rest are left alone.

    Args:
        rows: The export rows, from every export in the order they were read. When two rows
            list the same file, the later one wins.
        bucket_keys: Every key found under `prefix` in the bucket.
        prefix: Where the documents are, for example `files/`. A file name from the export
            is looked for at `prefix` plus the name.
        read_labels: Reads existing labels. Given the keys wanted, returns the text of each.
        limit: Label at most this many listed documents, newest first.
        departments: Label only listed documents of these departments.

    Returns:
        The counts, and the sidecars to write.
    """
    export = _read_export_rows(rows)

    keys = set(bucket_keys)
    labels = {key for key in keys if is_sidecar_key(key)}
    bucket_documents = {key for key in keys if _is_document_key(key)}
    restricted = limit is not None or departments is not None

    chosen = choose_documents(export.listed, limit, departments)
    targets, not_in_bucket = _targets_from_export(chosen, bucket_documents, prefix)

    unlisted = bucket_documents - {prefix + name for name in export.listed}
    in_run = set(targets) if restricted else bucket_documents
    old_labels = _read_old_labels(in_run, labels, read_labels)

    if not restricted:
        targets.update(_targets_for_unlisted(unlisted, labels, old_labels, export.cases))

    new, replacements, unchanged = _split_writes(targets, labels, old_labels)

    return SidecarPlan(
        rows_read=export.rows_read,
        test_rows_ignored=export.test_rows_ignored,
        rows_without_documents=export.rows_without_documents,
        unrecognised_submitters=dict(export.unrecognised),
        unreadable_dates=dict(export.unreadable),
        unmatched_departments=[] if departments is None else unmatched_departments(export.listed, departments),
        listed=len(export.listed),
        listed_without_date=sum(1 for sidecar in export.listed.values() if sidecar.date is None),
        chosen=len(chosen),
        not_in_bucket=not_in_bucket,
        chosen_already_labelled=sum(
            1 for key, (outcome, _) in targets.items() if outcome is Outcome.FROM_EXPORT and sidecar_key(key) in labels
        ),
        bucket_not_listed=len(unlisted),
        outside_run=len(bucket_documents - set(targets)) if restricted else 0,
        outcomes={key: outcome for key, (outcome, _) in targets.items()},
        unchanged=unchanged,
        new=new,
        replacements=replacements,
    )
