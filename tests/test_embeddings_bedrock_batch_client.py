"""Tests for dia.embeddings.bedrock_batch_client."""

import json

import boto3
import pytest
from moto import mock_aws

from dia.embeddings.bedrock_batch_client import (
    BEDROCK_MIN_BATCH_SIZE,
    BatchEmbeddingJobError,
    BatchEmbeddingRequest,
    BatchEmbeddingResult,
    _download_job_results,
    _Job,
    _reorder_to_match_requests,
    _split_into_jobs,
    _submit_job,
    _wait_for_job,
    submit_and_await_batch_embeddings,
)

BUCKET = "test-batch-embeddings-bucket"
ROLE_ARN = "arn:aws:iam::123456789012:role/batch-embedding-role"
MODEL_ID = "amazon.titan-embed-text-v2:0"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        yield client


class FakeBedrockControlClient:
    """Records create_model_invocation_job calls and lets tests script the
    get_model_invocation_job status sequence per job. Default behaviour
    (no explicit configuration) is every job immediately Completed - the
    common case, so most tests don't need to configure anything."""

    def __init__(self) -> None:
        self.created_jobs: list[dict] = []
        self._counter = 0
        self._status_sequences: dict[str, list[str]] = {}
        self._status_index: dict[str, int] = {}
        self._messages: dict[str, str] = {}

    def create_model_invocation_job(self, **kwargs) -> dict:
        self._counter += 1
        job_arn = f"arn:aws:bedrock:eu-west-2:123456789012:model-invocation-job/job-{self._counter}"
        self.created_jobs.append({**kwargs, "jobArn": job_arn})
        return {"jobArn": job_arn}

    def get_model_invocation_job(self, jobIdentifier: str) -> dict:  # noqa: N803 (matches boto3's own kwarg name)
        statuses = self._status_sequences.get(jobIdentifier, ["Completed"])
        idx = self._status_index.get(jobIdentifier, 0)
        status = statuses[min(idx, len(statuses) - 1)]
        self._status_index[jobIdentifier] = idx + 1
        result = {"status": status}
        if jobIdentifier in self._messages:
            result["message"] = self._messages[jobIdentifier]
        return result

    def set_status_sequence(self, job_arn: str, statuses: list[str]) -> None:
        self._status_sequences[job_arn] = statuses

    def set_message(self, job_arn: str, message: str) -> None:
        self._messages[job_arn] = message


# --- _split_into_jobs ---


def test_split_into_jobs_no_split_when_under_limits():
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(10)]
    groups = _split_into_jobs(requests, max_records_per_job=100, max_bytes_per_job=1_000_000)
    assert len(groups) == 1
    assert len(groups[0]) == 10


def test_split_into_jobs_splits_by_record_count():
    """min_records_per_job=1: this test is about the count-based chunking
    mechanics specifically, independent of the real Bedrock minimum -
    rebalancing behaviour has its own tests below."""
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(7)]
    groups = _split_into_jobs(requests, max_records_per_job=3, max_bytes_per_job=1_000_000, min_records_per_job=1)
    assert [len(g) for g in groups] == [3, 3, 1]


def test_split_into_jobs_splits_by_byte_size():
    long_text = "x" * 100
    requests = [BatchEmbeddingRequest(token=str(i), text=long_text) for i in range(5)]
    # each record ~= 164 bytes (100 chars + 64 overhead); cap at 200 bytes -> 1 per group
    groups = _split_into_jobs(requests, max_records_per_job=100, max_bytes_per_job=200)
    assert all(len(g) == 1 for g in groups)
    assert len(groups) == 5


def test_split_into_jobs_empty_input():
    assert _split_into_jobs([], max_records_per_job=100, max_bytes_per_job=1_000_000) == []


def test_split_into_jobs_rebalances_undersized_tail():
    """120 requests at max_records_per_job=100 naively gives [100, 20] -
    the 20 would be rejected by the real Bedrock API. Rebalanced to
    [60, 60] instead - both clear a minimum of 50."""
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(120)]
    groups = _split_into_jobs(requests, max_records_per_job=100, max_bytes_per_job=1_000_000, min_records_per_job=50)
    assert [len(g) for g in groups] == [60, 60]


def test_split_into_jobs_rebalances_with_multiple_full_groups():
    """320 requests at max_records_per_job=100 naively gives
    [100, 100, 100, 20] - rebalances the last two groups to [60, 60],
    giving [100, 100, 60, 60]."""
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(320)]
    groups = _split_into_jobs(requests, max_records_per_job=100, max_bytes_per_job=1_000_000, min_records_per_job=50)
    assert [len(g) for g in groups] == [100, 100, 60, 60]


def test_split_into_jobs_no_rebalance_when_tail_already_at_minimum():
    """300 requests at max_records_per_job=100 naively gives [100, 100, 100]
    - no undersized tail, nothing to rebalance."""
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(300)]
    groups = _split_into_jobs(requests, max_records_per_job=100, max_bytes_per_job=1_000_000, min_records_per_job=50)
    assert [len(g) for g in groups] == [100, 100, 100]


def test_split_into_jobs_rebalances_at_real_bedrock_minimum():
    """Same shape as test_split_into_jobs_rebalances_with_multiple_full_groups,
    scaled 2x to exercise the actual BEDROCK_MIN_BATCH_SIZE (100) rather
    than an illustrative smaller minimum: 640 requests at
    max_records_per_job=200 naively gives [200, 200, 200, 40], rebalanced
    to [200, 200, 120, 120]."""
    requests = [BatchEmbeddingRequest(token=str(i), text="hello") for i in range(640)]
    groups = _split_into_jobs(requests, max_records_per_job=200, max_bytes_per_job=1_000_000)
    assert [len(g) for g in groups] == [200, 200, 120, 120]


# --- _submit_job ---


def test_submit_job_uploads_jsonl_to_s3(s3_client):
    requests = [
        BatchEmbeddingRequest(token="doc-a::0", text="first"),
        BatchEmbeddingRequest(token="doc-a::1", text="second"),
    ]
    bedrock = FakeBedrockControlClient()

    job = _submit_job(
        requests,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="test-prefix",
        bedrock_client=bedrock,
        s3_client=s3_client,
    )

    body = s3_client.get_object(Bucket=BUCKET, Key=job.input_key)["Body"].read().decode("utf-8")
    lines = [json.loads(line) for line in body.splitlines()]
    assert lines == [
        {"recordId": "0", "modelInput": {"inputText": "first"}},
        {"recordId": "1", "modelInput": {"inputText": "second"}},
    ]


def test_submit_job_builds_record_id_to_token_map(s3_client):
    requests = [
        BatchEmbeddingRequest(token="doc-a::0", text="first"),
        BatchEmbeddingRequest(token="doc-b::5", text="second"),
    ]
    bedrock = FakeBedrockControlClient()

    job = _submit_job(
        requests,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="p",
        bedrock_client=bedrock,
        s3_client=s3_client,
    )

    assert job.record_id_to_token == {"0": "doc-a::0", "1": "doc-b::5"}


def test_submit_job_calls_create_model_invocation_job_with_correct_params(s3_client):
    requests = [BatchEmbeddingRequest(token="t", text="hello")]
    bedrock = FakeBedrockControlClient()

    job = _submit_job(
        requests,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="p",
        bedrock_client=bedrock,
        s3_client=s3_client,
    )

    (call,) = bedrock.created_jobs
    assert call["roleArn"] == ROLE_ARN
    assert call["modelId"] == MODEL_ID
    assert call["inputDataConfig"]["s3InputDataConfig"]["s3Uri"] == f"s3://{BUCKET}/{job.input_key}"
    assert call["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"] == f"s3://{BUCKET}/{job.output_prefix}"


# --- _wait_for_job ---


def test_wait_for_job_returns_immediately_completed():
    bedrock = FakeBedrockControlClient()
    job = _Job(job_arn="job-1", input_key="k", output_prefix="p/")

    status = _wait_for_job(job, bedrock_client=bedrock, poll_interval_seconds=0)

    assert status == "Completed"


def test_wait_for_job_polls_through_intermediate_statuses():
    bedrock = FakeBedrockControlClient()
    bedrock.set_status_sequence("job-1", ["Submitted", "Validating", "InProgress", "Completed"])
    job = _Job(job_arn="job-1", input_key="k", output_prefix="p/")

    status = _wait_for_job(job, bedrock_client=bedrock, poll_interval_seconds=0)

    assert status == "Completed"


def test_wait_for_job_accepts_partially_completed():
    bedrock = FakeBedrockControlClient()
    bedrock.set_status_sequence("job-1", ["InProgress", "PartiallyCompleted"])
    job = _Job(job_arn="job-1", input_key="k", output_prefix="p/")

    status = _wait_for_job(job, bedrock_client=bedrock, poll_interval_seconds=0)

    assert status == "PartiallyCompleted"


@pytest.mark.parametrize("terminal_status", ["Failed", "Stopped", "Expired"])
def test_wait_for_job_raises_on_non_success_terminal_status(terminal_status):
    bedrock = FakeBedrockControlClient()
    bedrock.set_status_sequence("job-1", [terminal_status])
    bedrock.set_message("job-1", "something went wrong")
    job = _Job(job_arn="job-1", input_key="k", output_prefix="p/")

    with pytest.raises(BatchEmbeddingJobError, match="something went wrong"):
        _wait_for_job(job, bedrock_client=bedrock, poll_interval_seconds=0)


# --- _download_job_results ---


def test_download_job_results_parses_output(s3_client):
    output_prefix = "p/job-1/output/"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=f"{output_prefix}input.jsonl.out",
        Body=b'{"recordId": "0", "modelOutput": {"embedding": [0.1, 0.2]}}\n'
        b'{"recordId": "1", "modelOutput": {"embedding": [0.3, 0.4]}}\n',
    )
    job = _Job(
        job_arn="job-1", input_key="k", output_prefix=output_prefix, record_id_to_token={"0": "tok-a", "1": "tok-b"}
    )

    results = _download_job_results(job, bucket=BUCKET, s3_client=s3_client)

    assert sorted(results, key=lambda r: r.token) == [
        BatchEmbeddingResult(token="tok-a", embedding=[0.1, 0.2]),
        BatchEmbeddingResult(token="tok-b", embedding=[0.3, 0.4]),
    ]


def test_download_job_results_excludes_manifest(s3_client):
    output_prefix = "p/job-1/output/"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=f"{output_prefix}input.jsonl.out",
        Body=b'{"recordId": "0", "modelOutput": {"embedding": [0.1]}}\n',
    )
    s3_client.put_object(
        Bucket=BUCKET,
        Key=f"{output_prefix}manifest.json.out",
        Body=b'{"totalRecordCount": 1, "recordId": "should-not-be-parsed"}',
    )
    job = _Job(job_arn="job-1", input_key="k", output_prefix=output_prefix, record_id_to_token={"0": "tok-a"})

    results = _download_job_results(job, bucket=BUCKET, s3_client=s3_client)

    assert len(results) == 1
    assert results[0].token == "tok-a"


def test_download_job_results_captures_per_record_errors(s3_client):
    output_prefix = "p/job-1/output/"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=f"{output_prefix}input.jsonl.out",
        Body=b'{"recordId": "0", "error": {"message": "boom"}}\n',
    )
    job = _Job(job_arn="job-1", input_key="k", output_prefix=output_prefix, record_id_to_token={"0": "tok-a"})

    results = _download_job_results(job, bucket=BUCKET, s3_client=s3_client)

    assert results[0].embedding is None
    assert "boom" in results[0].error


def test_download_job_results_skips_unrecognised_record_id(s3_client):
    output_prefix = "p/job-1/output/"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=f"{output_prefix}input.jsonl.out",
        Body=b'{"recordId": "999", "modelOutput": {"embedding": [0.1]}}\n',
    )
    job = _Job(job_arn="job-1", input_key="k", output_prefix=output_prefix, record_id_to_token={"0": "tok-a"})

    results = _download_job_results(job, bucket=BUCKET, s3_client=s3_client)

    assert results == []


# --- _reorder_to_match_requests ---


def test_reorder_to_match_requests_reorders():
    requests = [BatchEmbeddingRequest(token="a", text="x"), BatchEmbeddingRequest(token="b", text="y")]
    results = [BatchEmbeddingResult(token="b", embedding=[2]), BatchEmbeddingResult(token="a", embedding=[1])]

    reordered = _reorder_to_match_requests(requests, results)

    assert [r.token for r in reordered] == ["a", "b"]
    assert [r.embedding for r in reordered] == [[1], [2]]


def test_reorder_to_match_requests_synthesises_missing_result():
    requests = [BatchEmbeddingRequest(token="a", text="x")]

    reordered = _reorder_to_match_requests(requests, [])

    assert reordered[0].token == "a"
    assert reordered[0].embedding is None
    assert "no output record" in reordered[0].error


# --- submit_and_await_batch_embeddings (end-to-end) ---


def test_submit_and_await_batch_embeddings_below_minimum_raises():
    requests = [BatchEmbeddingRequest(token=str(i), text="x") for i in range(BEDROCK_MIN_BATCH_SIZE - 1)]

    with pytest.raises(ValueError, match="below Bedrock's minimum"):
        submit_and_await_batch_embeddings(requests, model_id=MODEL_ID, role_arn=ROLE_ARN, bucket=BUCKET, key_prefix="p")


def test_submit_and_await_batch_embeddings_rejects_max_records_per_job_too_small():
    """max_records_per_job must be at least 2x the real minimum, or job
    splitting can't guarantee every resulting job is individually valid
    (see _split_into_jobs) - this must be rejected outright, not silently
    produce a job the real Bedrock API would reject."""
    requests = [BatchEmbeddingRequest(token=str(i), text="x") for i in range(300)]

    with pytest.raises(ValueError, match="max_records_per_job=150 is too small"):
        submit_and_await_batch_embeddings(
            requests,
            model_id=MODEL_ID,
            role_arn=ROLE_ARN,
            bucket=BUCKET,
            key_prefix="p",
            max_records_per_job=150,
        )


def test_submit_and_await_batch_embeddings_end_to_end_single_job(s3_client):
    bedrock = FakeBedrockControlClient()
    requests = [BatchEmbeddingRequest(token=f"tok-{i}", text=f"text-{i}") for i in range(BEDROCK_MIN_BATCH_SIZE)]

    # Bedrock never actually runs in this test - the fake immediately reports
    # Completed, so pre-seed the output S3 location the (single) job will use.
    def create_and_seed_output(**kwargs):
        response = FakeBedrockControlClient.create_model_invocation_job(bedrock, **kwargs)
        output_uri = kwargs["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
        output_prefix = output_uri.removeprefix(f"s3://{BUCKET}/")
        body = "\n".join(
            json.dumps({"recordId": str(i), "modelOutput": {"embedding": [float(i)]}}) for i in range(len(requests))
        )
        s3_client.put_object(Bucket=BUCKET, Key=f"{output_prefix}input.jsonl.out", Body=body.encode())
        return response

    bedrock.create_model_invocation_job = create_and_seed_output

    results = submit_and_await_batch_embeddings(
        requests,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="p",
        bedrock_client=bedrock,
        s3_client=s3_client,
        poll_interval_seconds=0,
    )

    assert [r.token for r in results] == [f"tok-{i}" for i in range(BEDROCK_MIN_BATCH_SIZE)]
    assert [r.embedding for r in results] == [[float(i)] for i in range(BEDROCK_MIN_BATCH_SIZE)]


def test_submit_and_await_batch_embeddings_splits_into_multiple_jobs(s3_client):
    bedrock = FakeBedrockControlClient()
    max_records_per_job = 2 * BEDROCK_MIN_BATCH_SIZE
    requests = [BatchEmbeddingRequest(token=f"tok-{i}", text=f"text-{i}") for i in range(max_records_per_job + 20)]

    def create_and_seed_output(**kwargs):
        response = FakeBedrockControlClient.create_model_invocation_job(bedrock, **kwargs)
        output_uri = kwargs["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
        output_prefix = output_uri.removeprefix(f"s3://{BUCKET}/")
        input_uri = kwargs["inputDataConfig"]["s3InputDataConfig"]["s3Uri"]
        input_key = input_uri.removeprefix(f"s3://{BUCKET}/")
        input_body = s3_client.get_object(Bucket=BUCKET, Key=input_key)["Body"].read().decode()
        record_ids = [json.loads(line)["recordId"] for line in input_body.splitlines()]
        body = "\n".join(
            json.dumps({"recordId": rid, "modelOutput": {"embedding": [float(rid)]}}) for rid in record_ids
        )
        s3_client.put_object(Bucket=BUCKET, Key=f"{output_prefix}input.jsonl.out", Body=body.encode())
        return response

    bedrock.create_model_invocation_job = create_and_seed_output

    results = submit_and_await_batch_embeddings(
        requests,
        model_id=MODEL_ID,
        role_arn=ROLE_ARN,
        bucket=BUCKET,
        key_prefix="p",
        bedrock_client=bedrock,
        s3_client=s3_client,
        max_records_per_job=max_records_per_job,
        poll_interval_seconds=0,
    )

    assert len(bedrock.created_jobs) == 2
    assert len(results) == len(requests)
    assert [r.token for r in results] == [req.token for req in requests]
    assert all(r.embedding is not None for r in results)
