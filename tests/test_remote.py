"""Tests for dia.remote — launching and following tasks, with AWS mocked."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from dia.remote import (
    LogPage,
    RemoteError,
    TaskInfo,
    caller_started_by,
    describe,
    follow,
    launch,
    list_tasks,
    log_stream_name,
    read_log_page,
    started_by_label,
    stop,
    task_definition_family,
)
from dia.runtime_config import RuntimeConfig

CONFIG = RuntimeConfig(
    neptune_endpoint="dia-neptune-dev.cluster-abc.eu-west-2.neptune.amazonaws.com",
    opensearch_endpoint="abc123.eu-west-2.aoss.amazonaws.com",
    cluster_name="shared-cluster",
    task_definition_arn="arn:aws:ecs:eu-west-2:992382722318:task-definition/dia-pipeline-task-dev:3",
    subnet_ids=["subnet-1", "subnet-2"],
    security_group_id="sg-123",
    log_group="/dia-task-dev",
)

TASK_ARN = "arn:aws:ecs:eu-west-2:992382722318:task/shared-cluster/abc123"


def _client_error(code: str = "AccessDenied") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "nope"}}, "Operation")


def _task(
    task_id="abc123", status="STOPPED", exit_code=0, started_by="dia-cli/me", created=None, reason=None, desired=None
):
    task = {
        "taskArn": f"arn:aws:ecs:eu-west-2:992382722318:task/shared-cluster/{task_id}",
        "lastStatus": status,
        "startedBy": started_by,
        "createdAt": created or datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
        "overrides": {"containerOverrides": [{"name": "Pipeline", "command": ["pipeline", "preflight"]}]},
        "containers": [{"name": "Pipeline", **({"exitCode": exit_code} if exit_code is not None else {})}],
    }
    if reason:
        task["stoppedReason"] = reason
    if desired:
        task["desiredStatus"] = desired
    return task


# --- who is launching ---


@pytest.mark.parametrize(
    "arn,expected",
    [
        ("arn:aws:sts::992382722318:assumed-role/david.gillespie-poweraccess/gds-users", "dia-cli/david-gillespie"),
        ("arn:aws:sts::992382722318:assumed-role/david.gillespie-readonly/gds-users", "dia-cli/david-gillespie"),
        ("arn:aws:sts::992382722318:assumed-role/david.gillespie-read-only/x", "dia-cli/david-gillespie"),
        ("arn:aws:sts::992382722318:assumed-role/dia-pipeline-task-dev/abc", "dia-cli/dia-pipeline-task-dev"),
        ("arn:aws:iam::992382722318:user/david.gillespie", "dia-cli/david-gillespie"),
    ],
)
def test_started_by_label_comes_from_the_role_name_up_to_the_first_hyphen(arn, expected):
    assert started_by_label(arn) == expected


def test_started_by_label_only_uses_characters_ecs_allows_and_fits_its_length():
    label = started_by_label("arn:aws:sts::1:assumed-role/" + "a.b@c" * 60 + "/s")

    assert len(label) <= 128
    assert all(c.isalnum() or c in "-_/" for c in label)


def test_caller_started_by_reads_the_identity_from_sts():
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Arn": "arn:aws:sts::1:assumed-role/david.gillespie-poweraccess/s"}

    assert caller_started_by(sts) == "dia-cli/david-gillespie"


def test_caller_started_by_fails_when_sts_fails():
    sts = MagicMock()
    sts.get_caller_identity.side_effect = _client_error()

    with pytest.raises(RemoteError, match="STS"):
        caller_started_by(sts)


def test_task_definition_family_drops_the_account_and_revision():
    assert task_definition_family(CONFIG) == "dia-pipeline-task-dev"


# --- launch ---


def test_launch_runs_the_command_on_fargate_in_the_private_subnets_without_a_public_ip():
    ecs = MagicMock()
    ecs.run_task.return_value = {"tasks": [{"taskArn": TASK_ARN}], "failures": []}

    task_id = launch(CONFIG, ["pipeline", "preflight"], "dia-cli/me", ecs)

    assert task_id == "abc123"
    kwargs = ecs.run_task.call_args.kwargs
    assert kwargs["cluster"] == "shared-cluster"
    assert kwargs["taskDefinition"] == CONFIG.task_definition_arn
    assert kwargs["launchType"] == "FARGATE"
    assert kwargs["startedBy"] == "dia-cli/me"
    assert kwargs["networkConfiguration"]["awsvpcConfiguration"] == {
        "subnets": ["subnet-1", "subnet-2"],
        "securityGroups": ["sg-123"],
        "assignPublicIp": "DISABLED",
    }
    assert kwargs["overrides"] == {"containerOverrides": [{"name": "Pipeline", "command": ["pipeline", "preflight"]}]}


def test_launch_reports_ecs_failures():
    ecs = MagicMock()
    ecs.run_task.return_value = {"tasks": [], "failures": [{"reason": "MISSING", "detail": "no such thing"}]}

    with pytest.raises(RemoteError, match="MISSING no such thing"):
        launch(CONFIG, ["pipeline", "preflight"], "dia-cli/me", ecs)


def test_launch_reports_an_api_error():
    ecs = MagicMock()
    ecs.run_task.side_effect = _client_error("AccessDeniedException")

    with pytest.raises(RemoteError, match="Could not start the task"):
        launch(CONFIG, ["pipeline", "preflight"], "dia-cli/me", ecs)


# --- describe, list, stop ---


def test_describe_reports_status_command_and_exit_code():
    ecs = MagicMock()
    ecs.describe_tasks.return_value = {"tasks": [_task(exit_code=1, reason="Essential container in task exited")]}

    info = describe(CONFIG, "abc123", ecs)

    assert info == TaskInfo(
        task_id="abc123",
        status="STOPPED",
        command="pipeline preflight",
        started_by="dia-cli/me",
        created_at=datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
        exit_code=1,
        stop_reason="Essential container in task exited",
    )


@pytest.mark.parametrize(
    "status,desired,expected",
    [
        ("RUNNING", "RUNNING", "RUNNING"),
        ("RUNNING", "STOPPED", "STOPPING"),
        ("PENDING", "STOPPED", "STOPPING"),
        ("STOPPED", "STOPPED", "STOPPED"),
    ],
)
def test_a_task_ecs_is_stopping_shows_as_stopping(status, desired, expected):
    ecs = MagicMock()
    ecs.describe_tasks.return_value = {"tasks": [_task(status=status, desired=desired, exit_code=None)]}

    assert describe(CONFIG, "abc123", ecs).status == expected


def test_follow_keeps_waiting_while_a_task_is_stopping():
    ecs = MagicMock()
    ecs.describe_tasks.side_effect = [
        {"tasks": [_task(status="RUNNING", desired="STOPPED", exit_code=None)]},
        {"tasks": [_task(status="STOPPED", desired="STOPPED", exit_code=137)]},
    ]
    out: list[str] = []

    code = follow(
        CONFIG,
        "abc123",
        out.append,
        ecs_client=ecs,
        logs_client=_logs({"events": []}, {"events": []}),
        sleep=lambda s: None,
    )

    assert code == 137
    assert "Task status: STOPPING" in out

    ecs = MagicMock()
    ecs.describe_tasks.return_value = {"tasks": []}

    with pytest.raises(RemoteError, match="was not found"):
        describe(CONFIG, "gone", ecs)


def _ecs_with_tasks(running, stopped):
    ecs = MagicMock()
    pages = {"RUNNING": running, "STOPPED": stopped}
    paginator = MagicMock()
    paginator.paginate.side_effect = lambda **kw: [{"taskArns": [t["taskArn"] for t in pages[kw["desiredStatus"]]]}]
    ecs.get_paginator.return_value = paginator
    ecs.describe_tasks.side_effect = lambda **kw: {
        "tasks": [t for t in running + stopped if t["taskArn"] in kw["tasks"]]
    }
    return ecs, paginator


def test_list_tasks_only_asks_for_our_task_definition_family_and_sorts_newest_first():
    old = _task("old", created=datetime(2026, 10, 16, 8, 0, tzinfo=UTC))
    new = _task("new", status="RUNNING", exit_code=None, created=datetime(2026, 10, 16, 10, 0, tzinfo=UTC))
    ecs, paginator = _ecs_with_tasks([new], [old])

    infos = list_tasks(CONFIG, ecs_client=ecs)

    assert [i.task_id for i in infos] == ["new", "old"]
    assert all(call.kwargs["family"] == "dia-pipeline-task-dev" for call in paginator.paginate.call_args_list)
    assert all(call.kwargs["cluster"] == "shared-cluster" for call in paginator.paginate.call_args_list)


def test_list_tasks_can_keep_only_one_persons_tasks():
    mine = _task("mine", started_by="dia-cli/me")
    theirs = _task("theirs", started_by="dia-cli/them")
    ecs, _ = _ecs_with_tasks([], [mine, theirs])

    infos = list_tasks(CONFIG, started_by="dia-cli/me", ecs_client=ecs)

    assert [i.task_id for i in infos] == ["mine"]


def test_list_tasks_with_none_found_returns_an_empty_list():
    ecs, _ = _ecs_with_tasks([], [])

    assert list_tasks(CONFIG, ecs_client=ecs) == []


def test_stop_stops_the_task_on_the_cluster():
    ecs = MagicMock()

    stop(CONFIG, "abc123", ecs)

    assert ecs.stop_task.call_args.kwargs["cluster"] == "shared-cluster"
    assert ecs.stop_task.call_args.kwargs["task"] == "abc123"


def test_stop_reports_an_api_error():
    ecs = MagicMock()
    ecs.stop_task.side_effect = _client_error()

    with pytest.raises(RemoteError, match="Could not stop"):
        stop(CONFIG, "abc123", ecs)


# --- logs ---


def test_the_log_stream_is_named_from_the_container_and_task():
    assert log_stream_name("abc123") == "pipeline/Pipeline/abc123"


def _logs(*pages):
    logs = MagicMock()
    logs.get_log_events.side_effect = list(pages)
    return logs


def test_read_log_page_reads_until_the_token_stops_moving():
    logs = _logs(
        {"events": [{"message": "one"}, {"message": "two"}], "nextForwardToken": "t1"},
        {"events": [], "nextForwardToken": "t1"},
    )

    page = read_log_page(CONFIG, "abc123", logs_client=logs)

    assert page.lines == ["one", "two"]
    assert page.token == "t1"
    first = logs.get_log_events.call_args_list[0].kwargs
    assert first["logGroupName"] == "/dia-task-dev"
    assert first["logStreamName"] == "pipeline/Pipeline/abc123"
    assert logs.get_log_events.call_args_list[1].kwargs["nextToken"] == "t1"


def test_read_log_page_gives_no_lines_before_the_stream_exists():
    logs = MagicMock()
    logs.get_log_events.side_effect = _client_error("ResourceNotFoundException")

    assert read_log_page(CONFIG, "abc123", logs_client=logs) == LogPage([], None)


def test_read_log_page_reports_other_errors():
    logs = MagicMock()
    logs.get_log_events.side_effect = _client_error("AccessDeniedException")

    with pytest.raises(RemoteError, match="Could not read the logs"):
        read_log_page(CONFIG, "abc123", logs_client=logs)


# --- follow ---


def test_follow_prints_new_lines_each_poll_and_returns_the_exit_code():
    ecs = MagicMock()
    ecs.describe_tasks.side_effect = [
        {"tasks": [_task(status="PENDING", exit_code=None)]},
        {"tasks": [_task(status="RUNNING", exit_code=None)]},
        {"tasks": [_task(status="STOPPED", exit_code=0)]},
    ]
    logs = _logs(
        {"events": [], "nextForwardToken": "t0"},
        {"events": [{"message": "a"}], "nextForwardToken": "t1"},
        {"events": [], "nextForwardToken": "t1"},
        {"events": [{"message": "b"}], "nextForwardToken": "t2"},
        {"events": [], "nextForwardToken": "t2"},
    )
    out: list[str] = []
    sleeps: list[float] = []

    code = follow(CONFIG, "abc123", out.append, ecs_client=ecs, logs_client=logs, sleep=sleeps.append)

    assert code == 0
    assert [line for line in out if not line.startswith("Task status")] == ["a", "b"]
    assert len(sleeps) == 2


def test_follow_returns_the_containers_nonzero_exit_code():
    ecs = MagicMock()
    ecs.describe_tasks.return_value = {"tasks": [_task(status="STOPPED", exit_code=3)]}

    code = follow(CONFIG, "abc123", lambda line: None, ecs_client=ecs, logs_client=_logs({"events": []}))

    assert code == 3


def test_follow_reports_the_stop_reason_when_the_task_never_ran():
    ecs = MagicMock()
    ecs.describe_tasks.return_value = {
        "tasks": [_task(status="STOPPED", exit_code=None, reason="CannotPullContainerError: no outbound access")]
    }
    logs = MagicMock()
    logs.get_log_events.side_effect = _client_error("ResourceNotFoundException")
    out: list[str] = []

    code = follow(CONFIG, "abc123", out.append, ecs_client=ecs, logs_client=logs)

    assert code == 1
    assert "CannotPullContainerError" in out[-1]


class _Clock:
    """A fake clock that moves on only when the test's `sleep` is called."""

    def __init__(self, step: float):
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += self.step


def _follow_statuses(statuses, step, logs=None):
    ecs = MagicMock()
    ecs.describe_tasks.side_effect = [{"tasks": [_task(status=s, exit_code=0)]} for s in statuses]
    logs = logs or MagicMock(**{"get_log_events.side_effect": _client_error("ResourceNotFoundException")})
    clock = _Clock(step)
    out: list[str] = []
    follow(CONFIG, "abc123", out.append, ecs_client=ecs, logs_client=logs, sleep=clock.sleep, clock=clock)
    return out


def test_follow_says_when_the_status_changes_and_only_then():
    out = _follow_statuses(["PENDING", "PENDING", "RUNNING", "STOPPED"], step=1)

    assert out == ["Task status: PENDING", "Task status: RUNNING", "Task status: STOPPED"]


def test_follow_says_it_is_still_waiting_when_nothing_is_printed_for_a_while():
    out = _follow_statuses(["PENDING"] * 12 + ["STOPPED"], step=3)

    assert out[0] == "Task status: PENDING"
    assert [line for line in out if line.startswith("Still")] == ["Still PENDING (15s)", "Still PENDING (30s)"]


def test_follow_does_not_repeat_itself_while_logs_are_arriving():
    calls = {"n": 0}

    def get_log_events(**kwargs):
        # A new line on every other call (the first read of each poll), nothing on the confirming read.
        calls["n"] += 1
        if calls["n"] % 2:
            return {"events": [{"message": f"line {calls['n']}"}], "nextForwardToken": f"t{calls['n']}"}
        return {"events": [], "nextForwardToken": kwargs["nextToken"]}

    logs = MagicMock()
    logs.get_log_events.side_effect = get_log_events

    out = _follow_statuses(["RUNNING"] * 8 + ["STOPPED"], step=3, logs=logs)

    assert any(line.startswith("line") for line in out)
    assert not [line for line in out if line.startswith("Still")]
