"""Tests for dia.config — ExtractionConfig and ChunkingConfig."""

import pytest
from pydantic import ValidationError

from dia.config import ChunkingConfig, ExtractionConfig, TextExtractionConfig

# --- ChunkingConfig ---


def test_chunking_config_defaults():
    config = ChunkingConfig()

    assert config.sentence_chunk_size_tokens == 7900
    assert config.sentence_chunk_overlap_tokens == 100
    assert config.use_semantic_splitting is True
    assert config.semantic_buffer_size == 3
    assert config.semantic_breakpoint_threshold == 97


def test_chunking_config_no_semantic():
    config = ChunkingConfig(use_semantic_splitting=False)

    assert config.use_semantic_splitting is False
    assert config.sentence_chunk_size_tokens == 7900


def test_chunking_config_rejects_zero_chunk_size():
    with pytest.raises(ValidationError):
        ChunkingConfig(sentence_chunk_size_tokens=0)


def test_chunking_config_rejects_negative_overlap():
    with pytest.raises(ValidationError):
        ChunkingConfig(sentence_chunk_overlap_tokens=-1)


def test_chunking_config_rejects_threshold_over_100():
    with pytest.raises(ValidationError):
        ChunkingConfig(semantic_breakpoint_threshold=101)


def test_chunking_config_is_frozen():
    config = ChunkingConfig()
    with pytest.raises(ValidationError):
        config.sentence_chunk_size_tokens = 1000


def test_chunking_config_fingerprint_is_stable():
    config = ChunkingConfig()
    assert config.to_fingerprint("amazon.titan-embed-text-v2:0") == config.to_fingerprint(
        "amazon.titan-embed-text-v2:0"
    )


def test_chunking_config_fingerprint_differs_for_different_config():
    default = ChunkingConfig()
    different = ChunkingConfig(semantic_breakpoint_threshold=95)

    assert default.to_fingerprint("amazon.titan-embed-text-v2:0") != different.to_fingerprint(
        "amazon.titan-embed-text-v2:0"
    )


def test_chunking_config_fingerprint_differs_for_different_embeddings_model():
    """embeddings_model isn't a field on ChunkingConfig, but it directly
    determines where the semantic splitter cuts, so it must affect the
    fingerprint even though the config object itself is identical."""
    config = ChunkingConfig()

    assert config.to_fingerprint("amazon.titan-embed-text-v2:0") != config.to_fingerprint("cohere.embed-english-v3")


def test_chunking_config_fingerprint_is_short_hex():
    config = ChunkingConfig()
    fingerprint = config.to_fingerprint("amazon.titan-embed-text-v2:0")

    assert len(fingerprint) == 8
    assert all(c in "0123456789abcdef" for c in fingerprint)


# --- ExtractionConfig ---


def test_extraction_config_defaults():
    config = ExtractionConfig()

    assert config.embeddings_model == "amazon.titan-embed-text-v2:0"
    assert config.region == "eu-west-2"
    assert config.embed_concurrency == 8


def test_extraction_config_override():
    config = ExtractionConfig(
        embeddings_model="amazon.titan-embed-text-v1",
        embed_concurrency=4,
    )

    assert config.embeddings_model == "amazon.titan-embed-text-v1"
    assert config.embed_concurrency == 4


def test_extraction_config_rejects_zero_embed_concurrency():
    with pytest.raises(ValidationError):
        ExtractionConfig(embed_concurrency=0)


def test_extraction_config_rejects_embed_concurrency_of_one():
    """embed_concurrency=1 would silently disable the semaphore (llama_index
    only applies it when num_workers > 1), so it's rejected rather than
    accepted-but-misleading."""
    with pytest.raises(ValidationError):
        ExtractionConfig(embed_concurrency=1)


def test_extraction_config_is_frozen():
    config = ExtractionConfig()
    with pytest.raises(ValidationError):
        config.embed_concurrency = 99


def test_extraction_config_to_embedding_model():
    from llama_index.embeddings.bedrock import BedrockEmbedding

    config = ExtractionConfig(embeddings_model="amazon.titan-embed-text-v2:0", region="eu-west-2", embed_concurrency=6)
    embedding_model = config.to_embedding_model()

    assert isinstance(embedding_model, BedrockEmbedding)
    assert embedding_model.model_name == "amazon.titan-embed-text-v2:0"
    assert embedding_model.region_name == "eu-west-2"
    assert embedding_model.num_workers == 6
    assert embedding_model.embed_batch_size == 1


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
