"""Run `dia` commands as ECS tasks, and look at the tasks.

A task runs the image built from `task/Dockerfile` on the shared GDS IDEA ECS
cluster. Everything it needs to be launched (cluster, task definition, subnets,
security group, log group) comes from the `RuntimeConfig`.

The cluster is shared with other applications, so tasks are only ever listed by
the pipeline's task definition family, never all of them.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from dia.naming import REGION
from dia.runtime_config import RuntimeConfig

# The container in the task definition (stacks/pipeline_task.py) and its log stream prefix.
CONTAINER_NAME = "Pipeline"
LOG_STREAM_PREFIX = "pipeline"

STARTED_BY_PREFIX = "dia-cli/"

# ECS allows letters, numbers, hyphens, slashes and underscores, up to 128 characters.
_STARTED_BY_MAX_LENGTH = 128
_STARTED_BY_DISALLOWED = re.compile(r"[^A-Za-z0-9_/-]")

_POLL_SECONDS = 3

# While nothing else is printed (Fargate takes a minute or so to start a task), say so this often.
_QUIET_SECONDS = 15

# ECS stops listing stopped tasks after about an hour.
STOPPED_TASK_RETENTION = "about an hour"


class RemoteError(Exception):
    """A task could not be launched, found, stopped or followed."""


@dataclass(frozen=True)
class TaskInfo:
    """What `dia pipeline tasks` shows about one task."""

    task_id: str
    status: str
    command: str
    started_by: str
    created_at: datetime | None
    exit_code: int | None
    stop_reason: str | None


@dataclass(frozen=True)
class LogPage:
    """Log lines read from a task's stream, and where to carry on from."""

    lines: list[str]
    token: str | None
    """Pass this back to `read_log_page` to read only what is written after these lines."""


# --- who is launching ---


def started_by_label(caller_arn: str) -> str:
    """The `startedBy` value for the caller, so tasks on the shared cluster can be told apart.

    For an assumed role the label comes from the role name, up to its first hyphen,
    so `david.gillespie-poweraccess` and `david.gillespie-readonly` give the same
    label. If that part has no dot (it is not a person's name), the whole role name
    is used. Characters ECS does not allow, such as dots, become hyphens.

    Args:
        caller_arn: The ARN from STS `GetCallerIdentity`.

    Returns:
        For example `dia-cli/david-gillespie`.
    """
    name = caller_arn.split(":assumed-role/")[1].split("/")[0] if ":assumed-role/" in caller_arn else caller_arn
    name = name.rsplit("/", 1)[-1]

    first = name.split("-")[0]
    who = first if "." in first else name

    label = _STARTED_BY_DISALLOWED.sub("-", who)
    return (STARTED_BY_PREFIX + label)[:_STARTED_BY_MAX_LENGTH]


def caller_started_by(sts_client: BaseClient | None = None) -> str:
    """The `startedBy` value for the active credentials.

    Raises:
        RemoteError: If the caller cannot be identified.
    """
    sts = sts_client or boto3.client("sts", region_name=REGION)
    try:
        arn = sts.get_caller_identity()["Arn"]
    except (ClientError, BotoCoreError) as e:
        raise RemoteError(f"Could not work out who you are (STS): {e}") from e
    return started_by_label(arn)


# --- helpers ---


def task_definition_family(config: RuntimeConfig) -> str:
    """The family of the pipeline task definition, for example `dia-pipeline-task-dev`."""
    return config.task_definition_arn.rsplit("/", 1)[-1].split(":")[0]


def task_id_from_arn(task_arn: str) -> str:
    """The task ID: the last part of the task ARN."""
    return task_arn.rsplit("/", 1)[-1]


def _ecs(client: BaseClient | None) -> BaseClient:
    return client or boto3.client("ecs", region_name=REGION)


def _logs(client: BaseClient | None) -> BaseClient:
    return client or boto3.client("logs", region_name=REGION)


def _status(task: dict) -> str:
    """ECS's last known status, or STOPPING when ECS has been told to stop the task but it has not yet.

    STOPPING is our label, not an ECS status: until the task has shut down ECS still reports its
    last status (usually RUNNING), which looks as if a stop had no effect.
    """
    status = task.get("lastStatus", "UNKNOWN")
    if task.get("desiredStatus") == "STOPPED" and status != "STOPPED":
        return "STOPPING"
    return status


def _to_info(task: dict) -> TaskInfo:
    overrides = task.get("overrides", {}).get("containerOverrides", [])
    command = next((" ".join(o.get("command", [])) for o in overrides if o.get("name") == CONTAINER_NAME), "")
    containers = [c for c in task.get("containers", []) if c.get("name") == CONTAINER_NAME]
    exit_code = containers[0].get("exitCode") if containers else None
    return TaskInfo(
        task_id=task_id_from_arn(task["taskArn"]),
        status=_status(task),
        command=command,
        started_by=task.get("startedBy", ""),
        created_at=task.get("createdAt"),
        exit_code=exit_code,
        stop_reason=task.get("stoppedReason"),
    )


# --- ECS ---


def launch(config: RuntimeConfig, command: list[str], started_by: str, ecs_client: BaseClient | None = None) -> str:
    """Start a task that runs `dia <command>`.

    Args:
        config: The runtime config, which says where and how to run.
        command: The arguments to `dia`, for example `["pipeline", "preflight"]`.
        started_by: The `startedBy` value to record on the task.
        ecs_client: Optional injected ECS client (for testing).

    Returns:
        The task ID.

    Raises:
        RemoteError: If ECS refuses or fails to start the task.
    """
    try:
        response = _ecs(ecs_client).run_task(
            cluster=config.cluster_name,
            taskDefinition=config.task_definition_arn,
            launchType="FARGATE",
            count=1,
            startedBy=started_by,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": config.subnet_ids,
                    "securityGroups": [config.security_group_id],
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={"containerOverrides": [{"name": CONTAINER_NAME, "command": command}]},
        )
    except (ClientError, BotoCoreError) as e:
        raise RemoteError(f"Could not start the task: {e}") from e

    if response.get("failures") or not response.get("tasks"):
        problems = "; ".join(f"{f.get('reason')} {f.get('detail', '')}".strip() for f in response.get("failures", []))
        raise RemoteError(f"ECS did not start the task: {problems or 'no task returned'}")

    return task_id_from_arn(response["tasks"][0]["taskArn"])


def describe(config: RuntimeConfig, task_id: str, ecs_client: BaseClient | None = None) -> TaskInfo:
    """Describe one task.

    Args:
        config: The runtime config.
        task_id: The task to describe.
        ecs_client: Optional injected ECS client (for testing).

    Returns:
        What ECS reports about the task.

    Raises:
        RemoteError: If the task cannot be read or is not found (ECS forgets stopped
            tasks after about an hour).
    """
    try:
        response = _ecs(ecs_client).describe_tasks(cluster=config.cluster_name, tasks=[task_id])
    except (ClientError, BotoCoreError) as e:
        raise RemoteError(f"Could not describe task {task_id}: {e}") from e

    if not response.get("tasks"):
        raise RemoteError(f"Task {task_id} was not found. ECS forgets stopped tasks after {STOPPED_TASK_RETENTION}.")
    return _to_info(response["tasks"][0])


def list_tasks(
    config: RuntimeConfig, started_by: str | None = None, ecs_client: BaseClient | None = None
) -> list[TaskInfo]:
    """Running and recently stopped tasks of the pipeline task definition, newest first.

    Args:
        config: The runtime config.
        started_by: If given, only tasks started with this exact `startedBy` value.
        ecs_client: Optional injected ECS client (for testing).

    Returns:
        The tasks, newest first.

    Raises:
        RemoteError: If ECS cannot be read.
    """
    ecs = _ecs(ecs_client)
    family = task_definition_family(config)

    arns: list[str] = []
    try:
        for desired_status in ("RUNNING", "STOPPED"):
            paginator = ecs.get_paginator("list_tasks")
            for page in paginator.paginate(cluster=config.cluster_name, family=family, desiredStatus=desired_status):
                arns.extend(page["taskArns"])

        tasks: list[dict] = []
        for start in range(0, len(arns), 100):
            tasks.extend(ecs.describe_tasks(cluster=config.cluster_name, tasks=arns[start : start + 100])["tasks"])
    except (ClientError, BotoCoreError) as e:
        raise RemoteError(f"Could not list tasks: {e}") from e

    infos = [_to_info(t) for t in tasks]
    if started_by is not None:
        infos = [i for i in infos if i.started_by == started_by]
    return sorted(infos, key=lambda i: (i.created_at is not None, i.created_at), reverse=True)


def stop(config: RuntimeConfig, task_id: str, ecs_client: BaseClient | None = None) -> None:
    """Stop a running task.

    Args:
        config: The runtime config.
        task_id: The task to stop.
        ecs_client: Optional injected ECS client (for testing).

    Raises:
        RemoteError: If ECS refuses.
    """
    try:
        _ecs(ecs_client).stop_task(
            cluster=config.cluster_name, task=task_id, reason="Stopped with dia pipeline tasks stop"
        )
    except (ClientError, BotoCoreError) as e:
        raise RemoteError(f"Could not stop task {task_id}: {e}") from e


# --- logs ---


def log_stream_name(task_id: str) -> str:
    """The CloudWatch log stream a task writes to."""
    return f"{LOG_STREAM_PREFIX}/{CONTAINER_NAME}/{task_id}"


def read_log_page(
    config: RuntimeConfig,
    task_id: str,
    token: str | None = None,
    logs_client: BaseClient | None = None,
) -> LogPage:
    """Read a task's log lines, from the start or from where an earlier read stopped.

    If the stream does not exist yet (the container has not started) there are no
    lines and the token is unchanged.

    Args:
        config: The runtime config.
        task_id: The task whose logs to read.
        token: The `token` of an earlier `LogPage`, to read only what came after it.
            None reads from the start.
        logs_client: Optional injected logs client (for testing).

    Returns:
        The new lines, and the token to continue from.

    Raises:
        RemoteError: If the logs cannot be read.
    """
    logs = _logs(logs_client)
    lines: list[str] = []
    while True:
        kwargs = {"logGroupName": config.log_group, "logStreamName": log_stream_name(task_id), "startFromHead": True}
        if token:
            kwargs["nextToken"] = token
        try:
            response = logs.get_log_events(**kwargs)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return LogPage(lines, token)
            raise RemoteError(f"Could not read the logs of task {task_id}: {e}") from e
        except BotoCoreError as e:
            raise RemoteError(f"Could not read the logs of task {task_id}: {e}") from e

        lines.extend(event["message"] for event in response["events"])

        next_token = response.get("nextForwardToken")
        if not response["events"] or next_token == token:
            return LogPage(lines, next_token or token)
        token = next_token


def follow(
    config: RuntimeConfig,
    task_id: str,
    emit: Callable[[str], None],
    *,
    ecs_client: BaseClient | None = None,
    logs_client: BaseClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Print a task's log lines as they arrive, until the task stops.

    There is no time limit: this follows until the task stops, and a task has none
    (see #67). Ctrl-C stops following without stopping the task.

    Also prints the task's status when it changes, and a "Still ..." line when
    nothing has been printed for a while, so a slow start does not look stuck.

    Args:
        config: The runtime config.
        task_id: The task to follow.
        emit: Called with each new log line and progress message.
        ecs_client: Optional injected ECS client (for testing).
        logs_client: Optional injected logs client (for testing).
        sleep: Waits between polls (replaceable for testing).
        clock: Seconds from a monotonic clock (replaceable for testing).

    Returns:
        The container's exit code. 1 if the task stopped without one, for example
        because the image could not be pulled (the stop reason is then emitted).

    Raises:
        RemoteError: If ECS or the logs cannot be read.
    """
    token = None
    started = last_output = clock()
    last_status = None
    while True:
        info = describe(config, task_id, ecs_client)
        stopped = info.status == "STOPPED"

        if info.status != last_status:
            emit(f"Task status: {info.status}")
            last_status = info.status
            last_output = clock()

        # Read the logs after the status, so lines written just before the stop are not missed.
        page = read_log_page(config, task_id, token, logs_client)
        token = page.token
        for line in page.lines:
            emit(line)
        if page.lines:
            last_output = clock()

        if stopped:
            if info.exit_code is None:
                emit(f"Task stopped without running: {info.stop_reason or 'no reason given'}")
                return 1
            return info.exit_code

        if clock() - last_output >= _QUIET_SECONDS:
            emit(f"Still {info.status} ({int(clock() - started)}s)")
            last_output = clock()
        sleep(_POLL_SECONDS)
