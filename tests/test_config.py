"""Tests for dia.config."""

import pytest

from dia.config import PipelineConfig


class TestPipelineConfig:
    def test_default_construction(self):
        config = PipelineConfig()
        assert config.phase == "dev"
        assert config.project == "dia"
        assert config.team == "gds-idea"
        assert config.region == "eu-west-2"

    def test_bucket_helper(self):
        config = PipelineConfig()
        assert config.bucket("graph-raw") == "gds-idea-dia-graph-raw-dev"
        assert config.bucket("graph-validated") == "gds-idea-dia-graph-validated-dev"
        assert config.bucket("batch") == "gds-idea-dia-batch-dev"

    def test_bucket_with_custom_project(self):
        config = PipelineConfig(project="custom")
        assert config.bucket("data") == "gds-idea-custom-data-dev"

    def test_invalid_phase_rejected(self):
        with pytest.raises(Exception):
            PipelineConfig(phase="staging")
