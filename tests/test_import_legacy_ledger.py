"""Tests for scripts/import_legacy_ledger.py: marking the old pipeline's documents as done."""

import json
from unittest.mock import patch

import boto3
import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment
from moto import mock_aws

from dia.naming import Names
from dia.pipeline_ledger import LedgerRecord, LocalLedger, Stage, Status
from scripts.import_legacy_ledger import (
    LEGACY_CODE_VERSION,
    SOURCE,
    list_versions,
    main,
    read_mapping,
    run,
    write_not_found,
)

PREFIX = "files/"
VERSIONS = {
    "files/a.pdf": "2026-11-01T10:00:00Z",
    "files/b.docx": "2026-11-02T10:00:00Z",
    "files/new.pdf": "2026-11-03T10:00:00Z",
}
MAPPING = {"1": "a.pdf", "2": "b.docx", "3": "gone.pdf"}


def _run(ledger, *, write=False, answer=True, mapping=MAPPING):
    return run(mapping, VERSIONS, ledger, prefix=PREFIX, write=write, confirm=lambda question: answer)


@pytest.fixture
def ledger(tmp_path):
    return LocalLedger(tmp_path / "ledger")


def test_a_dry_run_counts_what_it_would_write_and_writes_nothing(ledger):
    result = _run(ledger)

    assert (result.entries, result.found, result.not_found) == (3, 2, ["gone.pdf"])
    assert (result.to_write, result.already_present, result.written) == (2 * len(Stage), 0, 0)
    assert all(ledger.records(SOURCE, stage) == [] for stage in Stage)


def test_each_found_document_is_done_for_every_stage_at_the_version_it_has_now(ledger):
    _run(ledger, write=True)

    for stage in Stage:
        records = {r.document_key: r for r in ledger.records(SOURCE, stage)}
        assert set(records) == {"files/a.pdf", "files/b.docx"}
        assert records["files/a.pdf"].version == VERSIONS["files/a.pdf"]
        assert records["files/a.pdf"].status is Status.DONE
        assert records["files/a.pdf"].code_version == LEGACY_CODE_VERSION


def test_a_no_at_the_question_writes_nothing(ledger):
    result = _run(ledger, write=True, answer=False)
    assert result.written == 0
    assert ledger.records(SOURCE, Stage.TEXT) == []


def test_a_second_run_finds_nothing_to_write(ledger):
    _run(ledger, write=True)
    again = _run(ledger, write=True)
    assert (again.to_write, again.already_present, again.written) == (0, 2 * len(Stage), 0)


def test_a_record_that_is_already_there_is_left_alone(ledger):
    existing = LedgerRecord.done(
        SOURCE, Stage.TEXT, "files/a.pdf", VERSIONS["files/a.pdf"], code_version="2.0", output_location="s3://x"
    )
    ledger.record([existing])

    _run(ledger, write=True)

    assert existing in ledger.records(SOURCE, Stage.TEXT)
    assert len(ledger.records(SOURCE, Stage.TEXT)) == 2


def test_the_old_ledger_file_must_be_a_map_of_text_to_text(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"1": "a.pdf"}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"1": 7}))

    assert read_mapping(good) == {"1": "a.pdf"}
    with pytest.raises(ValueError, match="not a map"):
        read_mapping(bad)


def test_versions_come_from_the_objects_last_modified_time():
    with mock_aws():
        s3 = boto3.client("s3", region_name="eu-west-2")
        s3.create_bucket(Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        s3.put_object(Bucket="test-bucket", Key="files/a.pdf", Body=b"x")
        s3.put_object(Bucket="test-bucket", Key="other/c.pdf", Body=b"x")

        versions = list_versions(s3, "test-bucket", "files/")

    assert list(versions) == ["files/a.pdf"]
    assert versions["files/a.pdf"].endswith("Z") and "T" in versions["files/a.pdf"]


def test_the_names_that_are_not_in_the_bucket_are_saved_on_this_machine(tmp_path):
    path = tmp_path / "out" / "not-found.csv"
    write_not_found(["gone.pdf"], path)
    assert path.read_text().splitlines() == ["file_name", "gone.pdf"]


def test_it_refuses_to_run_in_prod_before_reading_anything(tmp_path):
    mapping = tmp_path / "m.json"
    mapping.write_text("{}")
    with (
        patch("scripts.import_legacy_ledger.current_names", return_value=Names(DeploymentEnvironment.PRODUCTION)),
        patch("scripts.import_legacy_ledger.source_s3_client") as client,
    ):
        assert main([str(mapping), "--write", "--yes"]) == 1

    client.assert_not_called()
