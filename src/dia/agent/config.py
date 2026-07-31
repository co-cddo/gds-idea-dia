"""Runtime configuration for the dia agent.

All settings are read from environment variables
at import time via pydantic-settings.

Usage:
    from dia.config import settings

"""

import json

from pydantic import Field, computed_field
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

    # -- Secrets Manager --
    tavily_secret_name: str = Field(default="")
    kb_arns_secret_name: str = Field(default="")
    neptune_endpoint_secret_name: str = Field(default="")
    aoss_endpoint_secret_name: str = Field(default="")

    # -- MCP server defaults --
    mcp_port: int = Field(default=8000)

    @computed_field
    @property
    def mcp_url(self) -> str:
        return f"http://127.0.0.1:{self.mcp_port}/mcp/"

    @property
    def kb_arns(self) -> dict[str, str]:
        """Bedrock Knowledge Base IDs/ARNs, keyed without the 'kb_' prefix."""
        if self._kb_arns_cache is None:
            raw = get_secret(self.kb_arns_secret_name, region=self.aws_region)
            parsed = json.loads(raw)
            self._kb_arns_cache = {key.removeprefix("kb_"): value for key, value in parsed.items()}
        return self._kb_arns_cache

    @property
    def tavily_api_key(self) -> str:
        """Tavily API key, resolved from Secrets Manager."""
        if self._tavily_api_key_cache is None:
            self._tavily_api_key_cache = get_secret(self.tavily_secret_name, region=self.aws_region)
        return self._tavily_api_key_cache


settings = Settings()
