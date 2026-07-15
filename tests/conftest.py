import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig


@pytest.fixture
def synth():
    """Factory fixture that synthesises any CDK stack and returns its template."""

    def _synth(stack_class, environment=DeploymentEnvironment.DEVELOPMENT):
        config = AppConfig(environment=environment)
        app = cdk.App()
        stack = stack_class(
            app,
            "TestStack",
            config=config,
            env=cdk.Environment(account=config.account_number, region=config.region),
        )
        return assertions.Template.from_stack(stack)

    return _synth
