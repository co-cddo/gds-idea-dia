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

    # -- Bedrock model config --
    aws_region: str = Field(default="eu-west-2")
    model_id: str = Field(default="global.anthropic.claude-sonnet-5")
    model_max_tokens: int = Field(default=8000)
    model_temperature: float = Field(default=1.0)
    model_thinking_budget_tokens: int = Field(default=8192)
    model_thinking_effort: str = Field(default="high")
    model_thinking_display: str = Field(default="summarized")

    # -- Default persona hard gates --
    # NOTE: min_graph_calls / first_n_must_be_graph are temporarily relaxed to 0 while
    # Neptune is empty (graph queries return nothing useful right now, so forcing
    # the agent through them just burns tool calls/tokens). Restore to
    # min_graph_calls=5, first_n_must_be_graph=4 once Neptune has data.
    default_persona_min_words: int = Field(default=2_000)
    default_persona_min_graph_calls: int = Field(default=0)
    default_persona_first_n_must_be_graph: int = Field(default=0)
    default_persona_min_web_calls: int = Field(default=1)

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

    # -- Neptune SSH tunnel defaults --

    tunnel_port: int = Field(default=8182)
    tunnel_timeout: float = Field(default=30.0)
    tunnel_host: str = Field(default="127.0.0.1")

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
