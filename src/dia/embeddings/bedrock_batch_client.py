"""Low-level Bedrock batch inference client: submit texts for embedding,
wait, and return results keyed by a caller-supplied token.

Deliberately synchronous (plain boto3), not async - a batch job takes
minutes to hours and is mostly idle waiting, so there's little to gain
from async here (unlike PooledBedrockEmbedding, where many short calls
genuinely benefit from concurrency). This mirrors graphrag_toolkit's own
create_and_run_batch_job/wait_for_job_completion pattern (sync,
time.sleep(60) polling) - a proven approach for this exact kind of
long-running, mostly-idle operation. If an async caller needs this later,
asyncio.to_thread(submit_and_await_batch_embeddings, ...) is a one-line
adaptation, not a redesign.

Deliberately does not depend on graphrag_toolkit - see dia.embeddings's
module docstring for why. Reimplements the same Bedrock batch input/output
format (verified against real completed jobs, not just AWS docs):
  - Input: one JSONL file, one {"recordId": ..., "modelInput": {...}} per line.
  - Output: <output_prefix>/<jobId>/<input_filename>.jsonl.out, plus a
    manifest.json.out in the same folder (excluded when scanning for
    output records).
  - Output record order is NOT guaranteed to match input order (AWS's own
    docs state this explicitly) - results are re-attached by recordId,
    never by position.
  - Failed records carry an "error" field instead of "modelOutput".

recordId safety: real document keys can be long, contain spaces/#/%, and
have no documented AWS length/character guarantee. This module never uses
caller-supplied identifiers as recordIds directly - it generates its own
synthetic sequential recordIds and maps them back to the caller's opaque
`token` on each BatchEmbeddingRequest.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field

import boto3

logger = logging.getLogger(__name__)

# Bedrock's own minimum record count per batch inference job. Redefined
# here rather than imported from graphrag_toolkit - see module docstring.
BEDROCK_MIN_BATCH_SIZE = 100

# Conservative defaults, well under Bedrock's hard per-job limits (100,000
# records / ~1GB input file size at time of writing) - leaves margin
# rather than hugging the documented ceiling exactly.
DEFAULT_MAX_RECORDS_PER_JOB = 50_000
DEFAULT_MAX_BYTES_PER_JOB = 900_000_000

_TERMINAL_STATUSES = {"Completed", "Failed", "Stopped", "PartiallyCompleted", "Expired"}
_SUCCESS_STATUSES = {"Completed", "PartiallyCompleted"}


class BatchEmbeddingJobError(Exception):
    """A batch inference job ended in a non-recoverable state (Failed,
    Stopped, or Expired) - as opposed to PartiallyCompleted, where some
    records did succeed and are still returned."""


@dataclass(frozen=True)
class BatchEmbeddingRequest:
    """One text to be embedded via Bedrock batch inference.

    `token` is an opaque identifier the caller chooses (e.g. a
    (doc_key, window_index) tuple encoded however they like) - used only
    to map BatchEmbeddingResults back to the caller's own data. Never sent
    to AWS as-is; see module docstring on recordId safety.
    """

    token: str
    text: str


@dataclass(frozen=True)
class BatchEmbeddingResult:
    """The embedding for one BatchEmbeddingRequest, matched by `token`.

    `embedding` is None and `error` is set if this specific record failed
    - one failed record does not fail the whole batch (unless the job
    itself ends Failed/Stopped/Expired, which raises instead).
    """

    token: str
    embedding: list[float] | None
    error: str | None = None


@dataclass(frozen=True)
class _Job:
    """Internal: one submitted batch inference job and the recordId->token
    mapping needed to re-attach its results."""

    job_arn: str
    input_key: str
    output_prefix: str
    record_id_to_token: dict[str, str] = field(default_factory=dict)


def _split_into_jobs(
    requests: list[BatchEmbeddingRequest],
    max_records_per_job: int,
    max_bytes_per_job: int,
) -> list[list[BatchEmbeddingRequest]]:
    """Split requests into groups that each respect both the record-count
    and file-size limits. At today's real usage this is a no-op (one
    group) - it only engages once volume approaches Bedrock's per-job
    limits."""
    groups: list[list[BatchEmbeddingRequest]] = []
    current: list[BatchEmbeddingRequest] = []
    current_bytes = 0

    for request in requests:
        # Rough per-record byte estimate: text length plus JSON/field overhead.
        record_bytes = len(request.text.encode("utf-8")) + 64
        would_overflow_count = len(current) >= max_records_per_job
        would_overflow_bytes = current and (current_bytes + record_bytes) > max_bytes_per_job

        if would_overflow_count or would_overflow_bytes:
            groups.append(current)
            current = []
            current_bytes = 0

        current.append(request)
        current_bytes += record_bytes

    if current:
        groups.append(current)

    return groups


def _submit_job(
    requests: list[BatchEmbeddingRequest],
    *,
    model_id: str,
    role_arn: str,
    bucket: str,
    key_prefix: str,
    bedrock_client,
    s3_client,
) -> _Job:
    """Build the JSONL input, upload it, and submit one batch inference job."""
    record_id_to_token: dict[str, str] = {}
    lines = []
    for i, request in enumerate(requests):
        record_id = str(i)
        record_id_to_token[record_id] = request.token
        lines.append(json.dumps({"recordId": record_id, "modelInput": {"inputText": request.text}}))

    job_id = uuid.uuid4().hex[:12]
    input_key = f"{key_prefix}/{job_id}/input.jsonl"
    output_prefix = f"{key_prefix}/{job_id}/output/"

    s3_client.put_object(Bucket=bucket, Key=input_key, Body="\n".join(lines).encode("utf-8"))

    response = bedrock_client.create_model_invocation_job(
        jobName=f"batch-embed-{job_id}",
        roleArn=role_arn,
        modelId=model_id,
        inputDataConfig={"s3InputDataConfig": {"s3Uri": f"s3://{bucket}/{input_key}"}},
        outputDataConfig={"s3OutputDataConfig": {"s3Uri": f"s3://{bucket}/{output_prefix}"}},
    )

    logger.info(
        "Submitted batch embedding job [job_arn=%s records=%d input=%s]",
        response["jobArn"],
        len(requests),
        input_key,
    )

    return _Job(
        job_arn=response["jobArn"],
        input_key=input_key,
        output_prefix=output_prefix,
        record_id_to_token=record_id_to_token,
    )


def _wait_for_job(job: _Job, *, bedrock_client, poll_interval_seconds: float) -> str:
    """Poll until the job reaches a terminal status. Returns the final
    status. Raises BatchEmbeddingJobError for Failed/Stopped/Expired."""
    status = "Submitted"
    while status not in _TERMINAL_STATUSES:
        time.sleep(poll_interval_seconds)
        response = bedrock_client.get_model_invocation_job(jobIdentifier=job.job_arn)
        status = response["status"]
        logger.debug("Batch embedding job status [job_arn=%s status=%s]", job.job_arn, status)

    if status not in _SUCCESS_STATUSES:
        message = response.get("message", "")
        raise BatchEmbeddingJobError(f"Batch embedding job ended [job_arn={job.job_arn} status={status}] {message}")

    return status


def _download_job_results(job: _Job, *, bucket: str, s3_client) -> list[BatchEmbeddingResult]:
    """Download and parse this job's output, re-attaching results to the
    caller's tokens via the recordId map. Output object order is not
    meaningful (AWS doesn't guarantee it) - every record is matched by
    recordId, never by position."""
    results: list[BatchEmbeddingResult] = []

    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=job.output_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".jsonl.out"):
                continue  # excludes manifest.json.out and any other sibling objects

            body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
            for line in body.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                record_id = row["recordId"]
                token = job.record_id_to_token.get(record_id)
                if token is None:
                    logger.warning("Batch embedding output had unrecognised recordId=%r - skipping", record_id)
                    continue

                if "error" in row:
                    results.append(BatchEmbeddingResult(token=token, embedding=None, error=str(row["error"])))
                else:
                    embedding = row["modelOutput"]["embedding"]
                    results.append(BatchEmbeddingResult(token=token, embedding=embedding))

    return results


def submit_and_await_batch_embeddings(
    requests: list[BatchEmbeddingRequest],
    *,
    model_id: str,
    role_arn: str,
    bucket: str,
    key_prefix: str,
    bedrock_client=None,
    s3_client=None,
    max_records_per_job: int = DEFAULT_MAX_RECORDS_PER_JOB,
    max_bytes_per_job: int = DEFAULT_MAX_BYTES_PER_JOB,
    poll_interval_seconds: float = 30.0,
) -> list[BatchEmbeddingResult]:
    """Embed every request via Bedrock batch inference and return results.

    Results are returned positionally aligned with `requests` (result[i]
    corresponds to requests[i]) - AWS gives no ordering guarantee on batch
    output, so this reorders by recordId internally. A request whose
    result never arrives gets a synthesised error result rather than
    silently shrinking the list; per-record failures (the job succeeded
    but this specific record didn't) come through the same way, with
    `error` set and `embedding` None.

    Splits into multiple jobs automatically if `requests` exceeds
    `max_records_per_job` or `max_bytes_per_job` - transparent to the
    caller either way. Blocks (time.sleep) until every job reaches a
    terminal state.

    Raises:
        ValueError: fewer than BEDROCK_MIN_BATCH_SIZE requests - Bedrock's
            API itself would reject this; callers below the minimum should
            use an on-demand embedding path instead (this function does
            not fall back to one itself - that decision belongs to the
            caller, since only the caller knows whether an on-demand
            alternative exists).
        BatchEmbeddingJobError: any job ended Failed/Stopped/Expired.
    """
    if len(requests) < BEDROCK_MIN_BATCH_SIZE:
        raise ValueError(
            f"submit_and_await_batch_embeddings called with {len(requests)} requests, "
            f"below Bedrock's minimum of {BEDROCK_MIN_BATCH_SIZE} per job. "
            "Use an on-demand embedding path for small counts instead."
        )

    bedrock_client = bedrock_client or boto3.client("bedrock")
    s3_client = s3_client or boto3.client("s3")

    groups = _split_into_jobs(requests, max_records_per_job, max_bytes_per_job)
    if len(groups) > 1:
        logger.info(
            "Splitting %d requests into %d batch embedding jobs (max_records_per_job=%d)",
            len(requests),
            len(groups),
            max_records_per_job,
        )

    jobs = [
        _submit_job(
            group,
            model_id=model_id,
            role_arn=role_arn,
            bucket=bucket,
            key_prefix=key_prefix,
            bedrock_client=bedrock_client,
            s3_client=s3_client,
        )
        for group in groups
    ]

    all_results: list[BatchEmbeddingResult] = []
    for job in jobs:
        _wait_for_job(job, bedrock_client=bedrock_client, poll_interval_seconds=poll_interval_seconds)
        all_results.extend(_download_job_results(job, bucket=bucket, s3_client=s3_client))

    return _reorder_to_match_requests(requests, all_results)


def _reorder_to_match_requests(
    requests: list[BatchEmbeddingRequest], results: list[BatchEmbeddingResult]
) -> list[BatchEmbeddingResult]:
    """Output object scan order has no relationship to input order (S3
    listing order, not job order) - reorder so callers get results
    positionally aligned with their requests, which matters for anything
    re-attaching embeddings to an ordered sequence (e.g. sentence windows).

    A request whose token never appears in results (dropped record, not
    just a per-record error - those already come through as a normal
    BatchEmbeddingResult with `error` set) gets a synthesised result
    rather than silently shrinking the returned list.
    """
    token_to_result = {result.token: result for result in results}
    return [
        token_to_result.get(request.token)
        or BatchEmbeddingResult(token=request.token, embedding=None, error="no output record found for this request")
        for request in requests
    ]
