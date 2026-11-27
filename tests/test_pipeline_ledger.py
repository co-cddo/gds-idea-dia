"""Tests for dia.pipeline_ledger: the records, and the DynamoDB and local ledgers behind one interface."""

import datetime as dt

import boto3
import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment
from moto import mock_aws

from dia.naming import Names
from dia.pipeline_ledger import (
    DynamoLedger,
    LedgerError,
    LedgerRecord,
    LocalLedger,
    Stage,
    Status,
    document_version,
    open_ledger,
    pending,
)

SOURCE = "gats_business_cases"
V1 = "2026-11-24T10:15:00Z"
V2 = "2026-12-01T09:00:00Z"


def _done(key="files/a.pdf", version=V1, *, source=SOURCE, stage=Stage.TEXT, output="s3://out/a.json"):
    return LedgerRecord.done(source, stage, key, version, code_version="1.2.3", output_location=output)


def _failed(key="files/a.pdf", version=V1, *, stage=Stage.TEXT):
    return LedgerRecord.failed(SOURCE, stage, key, version, code_version="1.2.3", reason="no text found")


NAMES = Names(DeploymentEnvironment.DEVELOPMENT)


@pytest.fixture
def table():
    """An empty ledger table, as the storage stack creates it."""
    with mock_aws():
        boto3.client("dynamodb", region_name="eu-west-2").create_table(
            TableName="dia-pipeline-ledger-dev",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield boto3.resource("dynamodb", region_name="eu-west-2").Table("dia-pipeline-ledger-dev")


@pytest.fixture(params=["dynamodb", "local"])
def ledger(request, tmp_path, table):
    """The same tests run against both backends."""
    if request.param == "local":
        return LocalLedger(tmp_path / "ledger")
    return DynamoLedger(table)


# --- both ledgers ---


def test_a_source_and_stage_with_nothing_recorded_has_no_records(ledger):
    assert ledger.records(SOURCE, Stage.TEXT) == []


def test_a_done_record_comes_back_as_it_was_saved(ledger):
    saved = _done()
    ledger.record([saved])
    assert ledger.records(SOURCE, Stage.TEXT) == [saved]


def test_a_failed_record_keeps_its_reason(ledger):
    ledger.record([_failed()])
    (found,) = ledger.records(SOURCE, Stage.TEXT)
    assert (found.status, found.reason, found.output_location) == (Status.FAILED, "no text found", None)


def test_recording_a_document_and_version_again_replaces_the_earlier_record(ledger):
    ledger.record([_failed()])
    ledger.record([_done()])
    (found,) = ledger.records(SOURCE, Stage.TEXT)
    assert found.status is Status.DONE


def test_records_saved_in_separate_calls_are_all_kept(ledger):
    ledger.record([_done("files/a.pdf")])
    ledger.record([_done("files/b.pdf")])
    assert {r.document_key for r in ledger.records(SOURCE, Stage.TEXT)} == {"files/a.pdf", "files/b.pdf"}


def test_a_new_version_of_a_document_is_a_separate_record_and_the_old_one_stays(ledger):
    ledger.record([_done(version=V1), _done(version=V2)])
    assert {record.version for record in ledger.records(SOURCE, Stage.TEXT)} == {V1, V2}


def test_records_of_another_stage_or_source_are_not_returned(ledger):
    ledger.record([_done(), _done(stage=Stage.CHUNK), _done(source="sr25_bids")])
    assert [r.stage for r in ledger.records(SOURCE, Stage.TEXT)] == [Stage.TEXT]


def test_many_records_are_all_saved_and_returned(ledger):
    ledger.record([_done(key=f"files/{n}.pdf") for n in range(60)])
    assert len(ledger.records(SOURCE, Stage.TEXT)) == 60


# --- DynamoDB: reading in pages ---


def test_dynamodb_reads_every_page_of_a_long_partition():
    class TwoPages:
        def __init__(self):
            self.calls = []

        def query(self, **kwargs):
            self.calls.append(kwargs)
            if "ExclusiveStartKey" not in kwargs:
                return {"Items": [_item("files/a.pdf")], "LastEvaluatedKey": {"pk": "x", "sk": "y"}}
            return {"Items": [_item("files/b.pdf")]}

    def _item(key):
        from dia.pipeline_ledger import _to_item

        return _to_item(_done(key=key))

    table = TwoPages()
    records = DynamoLedger(table).records(SOURCE, Stage.TEXT)

    assert [r.document_key for r in records] == ["files/a.pdf", "files/b.pdf"]
    assert table.calls[1]["ExclusiveStartKey"] == {"pk": "x", "sk": "y"}
    assert all(call["ConsistentRead"] for call in table.calls)


# --- local ledger ---


def test_a_local_file_that_is_not_a_ledger_is_an_error_not_an_empty_ledger(tmp_path):
    ledger = LocalLedger(tmp_path)
    ledger.record([_done()])
    (path,) = tmp_path.glob("*.json")
    path.write_text("{not json")

    with pytest.raises(LedgerError):
        ledger.records(SOURCE, Stage.TEXT)


def test_a_local_save_leaves_no_temporary_file(tmp_path):
    LocalLedger(tmp_path).record([_done()])
    assert [p.suffix for p in tmp_path.iterdir()] == [".json"]


# --- pending ---


def test_a_document_done_at_its_current_version_is_skipped_and_a_changed_one_is_not():
    versions = {"files/a.pdf": V2, "files/b.pdf": V1, "files/c.pdf": V1}
    records = [_done("files/a.pdf", V1), _done("files/b.pdf", V1)]

    assert pending(versions, records) == ["files/a.pdf", "files/c.pdf"]


def test_a_failed_document_is_skipped_unless_retrying_failed():
    versions = {"files/a.pdf": V1}
    assert pending(versions, [_failed()]) == []
    assert pending(versions, [_failed()], retry_failed=True) == ["files/a.pdf"]


def test_a_failed_document_that_changed_is_pending_again_without_retry_failed():
    assert pending({"files/a.pdf": V2}, [_failed(version=V1)]) == ["files/a.pdf"]


# --- records and versions ---


def test_a_failed_record_needs_a_reason_and_a_done_record_has_none():
    with pytest.raises(ValueError, match="reason"):
        LedgerRecord(SOURCE, Stage.TEXT, "k", V1, Status.FAILED, "1")
    with pytest.raises(ValueError, match="no reason"):
        LedgerRecord(SOURCE, Stage.TEXT, "k", V1, Status.DONE, "1", reason="x")


def test_a_document_version_is_the_utc_time_and_needs_a_timezone():
    london = dt.timezone(dt.timedelta(hours=1))
    assert document_version(dt.datetime(2026, 7, 1, 11, 0, 5, tzinfo=london)) == "2026-07-01T10:00:05Z"
    with pytest.raises(ValueError, match="timezone"):
        document_version(dt.datetime(2026, 7, 1, 11, 0, 5))


# --- open_ledger ---


def test_a_remote_run_uses_the_real_table(table, tmp_path):
    ledger = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=True, directory=tmp_path / "local")
    ledger.record([_done()])

    assert len(DynamoLedger(table).records(SOURCE, Stage.TEXT)) == 1
    assert not (tmp_path / "local").exists()


def test_a_local_run_starts_from_a_copy_of_the_real_ledger(table, tmp_path):
    real = DynamoLedger(table)
    saved = _done()
    real.record([saved, _done(stage=Stage.CHUNK), _done(source="other_source")])

    ledger = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, directory=tmp_path)

    assert isinstance(ledger, LocalLedger)
    assert ledger.records(SOURCE, Stage.TEXT) == [saved]
    assert ledger.records(SOURCE, Stage.CHUNK) == []
    assert ledger.records("other_source", Stage.TEXT) == []


def test_a_local_run_never_changes_the_real_ledger(table, tmp_path):
    real = DynamoLedger(table)
    real.record([_done("files/a.pdf")])

    ledger = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, directory=tmp_path)
    ledger.record([_done("files/b.pdf"), _failed("files/a.pdf", V2)])

    assert [r.document_key for r in real.records(SOURCE, Stage.TEXT)] == ["files/a.pdf"]


def test_ignoring_the_ledger_starts_a_local_run_empty_and_leaves_the_real_one_alone(table, tmp_path):
    real = DynamoLedger(table)
    real.record([_done()])

    ledger = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, ignore_ledger=True, directory=tmp_path)

    assert ledger.records(SOURCE, Stage.TEXT) == []
    assert pending({"files/a.pdf": V1}, ledger.records(SOURCE, Stage.TEXT)) == ["files/a.pdf"]
    assert len(real.records(SOURCE, Stage.TEXT)) == 1


def test_a_second_local_run_replaces_the_first_ones_copy(table, tmp_path):
    first = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, directory=tmp_path)
    first.record([_done("files/only-local.pdf")])

    second = open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, directory=tmp_path)

    assert second.records(SOURCE, Stage.TEXT) == []


def test_a_copy_for_one_stage_leaves_the_local_copy_of_another_alone(table, tmp_path):
    other = open_ledger(SOURCE, Stage.CHUNK, names=NAMES, remote=False, directory=tmp_path)
    other.record([_done(stage=Stage.CHUNK)])

    open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=False, directory=tmp_path)

    assert len(LocalLedger(tmp_path).records(SOURCE, Stage.CHUNK)) == 1


def test_ignoring_the_ledger_is_refused_for_a_remote_run(table, tmp_path):
    with pytest.raises(ValueError, match="local run"):
        open_ledger(SOURCE, Stage.TEXT, names=NAMES, remote=True, ignore_ledger=True, directory=tmp_path)
