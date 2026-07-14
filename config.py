"""CDK configuration for DIA.

Phase-resolved infrastructure config. Phase is resolved automatically
from the authenticated AWS account via DeploymentEnvironment.
"""

from __future__ import annotations

from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import BaseModel, computed_field


class AppConfig(BaseModel):
    """Root CDK configuration.

    Takes a DeploymentEnvironment enum directly — resolved in app.py
    from the authenticated AWS account.

    Usage:
        from gds_idea_cdk_constructs import DeploymentEnvironment
        config = AppConfig(environment=DeploymentEnvironment.DEVELOPMENT)
        config.bucket("graph-raw")  # -> "gds-idea-dia-graph-raw-dev"
        config.account_number       # -> "992382722318"
    """

    environment: DeploymentEnvironment = DeploymentEnvironment.DEVELOPMENT
    project: str = "dia"
    team: str = "gds-idea"
    region: str = "eu-west-2"

    @computed_field
    @property
    def phase(self) -> str:
        """Short phase name (dev/prod) derived from environment."""
        return self.environment.short_name

    @computed_field
    @property
    def account_number(self) -> str:
        """AWS account number for the current environment."""
        return self.environment.value

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
