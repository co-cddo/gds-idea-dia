"""CDK stack for the DIA pipeline task: the image, task definition, roles and runtime config.

Pipeline commands run as ECS Fargate tasks on the shared GDS IDEA cluster. This
stack defines what a task is (image, size, logging), what it may do (its IAM
roles) and what it needs to know (the runtime config parameter). Starting tasks
is done from the CLI.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from gds_idea_cdk_constructs import DeploymentConfig, DeploymentEnvironment

from config import AppConfig
from dia import __version__
from dia.runtime_config import RUNTIME_CONFIG_ENV_VAR, RUNTIME_CONFIG_RESOURCE
from stacks.neptune import NeptuneStack
from stacks.opensearch import OpenSearchStack
from stacks.shared.iam import permissions_boundary
from stacks.storage import StorageStack

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

# Neptune data actions the pipeline uses. Later stages that need more (for example
# query status or cancellation) add them here.
_NEPTUNE_ACTIONS = [
    "neptune-db:GetEngineStatus",
    "neptune-db:ReadDataViaQuery",
    "neptune-db:WriteDataViaQuery",
    "neptune-db:DeleteDataViaQuery",
]


class PipelineTaskStack(cdk.Stack):
    """Creates the pipeline task definition and everything it needs to run.

    Resources:
        - Container image, built from task/Dockerfile for x86_64
        - Fargate task definition (2 vCPU, 8GB) with one container whose
          entrypoint is `dia`. A task supplies the command.
        - Task role: the permissions the pipeline code has while it runs
        - Execution role: lets ECS pull the image and write logs
        - Log group for task output
        - SSM parameter holding the runtime config (see dia.runtime_config)

    The tasks' security group is created in NetworkingStack, and NeptuneStack
    allows it in on port 8182, which avoids a dependency cycle between stacks.

    The task role can assume the shared cross-account role in dev, where source
    data in the production account is read through that role. In prod it reads
    the source buckets directly.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: AppConfig,
        deployment_config: DeploymentConfig,
        source_buckets: Sequence[str],
        task_security_group: ec2.ISecurityGroup,
        storage: StorageStack,
        neptune: NeptuneStack,
        opensearch: OpenSearchStack,
        vpc: ec2.IVpc | None = None,
        **kwargs,
    ) -> None:
        """Create the stack.

        Args:
            scope: The CDK app.
            construct_id: The stack ID.
            config: The CDK config.
            deployment_config: The shared deployment config, for the ECS cluster, the VPC
                and the cross-account role to assume to read production source data
                (None in prod, where the source buckets are read directly).
            source_buckets: Names of the source data buckets that tasks read.
            task_security_group: Security group for tasks.
            storage: The storage stack, for the ledger table and buckets.
            neptune: The Neptune stack, for the cluster.
            opensearch: The OpenSearch stack, for the collection endpoint.
            vpc: The shared VPC. Looked up from `deployment_config` if not given (tests
                give one). Tasks run in its private subnets.
            **kwargs: Passed to the base stack.
        """
        super().__init__(scope, construct_id, **kwargs)

        is_dev = config.environment == DeploymentEnvironment.DEVELOPMENT
        log_removal = cdk.RemovalPolicy.DESTROY if is_dev else cdk.RemovalPolicy.RETAIN
        config_parameter_name = config.names(RUNTIME_CONFIG_RESOURCE)
        vpc = vpc or ec2.Vpc.from_lookup(self, "SharedVpc", vpc_id=deployment_config.vpc_id)

        # --- Roles ---
        self.task_role = iam.Role(
            self,
            "TaskRole",
            role_name=config.names("pipeline-task"),
            description="Assumed by DIA pipeline tasks while they run.",
            assumed_by=iam.ServicePrincipal(
                "ecs-tasks.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": config.account_number}},
            ),
            permissions_boundary=permissions_boundary(self, "TaskPermissionsBoundary", config=config),
        )
        self.execution_role = iam.Role(
            self,
            "ExecutionRole",
            role_name=config.names("pipeline-task-execution"),
            description="Used by ECS to pull the DIA pipeline image and write task logs.",
            assumed_by=iam.ServicePrincipal(
                "ecs-tasks.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": config.account_number}},
            ),
            permissions_boundary=permissions_boundary(self, "ExecutionPermissionsBoundary", config=config),
        )

        # --- Logs ---
        self.log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/{config.names('task')}",
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=log_removal,
        )

        # --- Task definition ---
        # 2 vCPU and 8GB for now. Tune once real stages show what they need; the size can
        # also be overridden when a task is started.
        self.task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            family=config.names("pipeline-task"),
            cpu=2048,
            memory_limit_mib=8192,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            task_role=self.task_role,
            execution_role=self.execution_role,
        )
        self.task_definition.add_container(
            "Pipeline",
            image=ecs.ContainerImage.from_asset(
                str(_REPOSITORY_ROOT),
                file="task/Dockerfile",
                platform=ecr_assets.Platform.LINUX_AMD64,
                build_args={"DIA_VERSION": __version__},
                # What goes into the build context is listed in the repository's .dockerignore.
                ignore_mode=cdk.IgnoreMode.DOCKER,
            ),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="pipeline", log_group=self.log_group),
            # The one thing a task is told: where to find the rest of its configuration.
            environment={RUNTIME_CONFIG_ENV_VAR: config_parameter_name},
        )

        # --- Runtime config ---
        # The keys must match dia.runtime_config.RuntimeConfig exactly (a test checks this).
        self.runtime_config_parameter = ssm.StringParameter(
            self,
            "RuntimeConfigParameter",
            parameter_name=config_parameter_name,
            description="Runtime configuration for DIA pipeline tasks and the CLI (see dia.runtime_config).",
            string_value=self.to_json_string(
                {
                    "neptune_endpoint": neptune.cluster.attr_endpoint,
                    "neptune_port": cdk.Token.as_number(neptune.cluster.attr_port),
                    "opensearch_endpoint": opensearch.collection.attr_collection_endpoint,
                    "cluster_name": deployment_config.cluster_name,
                    "task_definition_arn": self.task_definition.task_definition_arn,
                    "subnet_ids": [subnet.subnet_id for subnet in vpc.private_subnets],
                    "security_group_id": task_security_group.security_group_id,
                    "log_group": self.log_group.log_group_name,
                    "cross_account_role_arn": deployment_config.cross_account_role_arn,
                }
            ),
        )

        # --- Task role permissions ---
        storage.ledger_table.grant_read_write_data(self.task_role)
        for bucket in (
            storage.text_extracted_bucket,
            storage.graph_raw_bucket,
            storage.graph_validated_bucket,
            storage.batch_bucket,
        ):
            bucket.grant_read_write(self.task_role)
        # Read-only: preflight checks that every bucket is reachable.
        storage.agent_reports_bucket.grant_read(self.task_role)
        storage.dbr_reports_bucket.grant_read(self.task_role)

        self.runtime_config_parameter.grant_read(self.task_role)

        self.task_role.add_to_policy(
            iam.PolicyStatement(
                sid="UseNeptune",
                actions=_NEPTUNE_ACTIONS,
                resources=[
                    f"arn:aws:neptune-db:{config.region}:{config.account_number}"
                    f":{neptune.cluster.attr_cluster_resource_id}/*"
                ],
            )
        )

        if deployment_config.cross_account_role_arn:
            self.task_role.add_to_policy(
                iam.PolicyStatement(
                    sid="AssumeSourceDataReadRole",
                    actions=["sts:AssumeRole"],
                    resources=[deployment_config.cross_account_role_arn],
                )
            )
        else:
            for index, bucket_name in enumerate(source_buckets):
                s3.Bucket.from_bucket_name(self, f"SourceBucket{index}", bucket_name).grant_read(self.task_role)

        # --- Outputs ---
        cdk.CfnOutput(
            self,
            "TaskRoleArn",
            value=self.task_role.role_arn,
            description="Role the pipeline tasks run as",
        )
        cdk.CfnOutput(
            self,
            "RuntimeConfigParameterName",
            value=self.runtime_config_parameter.parameter_name,
            description="SSM parameter holding the runtime config",
        )
