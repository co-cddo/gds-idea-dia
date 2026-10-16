"""Preflight checks: can this process do what the pipeline needs?

`dia pipeline preflight` runs these checks, in order, and reports one line for
each. It is read-only: it only describes, lists and reads.

What is checked depends on where it runs:

- Anywhere (a laptop, or a task): identity, the runtime config, the ledger
  table, our buckets and access to the source data. These are what local runs
  and tasks both need.
- Inside an ECS task only: Neptune. Neptune is only reachable from inside the
  VPC, and only tasks talk to it, so a local run never checks it.

Each check returns a `CheckResult`. A check that cannot run because an earlier
one failed is reported as skipped, so one problem is not reported many times.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from gds_idea_cdk_constructs import DeploymentEnvironment

from dia.naming import REGION, Bucket, Names
from dia.runtime_config import RuntimeConfig, RuntimeConfigError
from dia.sources.known import get_source
from dia.types import DataSource

# Sources whose input location is checked. GATS business cases is the first source.
PREFLIGHT_SOURCES = ("gats-business-cases",)

_CONNECT_TIMEOUT_SECONDS = 3

# ECS sets this variable in every task container (the task metadata endpoint):
# https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v4-fargate.html
_ECS_TASK_MARKER = "ECS_CONTAINER_METADATA_URI_V4"


class Status(StrEnum):
    """Outcome of a check."""

    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check, with a short human-readable detail."""

    name: str
    status: Status
    detail: str


def _ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, Status.OK, detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, Status.FAIL, detail)


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name, Status.SKIP, detail)


def running_in_ecs_task() -> bool:
    """Whether this process is running inside an ECS task."""
    return bool(os.environ.get(_ECS_TASK_MARKER))


def check_identity(sts_client) -> tuple[CheckResult, DeploymentEnvironment | None]:
    """Who am I, and is it an environment we know?

    Args:
        sts_client: An STS client.

    Returns:
        The result, and the environment if the account is a known one (else None).
    """
    try:
        identity = sts_client.get_caller_identity()
    except (ClientError, BotoCoreError) as e:
        return _fail("identity", f"could not call STS (are your credentials valid?): {e}"), None

    account = identity["Account"]
    try:
        environment = DeploymentEnvironment.from_account_id(account)
    except ValueError:
        return _fail("identity", f"account {account} is not a known environment ({identity['Arn']})"), None

    return _ok("identity", f"{environment.short_name} (account {account}) as {identity['Arn']}"), environment


def check_runtime_config(names: Names, ssm_client=None) -> tuple[CheckResult, RuntimeConfig | None]:
    """Can the runtime config parameter be read and is it valid?

    Args:
        names: Names for the environment, used to build the parameter name.
        ssm_client: Optional injected SSM client (for testing).

    Returns:
        The result, and the config if it loaded (else None).
    """
    try:
        name = RuntimeConfig.parameter_name(names)
        config = RuntimeConfig.load_parameter(name, ssm_client=ssm_client)
    except RuntimeConfigError as e:
        return _fail("runtime config", str(e)), None

    return _ok("runtime config", f"{name}: Neptune {config.neptune_endpoint}, cluster {config.cluster_name}"), config


def check_ledger_table(names: Names, dynamodb_client) -> CheckResult:
    """Does the ledger table exist and can it be described?"""
    table = names("ledger")
    try:
        status = dynamodb_client.describe_table(TableName=table)["Table"]["TableStatus"]
    except (ClientError, BotoCoreError) as e:
        return _fail("ledger table", f"{table}: {e}")
    return _ok("ledger table", f"{table} ({status})")


def check_buckets(names: Names, s3_client) -> CheckResult:
    """Can every bucket this project owns be reached?"""
    failures = []
    for bucket in Bucket:
        name = names(bucket)
        try:
            s3_client.head_bucket(Bucket=name)
        except (ClientError, BotoCoreError) as e:
            failures.append(f"{name}: {e}")

    if failures:
        return _fail("buckets", "; ".join(failures))
    return _ok("buckets", f"all {len(Bucket)} reachable")


def source_s3_client(role_arn: str | None, sts_client):
    """An S3 client that can read production source data.

    Without a role (production) it reads directly. With one (dev) it reads
    through that role.

    Args:
        role_arn: The cross-account role from the runtime config, or None.
        sts_client: An STS client, used to assume the role.

    Returns:
        A boto3 S3 client.

    Raises:
        ClientError: If the role cannot be assumed.
    """
    if role_arn is None:
        return boto3.client("s3", region_name=REGION)

    credentials = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="dia-preflight")["Credentials"]
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )


def check_source_access(source: DataSource, role_arn: str | None, sts_client) -> CheckResult:
    """Can one object be listed from the source's real location?

    Args:
        source: The source to check.
        role_arn: The cross-account role to read through, or None to read directly.
        sts_client: An STS client, used to assume the role.
    """
    name = f"source {source.name}"
    location = f"s3://{source.bucket}/{source.prefix}"
    via = f" via {role_arn}" if role_arn else ""

    try:
        s3 = source_s3_client(role_arn, sts_client)
        response = s3.list_objects_v2(Bucket=source.bucket, Prefix=source.prefix, MaxKeys=1)
    except (ClientError, BotoCoreError) as e:
        return _fail(name, f"could not list {location}{via}: {e}")

    found = "has objects" if response.get("KeyCount", 0) else "is empty"
    return _ok(name, f"{location} {found}{via}")


def _tcp_connect(host: str, port: int) -> str | None:
    """Try to open a TCP connection.

    Returns:
        None if it worked, otherwise why it did not, with what to check first.
    """
    try:
        with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT_SECONDS):
            return None
    except socket.gaierror:
        return (
            "could not resolve the hostname (is the endpoint in the runtime config right, and is this task in the VPC?)"
        )
    except ConnectionRefusedError:
        return "connection refused (nothing is listening on that port: check the port in the runtime config)"
    except TimeoutError:
        return (
            f"timed out after {_CONNECT_TIMEOUT_SECONDS}s (a stopped cluster looks like this: check it is running, "
            "then the task's subnet and security group)"
        )
    except OSError as e:
        return f"{str(e) or type(e).__name__} (check the task's subnet and security group)"


def check_neptune(
    config: RuntimeConfig,
    *,
    connect: Callable[[str, int], str | None] = _tcp_connect,
    client_factory: Callable[..., object] = boto3.client,
) -> CheckResult:
    """Is Neptune reachable, and does IAM authentication work?

    Only meaningful inside the VPC, so it is only run inside a task.

    Args:
        config: The runtime config, which holds the Neptune endpoint and port.
        connect: Opens a TCP connection to a host and port. Returns None if it worked,
            otherwise the reason it did not (replaceable for testing).
        client_factory: Builds the boto3 client used for the status call
            (replaceable for testing).

    Returns:
        The result of the check.
    """
    endpoint, port = config.neptune_endpoint, config.neptune_port

    problem = connect(endpoint, port)
    if problem is not None:
        return _fail("neptune", f"cannot connect to {endpoint}:{port}: {problem}")

    try:
        client = client_factory(
            "neptunedata",
            endpoint_url=f"https://{endpoint}:{port}",
            region_name=REGION,
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=10),
        )
        status = client.get_engine_status()["status"]
    except (ClientError, BotoCoreError) as e:
        return _fail("neptune", f"connected to {endpoint}:{port} but the status call failed: {e}")

    return _ok("neptune", f"{endpoint}:{port} is {status}")


def run_preflight() -> list[CheckResult]:
    """Run every check that applies where this is running, and return the results."""
    in_task = running_in_ecs_task()
    region = {"region_name": REGION}
    sts = boto3.client("sts", **region)

    identity, environment = check_identity(sts)
    results = [identity]
    if environment is None:
        return [*results, *_skipped_after_identity(in_task)]

    names = Names(environment)
    config_result, config = check_runtime_config(names)
    results.append(config_result)
    results.append(check_ledger_table(names, boto3.client("dynamodb", **region)))
    results.append(check_buckets(names, boto3.client("s3", **region)))
    results.extend(_check_sources(environment, config, sts))

    if in_task:
        results.append(check_neptune(config) if config else _skip("neptune", "needs the runtime config"))

    return results


def _check_sources(environment: DeploymentEnvironment, config: RuntimeConfig | None, sts_client) -> list[CheckResult]:
    """Check access to each source. Dev needs the runtime config to know which role to use."""
    if config is None and environment != DeploymentEnvironment.PRODUCTION:
        return [_skip(f"source {name}", "needs the runtime config") for name in PREFLIGHT_SOURCES]

    role_arn = config.cross_account_role_arn if config else None
    return [check_source_access(get_source(name), role_arn, sts_client) for name in PREFLIGHT_SOURCES]


def _skipped_after_identity(in_task: bool) -> list[CheckResult]:
    reason = "needs a known environment"
    names = ["runtime config", "ledger table", "buckets", *(f"source {s}" for s in PREFLIGHT_SOURCES)]
    if in_task:
        names.append("neptune")
    return [_skip(name, reason) for name in names]
