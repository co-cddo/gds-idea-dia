#!/usr/bin/env python3
"""CDK app entry point for DIA infrastructure."""

import os

import aws_cdk as cdk
from gds_idea_cdk_constructs import DeploymentEnvironment, IdeaTags
from gds_idea_cdk_constructs.config import DeploymentConfig

from config import AppConfig
from dia.naming import PROJECT
from dia.sources.known import get_source
from stacks.bastion import BastionStack
from stacks.neptune import NeptuneStack
from stacks.networking import NetworkingStack
from stacks.opensearch import OpenSearchStack
from stacks.pipeline_task import PipelineTaskStack
from stacks.secrets import SecretsStack
from stacks.storage import StorageStack

app = cdk.App()

cdk_env = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

# Phase is resolved automatically from the authenticated AWS account.
environment = DeploymentEnvironment.from_cdk_env(cdk_env)
config = AppConfig(environment=environment)

# Shared org VPC — resolved via SSM Parameter Store (/gds-idea-vpc).
deployment_config = DeploymentConfig(cdk_env)

IdeaTags(
    environment=environment,
    app_name=PROJECT,
    repository="gds-idea-dia",
).apply(app)

storage_stack = StorageStack(app, config.names("storage"), config=config, env=cdk_env)

SecretsStack(app, config.names("SecretStack"), config=config, env=cdk_env)

# Stack order matters — strictly one-directional dependency chain:
# NetworkingStack → BastionStack → NeptuneStack
networking_stack = NetworkingStack(
    app,
    config.names("networking"),
    config=config,
    vpc_id=deployment_config.vpc_id,
    env=cdk_env,
)

bastion_stack = BastionStack(
    app,
    config.names("bastion"),
    config=config,
    vpc=networking_stack.vpc,
    eice_security_group=networking_stack.eice_security_group,
    env=cdk_env,
)

neptune_stack = NeptuneStack(
    app,
    config.names("neptune"),
    config=config,
    vpc=networking_stack.vpc,
    bastion_security_group=bastion_stack.bastion_security_group,
    task_security_group=networking_stack.task_security_group,
    env=cdk_env,
)

# Pipeline tasks: the image, task definition, roles and runtime config.
# In dev, source data in the production account is read through the shared
# cross-account role (None in prod, where the source buckets are read directly).
pipeline_task_stack = PipelineTaskStack(
    app,
    config.names("pipeline-task"),
    config=config,
    cluster_name=deployment_config.cluster_name,
    cross_account_role_arn=deployment_config.cross_account_role_arn,
    source_buckets=[get_source("gats-business-cases").bucket],
    vpc=networking_stack.vpc,
    task_security_group=networking_stack.task_security_group,
    storage=storage_stack,
    neptune=neptune_stack,
    env=cdk_env,
)
pipeline_task_stack.add_dependency(storage_stack)
pipeline_task_stack.add_dependency(networking_stack)
pipeline_task_stack.add_dependency(neptune_stack)

# OpenSearch Serverless — standalone (no VPC dependency), public endpoint
# restricted by IAM data-access policy.
OpenSearchStack(app, config.names("opensearch"), config=config, env=cdk_env)

app.synth()
