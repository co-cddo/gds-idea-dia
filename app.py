#!/usr/bin/env python3
"""CDK app entry point for DIA infrastructure."""

import os

import aws_cdk as cdk
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig
from stacks.storage import StorageStack

app = cdk.App()

cdk_env = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ["CDK_DEFAULT_REGION"],
)

# Phase is resolved automatically from the authenticated AWS account.
environment = DeploymentEnvironment.from_cdk_env(cdk_env)
config = AppConfig(environment=environment)

StorageStack(app, config.resource_name("storage"), config=config, env=cdk_env)

app.synth()
