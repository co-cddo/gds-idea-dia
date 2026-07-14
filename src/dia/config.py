"""Pipeline configuration for DIA.

Provides typed, validated configuration for the extraction pipeline.
Phase-resolved infrastructure values are derived from a single `phase` input.

Usage:
    from dia.config import PipelineConfig

    config = PipelineConfig(phase="dev")
    config.to_env_for_graphrag_toolkit()
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, computed_field

# ---------------------------------------------------------------------------
# Phase-specific lookup tables
# ---------------------------------------------------------------------------

_NEPTUNE_ENDPOINTS: dict[str, str] = {
    "dev": "db-neptune-ai-in-assurance-v3.cluster-ro-c3a42mmuka2e.eu-west-2.neptune.amazonaws.com",
}

_AOSS_ENDPOINTS: dict[str, str] = {
    "dev": "https://tam93zn67apwgk5pjg4i.eu-west-2.aoss.amazonaws.com",
}


# ---------------------------------------------------------------------------
# Bucket naming helper
# ---------------------------------------------------------------------------


def bucket_name(team: str, project: str, purpose: str, phase: str) -> str:
    """Generate consistent S3 bucket names.

    Pattern: {team}-{project}-{purpose}-{phase}
    Example: gds-idea-dia-graph-raw-dev
    """
    return f"{team}-{project}-{purpose}-{phase}"


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Configuration for the extraction pipeline.

    Only `phase` is required — everything else has validated defaults.
    Override any field via constructor args for testing or one-off runs.

    Phase-resolved fields (neptune_endpoint, aoss_endpoint, etc.) are
    derived from lookup tables. Add a "prod" entry to each table when
    production infrastructure is provisioned.
    """

    # --- Core ---
    phase: Literal["dev"] = "dev"
    project: str = "dia"
    team: str = "gds-idea"
    region: str = "eu-west-2"
    aws_profile: str = "default"

    # --- Models ---
    extraction_model: str = "eu.anthropic.claude-sonnet-4-6"
    response_model: str = "eu.anthropic.claude-sonnet-4-6"
    embeddings_model: str = "amazon.titan-embed-text-v2:0"
    max_tokens: int = Field(default=42768, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- Extraction tuning ---
    sentence_chunk_size: int = Field(default=7900, gt=0)
    sentence_chunk_overlap: int = Field(default=100, ge=0)
    semantic_buffer_size: int = Field(default=3, gt=0)
    semantic_breakpoint_threshold: int = Field(default=97, gt=0, le=100)
    extraction_batch_size: int = Field(default=20000, gt=0)
    max_batch_size: int = Field(default=40000, gt=0)
    num_iterations: int = Field(default=10, gt=0)
    num_samples: int = Field(default=40, gt=0)
    num_classifications: int = Field(default=50, gt=0)

    # --- Toolkit tuning ---
    extraction_num_workers: int = Field(default=1, gt=0)
    extraction_num_threads_per_worker: int = Field(default=2, gt=0)
    read_timeout: int = Field(default=600, gt=0)
    enable_cache: bool = True

    # --- Phase-resolved infrastructure ---

    @computed_field
    @property
    def neptune_endpoint(self) -> str:
        """Neptune cluster endpoint for the current phase."""
        return _NEPTUNE_ENDPOINTS[self.phase]

    @computed_field
    @property
    def aoss_endpoint(self) -> str:
        """OpenSearch Serverless endpoint for the current phase."""
        return _AOSS_ENDPOINTS[self.phase]

    @computed_field
    @property
    def graph_raw_bucket(self) -> str:
        """S3 bucket for raw extraction output."""
        return bucket_name(self.team, self.project, "graph-raw", self.phase)

    @computed_field
    @property
    def graph_validated_bucket(self) -> str:
        """S3 bucket for validated/normalised output."""
        return bucket_name(self.team, self.project, "graph-validated", self.phase)

    @computed_field
    @property
    def batch_bucket(self) -> str:
        """S3 bucket for Bedrock batch inference."""
        return bucket_name(self.team, self.project, "batch", self.phase)

    @computed_field
    @property
    def batch_role_arn(self) -> str:
        """IAM role ARN for Bedrock batch inference."""
        # TODO: derive from account lookup when prod exists
        return "arn:aws:iam::992382722318:role/BatchInferenceRole"

    # --- Helpers ---

    def bucket(self, purpose: str) -> str:
        """Generate a bucket name for this project/phase."""
        return bucket_name(self.team, self.project, purpose, self.phase)

    # --- Environment export ---

    def to_env_for_graphrag_toolkit(self) -> None:
        """Export configuration to os.environ for graphrag-toolkit.

        The graphrag-toolkit reads configuration from environment variables
        at runtime. This method bridges our typed config into that interface.
        Call this once before any graphrag-toolkit imports or operations.
        """
        os.environ["AWS_REGION"] = self.region
        os.environ["aws_profile"] = self.aws_profile
        os.environ["NEPTUNE_ENDPOINT"] = self.neptune_endpoint
        os.environ["AOSS_ENDPOINT"] = self.aoss_endpoint
        os.environ["LOCAL_EXTRACT_S3"] = self.graph_raw_bucket
        os.environ["EXTRACTION_MODEL"] = self.extraction_model
        os.environ["RESPONSE_MODEL"] = self.response_model
        os.environ["EMBEDDINGS_MODEL"] = self.embeddings_model
        os.environ["EXTRACTION_NUM_WORKERS"] = str(self.extraction_num_workers)
        os.environ["EXTRACTION_NUM_THREADS_PER_WORKER"] = str(self.extraction_num_threads_per_worker)
        os.environ["read_timeout"] = str(self.read_timeout)
        os.environ["ENABLE_CACHE"] = str(self.enable_cache)
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
