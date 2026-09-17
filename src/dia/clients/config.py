"""Shared AWS access settings: which login, which region, which models.

Settings here can be set via environment variables or a local, git-ignored
`.env` file (environment variables always win over `.env`) — so anything
that uses this doesn't need the same `export` commands typed out every
session.

Two things are deliberately *not* here, and never should be:

- `RUN_LIVE_AWS_TESTS`: the live-AWS test suite's opt-in safety switch. It
  must stay a one-off `export`, never persisted, or it stops being an
  opt-in switch.
- Neptune/AOSS endpoints: resolved live via CloudFormation (see
  `dia.clients.cloudformation.resolve_stack_output`) rather than typed in —
  see that module's docstring for why.

Currently used by `tests/test_lexical_graph_integration.py`. Intended for
`src/dia/agent/` to adopt too, once its own config wiring lands (see
`pyproject.toml`'s per-file-ignores comment on `src/dia/agent/agents.py` —
that wiring is deliberately deferred to a separate PR, not done here).
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class AwsSettings(BaseSettings):
    """AWS login, region, and Bedrock model choices, shared across the project."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_profile: str | None = None
    aws_region: str = "eu-west-2"
    extraction_model: str = "eu.anthropic.claude-sonnet-4-6"
    response_model: str = "eu.anthropic.claude-sonnet-4-6"
    embeddings_model: str = "amazon.titan-embed-text-v2:0"
    phase: str = "dev"  # -> CloudFormation stacks dia-neptune-{phase} / dia-opensearch-{phase}

    def export_to_environ(self) -> None:
        """Push profile/region/model settings into `os.environ`.

        `graphrag_toolkit`'s `GraphRAGConfig` reads these directly from the
        environment — lazily, on first access, and only once — rather than
        accepting them as constructor arguments (see
        `graphrag_toolkit.lexical_graph.config`). Anything that builds a
        graph/vector store via `graphrag_toolkit` needs this step first.
        """
        if self.aws_profile:
            os.environ["AWS_PROFILE"] = self.aws_profile
        os.environ["AWS_REGION"] = self.aws_region
        os.environ["EXTRACTION_MODEL"] = self.extraction_model
        os.environ["RESPONSE_MODEL"] = self.response_model
        os.environ["EMBEDDINGS_MODEL"] = self.embeddings_model


aws_settings = AwsSettings()
