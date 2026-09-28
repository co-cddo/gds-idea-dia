"""Settings for connecting to the graph toolkit's AWS-backed services.

`graphrag_toolkit` (Neptune + OpenSearch Serverless, via Bedrock) reads its
AWS login, region, and model choices lazily from the environment. This
class is the one place those values are defined, loadable from environment
variables or a local, git-ignored `.env` file (environment variables always
win over `.env`) — so anything that uses this doesn't need the same
`export` commands typed out every session.

Two things are deliberately *not* here, and never should be:

- `RUN_LIVE_AWS_TESTS`: the live-AWS test suite's opt-in safety switch. It
  must stay a one-off `export`, never persisted, or it stops being an
  opt-in switch.
- Neptune/AOSS endpoints: resolved live via CloudFormation (see
  `dia.clients.cloudformation.resolve_stack_output`) rather than typed in —
  see that module's docstring for why.

Currently used by `tests/test_lexical_graph_integration.py`. `src/dia/agent/`
doesn't use this yet — it has its own separate `aws_region`/`model_id`
fields in `dia.agent.config.Settings` — but this is written to be reusable
there too, since `dia.agent.stores.build_graph_store`/`build_vector_store`
go through the same `graphrag_toolkit` and need the same environment setup.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class GraphRagSettings(BaseSettings):
    """AWS login, region, and Bedrock model choices for graphrag_toolkit."""

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


graph_rag_settings = GraphRagSettings()
