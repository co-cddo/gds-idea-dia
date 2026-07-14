#!/usr/bin/env python3
"""CDK app entry point for DIA infrastructure."""

import aws_cdk as cdk

from config import AppConfig

app = cdk.App()

phase = app.node.try_get_context("phase") or "dev"
config = AppConfig(phase=phase)

env = cdk.Environment(
    account=config.account_number,
    region=config.region,
)

# Stacks will be added here as they are implemented
# e.g. StorageStack(app, config.resource_name("storage"), config=config, env=env)

app.synth()
