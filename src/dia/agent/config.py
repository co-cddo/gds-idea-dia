"""Runtime configuration for the dia agent.

All settings are read from environment variables
at import time via pydantic-settings.

Usage:
    from dia.config import settings

"""

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- Bedrock model IDs and region --
    aws_region: str = Field(default="eu-west-2")
    model_id: str = Field(default="global.anthropic.claude-sonnet-5")

    # -- Endpoints --

    # -- Athena - contracts --
    contracts_db: str = Field(default="assurance_contracts")
    contracts_table: str = Field(default="extracted_contracts")
    contracts_group: str = Field(default="assurance-contracts")

    # -- Athena - GATS spend controls --
    gats_db: str = Field(default="gats-assurance-ai")
    gats_workgroup: str = Field(default="athena-gats-snapshot-schema-in-code-dev-wg-cleaned-v2")
    gats_output: str = Field(default="s3://performanceandassuranceat-athenaresultsbucket87993-6swdwdgurxgq/athena/dev/")

    # -- Athena — GATS Service Standard assessments --
    gats_service_db: str = Field(default="gats-assurance")
    gats_service_table: str = Field(default="service_assessments_snapshot20251217")

    # -- Secrets Manager --
    tavily_secret_name: str = Field(default="")
    kb_gats_business_cases: str = Field(default="")
    kb_sr25_bids: str = Field(default="")
    kb_sr21_bids: str = Field(default="")
    kb_nao_reports: str = Field(default="")
    kb_efficiency_reports: str = Field(default="")

    @computed_field
    @property
    def kb_ids(self) -> dict[str, str]:
        return {
            "gats_business_cases": self.kb_gats_business_cases,
            "sr25_bids": self.kb_sr25_bids,
            "sr21_bids": self.kb_sr21_bids,
            "nao_reports": self.kb_nao_reports,
            "efficiency_reports": self.kb_efficiency_reports,
        }

    # -- MCP server defaults --
    mcp_port: int = Field(default=8000)

    @computed_field
    @property
    def mcp_url(self) -> str:
        return f"http://127.0.0.1:{self.mcp_port}/mcp/"


settings = Settings()
