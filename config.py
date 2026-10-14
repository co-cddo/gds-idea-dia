"""CDK configuration for DIA.

Phase-resolved infrastructure config. Phase is resolved automatically
from the authenticated AWS account via DeploymentEnvironment.
"""

from __future__ import annotations

from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import BaseModel, computed_field

from dia.naming import REGION, Names


class AppConfig(BaseModel):
    """Root CDK configuration.

    Takes a DeploymentEnvironment enum directly — resolved in app.py
    from the authenticated AWS account.

    Usage:
        from gds_idea_cdk_constructs import DeploymentEnvironment
        config = AppConfig(environment=DeploymentEnvironment.DEVELOPMENT)
        config.names.bucket(Bucket.GRAPH_RAW)  # -> "gds-idea-dia-graph-raw-dev"
        config.names("neptune")                # -> "dia-neptune-dev"
        config.account_number                  # -> "992382722318"
    """

    environment: DeploymentEnvironment = DeploymentEnvironment.DEVELOPMENT
    region: str = REGION

    @property
    def names(self) -> Names:
        """Resource and stack names for this environment."""
        return Names(self.environment)

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

    @computed_field
    @property
    def tavily_secret(self) -> str:
        """Secrets Manager name for the Tavily API key."""
        return self.names("tavily")

    @computed_field
    @property
    def neptune_endpoint_secret(self) -> str:
        """Secrets Manager name for Nepture endpoint."""
        return self.names("neptune-endpoint")

    @computed_field
    @property
    def aoss_endpoint_secret(self) -> str:
        """Secrets Manager name for OpenSearch endpoint."""
        return self.names("aoss-endpoint")

    @computed_field
    @property
    def kb_arns(self) -> str:
        """Secrets Manager name for the Bedrock Knowledge Base ARNs (one secret, one key per KB)."""
        return self.names("kb-arns")
