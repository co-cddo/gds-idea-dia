"""Runtime configuration for the dia agent.

All settings are read from environment variables
at import time via pydantic-settings.

Usage:
    from dia.config import settings

"""

import json

from pydantic import Field, PrivateAttr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from dia.clients.secrets import get_secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- Bedrock model IDs and region --
    aws_region: str = Field(default="eu-west-2")
    model_id: str = Field(default="global.anthropic.claude-sonnet-5")

    # -- Athena - contracts --
    contracts_db: str = Field(default="assurance_contracts")
    contracts_table: str = Field(default="extracted_contracts")
    contracts_workgroup: str = Field(default="assurance-contracts")

    # -- Athena - GATS spend controls --
    gats_db: str = Field(default="gats-assurance-ai")
    gats_workgroup: str = Field(default="athena-gats-snapshot-schema-in-code-dev-wg-cleaned-v2")
    gats_output: str = Field(default="s3://performanceandassuranceat-athenaresultsbucket87993-6swdwdgurxgq/athena/dev/")

    # -- Athena — GATS Service Standard assessments --
    gats_service_db: str = Field(default="gats-assurance")
    gats_service_table: str = Field(default="service_assessments_snapshot20251217")

    # -- Secrets Manager (currently hardcoded for local runs. To update when agent is deployed) --
    tavily_secret_name: str = Field(default="dia-tavily-dev")
    kb_arns_secret_name: str = Field(default="dia-kb-arns-dev")
    neptune_endpoint_secret_name: str = Field(default="dia-neptune-endpoint-dev")
    aoss_endpoint_secret_name: str = Field(default="dia-aoss-endpoint-dev")

    # -- MCP server defaults --
    mcp_port: int = Field(default=8000)

    # -- Neptune port --

    neptune_port: int = Field(default=8182)
    timeout: float = Field(default=30.0)
    host: str = Field(default="127.0.0.1")

    @computed_field
    @property
    def mcp_url(self) -> str:
        return f"http://127.0.0.1:{self.mcp_port}/mcp/"

    _secret_cache: dict[str, str] = PrivateAttr(default_factory=dict)

    def _resolve_secret(self, secret_name: str) -> str:
        """Fetch a plain-string secret once, cached by secret name."""
        if secret_name not in self._secret_cache:
            self._secret_cache[secret_name] = get_secret(secret_name, region=self.aws_region)
        return self._secret_cache[secret_name]

    @property
    def kb_arns(self) -> dict[str, str]:
        """Bedrock Knowledge Base IDs/ARNs, keyed without the 'kb_' prefix."""
        raw = self._resolve_secret(self.kb_arns_secret_name)
        parsed = json.loads(raw)
        return {key.removeprefix("kb_"): value for key, value in parsed.items()}

    @property
    def tavily_api_key(self) -> str:
        """Tavily API key, resolved from Secrets Manager."""
        return self._resolve_secret(self.tavily_secret_name)

    @property
    def neptune_endpoint(self) -> str:
        """Neptune cluster endpoint hostname, resolved from Secrets Manager."""
        return self._resolve_secret(self.neptune_endpoint_secret_name)

    @property
    def aoss_endpoint(self) -> str:
        """OpenSearch (AOSS) collection endpoint hostname, resolved from Secrets Manager."""
        return self._resolve_secret(self.aoss_endpoint_secret_name)


settings = Settings()
