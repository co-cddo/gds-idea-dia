#!/usr/bin/env python3
"""CDK app entry point for DIA infrastructure."""

import os

import aws_cdk as cdk
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig

app = cdk.App()

cdk_env = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

# Phase is resolved automatically from the authenticated AWS account.
# No --context flag needed — DeploymentEnvironment maps account → phase.
environment = DeploymentEnvironment.from_cdk_env(cdk_env)
config = AppConfig(phase=environment.short_name)

# Stacks will be added here as they are implemented
# e.g. StorageStack(app, config.resource_name("storage"), config=config, env=env)

app.synth()
