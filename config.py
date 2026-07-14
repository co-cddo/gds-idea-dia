"""CDK configuration for DIA.

Phase-resolved infrastructure config. Phase is determined by the
gds-idea-cdk-constructs DeploymentConfig mechanism, not cdk.json context.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field


class AppConfig(BaseModel):
    """Root CDK configuration.

    Usage:
        config = AppConfig(phase="dev")
        config.bucket("graph-raw")  # -> "gds-idea-dia-graph-raw-dev"
        config.account_number       # -> resolved from DeploymentEnvironment
    """

    phase: Literal["dev"] = "dev"
    project: str = "dia"
    team: str = "gds-idea"
    region: str = "eu-west-2"

    @computed_field
    @property
    def account_number(self) -> str:
        """AWS account number for the current phase.

        Resolved via gds-idea-cdk-constructs DeploymentEnvironment.
        """
        from gds_idea_cdk_constructs import DeploymentEnvironment

        mapping = {
            "dev": DeploymentEnvironment.DEVELOPMENT,
            "prod": DeploymentEnvironment.PRODUCTION,
        }
        return mapping[self.phase].value

    def bucket(self, purpose: str) -> str:
        """Generate a consistent S3 bucket name.

        Pattern: {team}-{project}-{purpose}-{phase}
        Example: gds-idea-dia-graph-raw-dev
        """
        return f"{self.team}-{self.project}-{purpose}-{self.phase}"

    def resource_name(self, resource: str) -> str:
        """Generate a consistent AWS resource name.

        Pattern: {project}-{resource}-{phase}
        Example: dia-neptune-dev
        """
        return f"{self.project}-{resource}-{self.phase}"
