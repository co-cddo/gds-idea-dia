"""Tests for dia.config — ExtractionConfig and ChunkingConfig."""

import pytest
from pydantic import ValidationError

from dia.config import ChunkingConfig, ExtractionConfig, TextExtractionConfig

# --- ChunkingConfig ---


def test_chunking_config_defaults():
    config = ChunkingConfig()

    assert config.sentence_chunk_size == 7900
    assert config.sentence_chunk_overlap == 100
    assert config.use_semantic_splitting is True
    assert config.semantic_buffer_size == 3
    assert config.semantic_breakpoint_threshold == 97


def test_chunking_config_no_semantic():
    config = ChunkingConfig(use_semantic_splitting=False)

    assert config.use_semantic_splitting is False
    assert config.sentence_chunk_size == 7900


def test_chunking_config_rejects_zero_chunk_size():
    with pytest.raises(ValidationError):
        ChunkingConfig(sentence_chunk_size=0)


def test_chunking_config_rejects_negative_overlap():
    with pytest.raises(ValidationError):
        ChunkingConfig(sentence_chunk_overlap=-1)


def test_chunking_config_rejects_threshold_over_100():
    with pytest.raises(ValidationError):
        ChunkingConfig(semantic_breakpoint_threshold=101)


def test_chunking_config_is_frozen():
    config = ChunkingConfig()
    with pytest.raises(ValidationError):
        config.sentence_chunk_size = 1000


# --- ExtractionConfig ---


def test_extraction_config_defaults():
    config = ExtractionConfig()

    assert config.extraction_model == "eu.anthropic.claude-sonnet-4-6"
    assert config.embeddings_model == "amazon.titan-embed-text-v2:0"
    assert config.region == "eu-west-2"
    assert config.extraction_batch_size == 20000
    assert config.extraction_num_workers == 2
    assert config.extraction_num_threads_per_worker == 2
    assert config.max_tokens == 42768
    assert config.temperature == 0.0
    assert config.read_timeout == 600
    assert config.enable_cache is True


def test_extraction_config_override():
    config = ExtractionConfig(
        extraction_model="anthropic.claude-sonnet-4-5-20250929-v1:0",
        extraction_batch_size=5000,
    )

    assert config.extraction_model == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert config.extraction_batch_size == 5000


def test_extraction_config_rejects_unapproved_model():
    with pytest.raises(ValidationError):
        ExtractionConfig(extraction_model="eu.anthropic.claude-haiku-4-5-20251001-v1:0")


def test_extraction_config_rejects_zero_batch_size():
    with pytest.raises(ValidationError):
        ExtractionConfig(extraction_batch_size=0)


def test_extraction_config_rejects_zero_workers():
    with pytest.raises(ValidationError):
        ExtractionConfig(extraction_num_workers=0)


def test_extraction_config_rejects_negative_temperature():
    with pytest.raises(ValidationError):
        ExtractionConfig(temperature=-0.1)


def test_extraction_config_rejects_temperature_over_1():
    with pytest.raises(ValidationError):
        ExtractionConfig(temperature=1.1)


def test_extraction_config_temperature_none():
    config = ExtractionConfig(temperature=None)
    assert config.temperature is None


def test_extraction_config_is_frozen():
    config = ExtractionConfig()
    with pytest.raises(ValidationError):
        config.extraction_model = "something"


def test_extraction_config_to_llm():
    config = ExtractionConfig(
        extraction_model="anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.2,
        max_tokens=1000,
        region="us-east-1",
    )

    llm = config.to_llm()

    assert llm.model == "anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert llm.temperature == 0.2
    assert llm.max_tokens == 1000
    assert llm.region_name == "us-east-1"


def test_extraction_config_to_embedding_model():
    config = ExtractionConfig(embeddings_model="amazon.titan-embed-text-v2:0", region="us-east-1")

    embed_model = config.to_embedding_model()

    assert embed_model.model_name == "amazon.titan-embed-text-v2:0"
    assert embed_model.region_name == "us-east-1"


# --- TextExtractionConfig ---


def test_text_extraction_config_defaults():
    config = TextExtractionConfig()

    assert config.batch_size == 100
    assert config.max_concurrency == 10


def test_text_extraction_config_override():
    config = TextExtractionConfig(batch_size=50, max_concurrency=20)

    assert config.batch_size == 50
    assert config.max_concurrency == 20


def test_text_extraction_config_rejects_zero_batch_size():
    with pytest.raises(ValidationError):
        TextExtractionConfig(batch_size=0)


def test_text_extraction_config_rejects_zero_concurrency():
    with pytest.raises(ValidationError):
        TextExtractionConfig(max_concurrency=0)


def test_text_extraction_config_is_frozen():
    config = TextExtractionConfig()
    with pytest.raises(ValidationError):
        config.batch_size = 50
