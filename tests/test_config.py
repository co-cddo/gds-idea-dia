"""Tests for dia.config."""

import os

import pytest

from dia.config import PipelineConfig, bucket_name


class TestBucketName:
    """Test the bucket naming helper."""

    def test_standard_pattern(self):
        assert bucket_name("gds-idea", "dia", "graph-raw", "dev") == "gds-idea-dia-graph-raw-dev"

    def test_prod_phase(self):
        assert bucket_name("gds-idea", "dia", "graph-raw", "prod") == "gds-idea-dia-graph-raw-prod"

    def test_different_purpose(self):
        assert bucket_name("gds-idea", "dia", "batch", "dev") == "gds-idea-dia-batch-dev"


class TestPipelineConfigDefaults:
    """Test that defaults are sensible and construction works."""

    def test_default_construction(self):
        config = PipelineConfig()
        assert config.phase == "dev"
        assert config.project == "dia"
        assert config.team == "gds-idea"
        assert config.region == "eu-west-2"

    def test_invalid_phase_rejected(self):
        with pytest.raises(Exception):
            PipelineConfig(phase="staging")

    def test_model_defaults(self):
        config = PipelineConfig()
        assert config.extraction_model == "eu.anthropic.claude-sonnet-4-6"
        assert config.embeddings_model == "amazon.titan-embed-text-v2:0"
        assert config.max_tokens == 42768
        assert config.temperature == 0.0

    def test_extraction_tuning_defaults(self):
        config = PipelineConfig()
        assert config.sentence_chunk_size == 7900
        assert config.extraction_batch_size == 20000
        assert config.num_classifications == 50


class TestPipelineConfigPhaseResolution:
    """Test that phase-resolved fields derive correctly."""

    def test_neptune_endpoint_dev(self):
        config = PipelineConfig(phase="dev")
        assert "neptune" in config.neptune_endpoint
        assert "eu-west-2" in config.neptune_endpoint

    def test_aoss_endpoint_dev(self):
        config = PipelineConfig(phase="dev")
        assert config.aoss_endpoint.startswith("https://")
        assert "aoss.amazonaws.com" in config.aoss_endpoint

    def test_graph_raw_bucket_dev(self):
        config = PipelineConfig(phase="dev")
        assert config.graph_raw_bucket == "gds-idea-dia-graph-raw-dev"

    def test_graph_validated_bucket_dev(self):
        config = PipelineConfig(phase="dev")
        assert config.graph_validated_bucket == "gds-idea-dia-graph-validated-dev"

    def test_batch_bucket_dev(self):
        config = PipelineConfig(phase="dev")
        assert config.batch_bucket == "gds-idea-dia-batch-dev"

    def test_bucket_helper(self):
        config = PipelineConfig(phase="dev")
        assert config.bucket("custom-purpose") == "gds-idea-dia-custom-purpose-dev"

    def test_batch_role_arn_dev(self):
        config = PipelineConfig(phase="dev")
        assert config.batch_role_arn.startswith("arn:aws:iam::")


class TestPipelineConfigOverrides:
    """Test that fields can be overridden."""

    def test_override_model(self):
        config = PipelineConfig(extraction_model="eu.anthropic.claude-haiku-4-5-20251001-v1:0")
        assert config.extraction_model == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_override_batch_size(self):
        config = PipelineConfig(extraction_batch_size=2000)
        assert config.extraction_batch_size == 2000


class TestPipelineConfigValidation:
    """Test that invalid values are rejected."""

    def test_negative_max_tokens_rejected(self):
        with pytest.raises(Exception):
            PipelineConfig(max_tokens=-1)

    def test_zero_batch_size_rejected(self):
        with pytest.raises(Exception):
            PipelineConfig(extraction_batch_size=0)

    def test_temperature_above_one_rejected(self):
        with pytest.raises(Exception):
            PipelineConfig(temperature=1.5)


class TestToEnvForGraphragToolkit:
    """Test that to_env_for_graphrag_toolkit() sets expected env vars."""

    def test_sets_all_expected_vars(self, monkeypatch):
        env_vars = [
            "AWS_REGION",
            "aws_profile",
            "NEPTUNE_ENDPOINT",
            "AOSS_ENDPOINT",
            "LOCAL_EXTRACT_S3",
            "EXTRACTION_MODEL",
            "RESPONSE_MODEL",
            "EMBEDDINGS_MODEL",
            "EXTRACTION_NUM_WORKERS",
            "EXTRACTION_NUM_THREADS_PER_WORKER",
            "read_timeout",
            "ENABLE_CACHE",
            "TOKENIZERS_PARALLELISM",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

        config = PipelineConfig(phase="dev")
        config.to_env_for_graphrag_toolkit()

        assert os.environ["AWS_REGION"] == "eu-west-2"
        assert os.environ["NEPTUNE_ENDPOINT"] == config.neptune_endpoint
        assert os.environ["LOCAL_EXTRACT_S3"] == "gds-idea-dia-graph-raw-dev"
        assert os.environ["EXTRACTION_MODEL"] == "eu.anthropic.claude-sonnet-4-6"
        assert os.environ["TOKENIZERS_PARALLELISM"] == "false"
