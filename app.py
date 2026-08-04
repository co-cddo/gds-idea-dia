#!/usr/bin/env python3
"""CDK app entry point for DIA infrastructure."""

import os

import aws_cdk as cdk
from gds_idea_cdk_constructs import DeploymentEnvironment
from gds_idea_cdk_constructs.config import DeploymentConfig

from config import AppConfig, StackId
from stacks.bastion import BastionStack
from stacks.neptune import NeptuneStack
from stacks.networking import NetworkingStack
from stacks.opensearch import OpenSearchStack
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
sid = StackId.from_config(config)

# Shared org VPC — resolved via SSM Parameter Store (/gds-idea-vpc).
deployment_config = DeploymentConfig(cdk_env)

StorageStack(app, config.resource_name("storage"), config=config, env=cdk_env)

SecretsStack(app, sid("SecretStack"), config=config, env=cdk_env)

# Stack order matters — strictly one-directional dependency chain:
# NetworkingStack → BastionStack → NeptuneStack
networking_stack = NetworkingStack(
    app,
    config.resource_name("networking"),
    config=config,
    vpc_id=deployment_config.vpc_id,
    env=cdk_env,
)

bastion_stack = BastionStack(
    app,
    config.resource_name("bastion"),
    config=config,
    vpc=networking_stack.vpc,
    eice_security_group=networking_stack.eice_security_group,
    env=cdk_env,
)

NeptuneStack(
    app,
    config.resource_name("neptune"),
    config=config,
    vpc=networking_stack.vpc,
    bastion_security_group=bastion_stack.bastion_security_group,
    env=cdk_env,
)

# OpenSearch Serverless — standalone (no VPC dependency), public endpoint
# restricted by IAM data-access policy.
OpenSearchStack(app, config.resource_name("opensearch"), config=config, env=cdk_env)

app.synth()
