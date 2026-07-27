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

    @computed_field
    @property
    def tavily_secret(self) -> str:
        """Secrets Manager name for the Tavily API key."""
        return self.resource_name("tavily")

    @computed_field
    @property
    def neptune_endpoint_secret(self) -> str:
        """Secrets Manager name for Nepture endpoint."""
        return self.resource_name("neptune-endpoint")

    @computed_field
    @property
    def aoss_endpoint_secret(self) -> str:
        """Secrets Manager name for OpenSearch endpoint."""
        return self.resource_name("aoss-endpoint")

    @computed_field
    @property
    def kb_arns(self) -> str:
        """Secrets Manager name for the Bedrock Knowledge Base ARNs (one secret, one key per KB)."""
        return self.resource_name("kb-arns")


class StackId:
    """Generates consistent CDK stack IDs for a given project and phase.

    Same underlying pattern as AppConfig._resource_name() —
    {project}-{name}-{phase}. Kept as a separate callable for
    ergonomics in app.py rather than calling config._resource_name()
    at every stack instantiation site.

    Usage:
        sid = StackId.from_config(config)
        sid("StorageStack")  # -> "dia-StorageStack-dev"
    """

    def __init__(self, project: str, phase: str) -> None:
        self._project = project
        self._phase = phase

    def __call__(self, name: str) -> str:
        return f"{self._project}-{name}-{self._phase}"

    @classmethod
    def from_config(cls, config: AppConfig) -> StackId:
        """Create a StackId from an AppConfig instance."""
        return cls(config.project, config.phase)
