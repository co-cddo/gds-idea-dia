"""Tests for PipelineTaskStack — the task definition, roles, logs and runtime config parameter."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from aws_cdk import aws_ec2 as ec2
from gds_idea_cdk_constructs import DeploymentConfig, DeploymentEnvironment

from config import AppConfig
from dia.runtime_config import RuntimeConfig
from stacks.neptune import NeptuneStack
from stacks.opensearch import OpenSearchStack
from stacks.pipeline_task import PipelineTaskStack
from stacks.storage import StorageStack

DEV = DeploymentEnvironment.DEVELOPMENT
PROD = DeploymentEnvironment.PRODUCTION
CROSS_ACCOUNT_ROLE = f"arn:aws:iam::{PROD.value}:role/assume_role_for_development_account"
SOURCE_BUCKET = "source-bucket-for-tests"


@dataclass
class Built:
    template: assertions.Template
    stack: PipelineTaskStack
    outdir: Path
    config: AppConfig


def _build(environment: DeploymentEnvironment, outdir: Path, *, lookup_vpc: bool = False) -> Built:
    """Build the task stack with the stacks it depends on, in dev or prod."""
    config = AppConfig(environment=environment)
    app = cdk.App(outdir=str(outdir))
    env = cdk.Environment(account=config.account_number, region=config.region)

    harness = cdk.Stack(app, "Harness", env=env)
    vpc = ec2.Vpc.from_vpc_attributes(
        harness,
        "Vpc",
        vpc_id="vpc-12345",
        availability_zones=["eu-west-2a", "eu-west-2b"],
        private_subnet_ids=["subnet-private-a", "subnet-private-b"],
        isolated_subnet_ids=["subnet-isolated-a", "subnet-isolated-b"],
    )
    bastion_sg = ec2.SecurityGroup(harness, "BastionSg", vpc=vpc)
    task_sg = ec2.SecurityGroup(harness, "TaskSg", vpc=vpc)

    storage = StorageStack(app, "Storage", config=config, env=env)
    neptune = NeptuneStack(
        app, "Neptune", config=config, vpc=vpc, bastion_security_group=bastion_sg, task_security_group=task_sg, env=env
    )
    opensearch = OpenSearchStack(app, "OpenSearch", config=config, env=env)
    deployment_config = DeploymentConfig.from_dict(
        env,
        {
            "domain_name": "example.com",
            "vpc_id": "vpc-12345",
            "ecs_arn": "arn:aws:ecs:eu-west-2:123456789012:cluster/shared-cluster",
            "cognito_user_pool_id": "pool",
            "waf_arn": "waf",
            "waf_big_upload_arn": "waf-big",
            "logs_bucket_name": "logs",
        },
    )
    stack = PipelineTaskStack(
        app,
        "PipelineTask",
        config=config,
        deployment_config=deployment_config,
        source_buckets=[SOURCE_BUCKET],
        task_security_group=task_sg,
        storage=storage,
        neptune=neptune,
        opensearch=opensearch,
        vpc=None if lookup_vpc else vpc,
        env=env,
    )
    return Built(assertions.Template.from_stack(stack), stack, outdir, config)


@pytest.fixture
def dev(tmp_path):
    return _build(DEV, tmp_path / "dev")


@pytest.fixture
def prod(tmp_path):
    return _build(PROD, tmp_path / "prod")


def _statements(template: assertions.Template, role_logical_prefix: str = "TaskRole") -> list[dict]:
    """All policy statements attached to the task role."""
    statements = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        if any(role_logical_prefix in str(role) for role in policy["Properties"]["Roles"]):
            statements.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return statements


def _actions(statement: dict) -> list[str]:
    actions = statement["Action"]
    return [actions] if isinstance(actions, str) else actions


def _statement_with_sid(template: assertions.Template, sid: str) -> dict | None:
    return next((s for s in _statements(template) if s.get("Sid") == sid), None)


# --- task definition ---


@pytest.mark.parametrize("fixture,phase", [("dev", "dev"), ("prod", "prod")])
def test_task_definition_is_a_fargate_x86_task_of_2_vcpu_and_8gb(request, fixture, phase):
    built = request.getfixturevalue(fixture)

    built.template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "Family": f"dia-pipeline-task-{phase}",
            "Cpu": "2048",
            "Memory": "8192",
            "NetworkMode": "awsvpc",
            "RequiresCompatibilities": ["FARGATE"],
            "RuntimePlatform": {"CpuArchitecture": "X86_64", "OperatingSystemFamily": "LINUX"},
        },
    )


def test_container_leaves_the_dia_entrypoint_alone_and_is_told_where_its_config_is(dev):
    (task_definition,) = dev.template.find_resources("AWS::ECS::TaskDefinition").values()
    (container,) = task_definition["Properties"]["ContainerDefinitions"]

    assert "EntryPoint" not in container
    assert "Command" not in container
    assert container["Environment"] == [{"Name": "DIA_RUNTIME_CONFIG", "Value": "dia-runtime-config-dev"}]


def test_container_logs_to_the_log_group(dev):
    (task_definition,) = dev.template.find_resources("AWS::ECS::TaskDefinition").values()
    (container,) = task_definition["Properties"]["ContainerDefinitions"]

    assert container["LogConfiguration"]["LogDriver"] == "awslogs"
    assert container["LogConfiguration"]["Options"]["awslogs-stream-prefix"] == "pipeline"


# --- image ---


def _docker_asset(built: Built) -> dict:
    manifest = json.loads((built.outdir / "PipelineTask.assets.json").read_text())
    (asset,) = manifest["dockerImages"].values()
    return asset["source"]


def test_image_is_built_from_the_task_dockerfile_for_x86(dev):
    source = _docker_asset(dev)

    assert source["dockerFile"] == "task/Dockerfile"
    assert source["platform"] == "linux/amd64"
    assert source["dockerBuildArgs"]["DIA_VERSION"]


def test_image_build_context_only_has_what_the_build_needs(dev):
    staged = dev.outdir / _docker_asset(dev)["directory"]
    top_level = {path.name for path in staged.iterdir()}

    # CDK copies .dockerignore along with the files, so the build applies it too.
    assert top_level == {".dockerignore", "pyproject.toml", "uv.lock", "README.md", "src", "task"}
    assert {path.name for path in (staged / "task").iterdir()} == {"Dockerfile"}
    assert not (staged / "src" / "dia" / "_version.py").exists()


# --- roles ---


@pytest.mark.parametrize("fixture,phase,account", [("dev", "dev", DEV.value), ("prod", "prod", PROD.value)])
def test_roles_have_fixed_names_and_the_permissions_boundary(request, fixture, phase, account):
    built = request.getfixturevalue(fixture)
    boundary = f"arn:aws:iam::{account}:policy/DenyUserPermissionsPolicy"

    for name in (f"dia-pipeline-task-{phase}", f"dia-pipeline-task-execution-{phase}"):
        built.template.has_resource_properties("AWS::IAM::Role", {"RoleName": name, "PermissionsBoundary": boundary})


def test_roles_can_only_be_assumed_by_ecs_tasks_in_this_account(dev):
    for role in dev.template.find_resources("AWS::IAM::Role").values():
        if role["Properties"].get("RoleName", "").startswith("dia-pipeline-task"):
            (statement,) = role["Properties"]["AssumeRolePolicyDocument"]["Statement"]
            assert statement["Principal"] == {"Service": "ecs-tasks.amazonaws.com"}
            assert statement["Condition"] == {"StringEquals": {"aws:SourceAccount": DEV.value}}


# --- task role permissions ---


def test_task_role_can_use_the_ledger(dev):
    actions = {a for s in _statements(dev.template) for a in _actions(s) if a.startswith("dynamodb:")}

    assert "dynamodb:DescribeTable" in actions
    assert "dynamodb:BatchGetItem" in actions
    assert "dynamodb:PutItem" in actions


def test_task_role_can_read_and_write_four_pipeline_buckets_and_only_read_the_others(dev):
    s3_statements = [s for s in _statements(dev.template) if any(a.startswith("s3:") for a in _actions(s))]
    writers = [s for s in s3_statements if any(a.startswith("s3:PutObject") for a in _actions(s))]
    readers = [s for s in s3_statements if s not in writers]

    assert len(writers) == 4
    assert len(readers) == 2  # agent reports and DBR reports
    for reader in readers:
        assert not any(a.startswith(("s3:Put", "s3:Delete")) for a in _actions(reader))


def test_task_role_can_reach_every_bucket_preflight_checks(dev):
    """Preflight calls head_bucket on every Bucket, so the task role needs access to each one."""
    granted = json.dumps(
        [s["Resource"] for s in _statements(dev.template) if any(a.startswith("s3:") for a in _actions(s))]
    )
    storage_buckets = dev.stack.node.scope.node.find_child("Storage")
    template = assertions.Template.from_stack(storage_buckets)
    for logical_id in template.find_resources("AWS::S3::Bucket"):
        assert logical_id in granted, f"task role has no access to {logical_id}"


def test_task_role_can_use_neptune(dev):
    statement = _statement_with_sid(dev.template, "UseNeptune")

    assert statement is not None
    assert set(_actions(statement)) == {
        "neptune-db:GetEngineStatus",
        "neptune-db:ReadDataViaQuery",
        "neptune-db:WriteDataViaQuery",
        "neptune-db:DeleteDataViaQuery",
    }
    resource = json.dumps(statement["Resource"])
    assert f"arn:aws:neptune-db:eu-west-2:{DEV.value}:" in resource


def test_task_role_can_read_the_runtime_config_parameter(dev):
    reads = [s for s in _statements(dev.template) if any(a.startswith("ssm:GetParameter") for a in _actions(s))]

    assert len(reads) == 1


def test_in_dev_the_task_role_assumes_the_cross_account_role_and_does_not_read_source_buckets_directly(dev):
    statement = _statement_with_sid(dev.template, "AssumeSourceDataReadRole")

    assert statement is not None
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Resource"] == CROSS_ACCOUNT_ROLE  # as the shared library builds it
    assert SOURCE_BUCKET not in json.dumps(_statements(dev.template))


def test_in_prod_the_task_role_reads_source_buckets_directly_and_assumes_no_role(prod):
    assert _statement_with_sid(prod.template, "AssumeSourceDataReadRole") is None
    assert not any("sts:AssumeRole" in _actions(s) for s in _statements(prod.template))
    assert SOURCE_BUCKET in json.dumps(_statements(prod.template))


def test_in_prod_the_task_role_cannot_write_to_source_buckets(prod):
    for statement in _statements(prod.template):
        if SOURCE_BUCKET in json.dumps(statement.get("Resource")):
            assert not any(a.startswith("s3:Put") or a.startswith("s3:Delete") for a in _actions(statement))


# --- logs ---


@pytest.mark.parametrize("fixture,phase,policy", [("dev", "dev", "Delete"), ("prod", "prod", "Retain")])
def test_log_group_keeps_90_days_and_is_only_retained_in_prod(request, fixture, phase, policy):
    built = request.getfixturevalue(fixture)

    built.template.has_resource(
        "AWS::Logs::LogGroup",
        {
            "Properties": {"LogGroupName": f"/dia-task-{phase}", "RetentionInDays": 90},
            "DeletionPolicy": policy,
        },
    )


# --- runtime config parameter ---


def _parameter_json_text(built: Built) -> str:
    """The parameter value with any CloudFormation reference replaced by a marker."""
    (parameter,) = built.template.find_resources("AWS::SSM::Parameter").values()
    value = parameter["Properties"]["Value"]
    parts = value["Fn::Join"][1] if isinstance(value, dict) else [value]
    return "".join(part if isinstance(part, str) else "<ref>" for part in parts)


@pytest.mark.parametrize("fixture,phase", [("dev", "dev"), ("prod", "prod")])
def test_runtime_config_parameter_has_the_phase_name(request, fixture, phase):
    built = request.getfixturevalue(fixture)

    built.template.has_resource_properties("AWS::SSM::Parameter", {"Name": f"dia-runtime-config-{phase}"})


def test_runtime_config_parameter_has_exactly_the_fields_of_the_model(dev):
    keys = set(re.findall(r'"([a-z_]+)":', _parameter_json_text(dev)))

    assert keys == set(RuntimeConfig.model_fields)


def test_runtime_config_parameter_holds_the_opensearch_collection_endpoint(dev):
    (parameter,) = dev.template.find_resources("AWS::SSM::Parameter").values()

    assert "CollectionEndpoint" in json.dumps(parameter["Properties"]["Value"])


def test_runtime_config_parameter_holds_the_cluster_name_and_private_subnets(dev):
    text = _parameter_json_text(dev)

    assert '"cluster_name":"shared-cluster"' in text
    assert '"subnet-private-a"' in text
    assert '"subnet-private-b"' in text
    assert "subnet-isolated" not in text


def test_runtime_config_parameter_holds_the_cross_account_role_in_dev(dev):
    assert f'"cross_account_role_arn":"{CROSS_ACCOUNT_ROLE}"' in _parameter_json_text(dev)


def test_runtime_config_parameter_omits_the_cross_account_role_in_prod(prod):
    assert "cross_account_role_arn" not in _parameter_json_text(prod)


def test_the_task_is_pointed_at_the_parameter_it_can_read(dev):
    (parameter,) = dev.template.find_resources("AWS::SSM::Parameter").values()
    (task_definition,) = dev.template.find_resources("AWS::ECS::TaskDefinition").values()
    (container,) = task_definition["Properties"]["ContainerDefinitions"]

    assert container["Environment"][0]["Value"] == parameter["Properties"]["Name"]


def test_outputs_the_role_and_parameter_name(dev):
    outputs = dev.template.find_outputs("*")

    assert any("TaskRoleArn" in key for key in outputs)
    assert any("RuntimeConfigParameterName" in key for key in outputs)


# --- shared VPC ---


def test_without_a_vpc_given_the_stack_looks_up_the_shared_vpc_by_id(tmp_path):
    built = _build(DEV, tmp_path / "lookup", lookup_vpc=True)

    manifest = json.loads((built.outdir / "manifest.json").read_text())
    lookups = [m for m in manifest.get("missing", []) if m["provider"] == "vpc-provider"]

    assert any(m["props"]["filter"] == {"vpc-id": "vpc-12345"} for m in lookups)
