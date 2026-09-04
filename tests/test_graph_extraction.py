"""Tests for dia.pipeline.graph_extraction — chunking builder and checkpoint helpers."""

from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter

from dia.config import ChunkingConfig, ExtractionConfig
from dia.pipeline.graph_extraction import (
    _build_chunking_pipeline,
    _checkpoint_name,
    clear_checkpoint_dir,
)

# --- _checkpoint_name ---


def test_checkpoint_name_is_stable_for_same_source():
    assert _checkpoint_name("gats-business-cases") == _checkpoint_name("gats-business-cases")


def test_checkpoint_name_differs_by_source():
    assert _checkpoint_name("source-a") != _checkpoint_name("source-b")


# --- clear_checkpoint_dir ---


def test_clear_checkpoint_dir_removes_directory(tmp_path):
    checkpoint_dir = tmp_path / "save_points" / _checkpoint_name("my-source")
    checkpoint_dir.mkdir(parents=True)
    (checkpoint_dir / "some-node-id").write_text("")

    clear_checkpoint_dir("my-source", output_dir=tmp_path)

    assert not checkpoint_dir.exists()


def test_clear_checkpoint_dir_missing_directory_is_noop(tmp_path):
    # Should not raise even though nothing exists yet.
    clear_checkpoint_dir("never-run-source", output_dir=tmp_path)


def test_clear_checkpoint_dir_only_removes_the_named_source(tmp_path):
    keep_dir = tmp_path / "save_points" / _checkpoint_name("keep-me")
    remove_dir = tmp_path / "save_points" / _checkpoint_name("remove-me")
    keep_dir.mkdir(parents=True)
    remove_dir.mkdir(parents=True)

    clear_checkpoint_dir("remove-me", output_dir=tmp_path)

    assert keep_dir.exists()
    assert not remove_dir.exists()


# --- _build_chunking_pipeline ---


def test_chunking_pipeline_always_includes_sentence_splitter():
    parsers = _build_chunking_pipeline(ChunkingConfig(), ExtractionConfig())

    assert any(isinstance(p, SentenceSplitter) for p in parsers)


def test_chunking_pipeline_uses_configured_sentence_settings():
    chunking = ChunkingConfig(sentence_chunk_size=500, sentence_chunk_overlap=50, use_semantic_splitting=False)

    (parser,) = _build_chunking_pipeline(chunking, ExtractionConfig())

    assert isinstance(parser, SentenceSplitter)
    assert parser.chunk_size == 500
    assert parser.chunk_overlap == 50


def test_chunking_pipeline_omits_semantic_splitter_when_disabled():
    chunking = ChunkingConfig(use_semantic_splitting=False)

    parsers = _build_chunking_pipeline(chunking, ExtractionConfig())

    assert len(parsers) == 1
    assert not any(isinstance(p, SemanticSplitterNodeParser) for p in parsers)


def test_chunking_pipeline_includes_semantic_splitter_when_enabled():
    chunking = ChunkingConfig(use_semantic_splitting=True, semantic_buffer_size=5, semantic_breakpoint_threshold=90)

    parsers = _build_chunking_pipeline(chunking, ExtractionConfig())

    semantic_parsers = [p for p in parsers if isinstance(p, SemanticSplitterNodeParser)]
    assert len(semantic_parsers) == 1
    assert semantic_parsers[0].buffer_size == 5
    assert semantic_parsers[0].breakpoint_percentile_threshold == 90


def test_chunking_pipeline_semantic_splitter_uses_configured_embedding_model():
    extraction_config = ExtractionConfig(embeddings_model="amazon.titan-embed-text-v2:0")
    chunking = ChunkingConfig(use_semantic_splitting=True)

    parsers = _build_chunking_pipeline(chunking, extraction_config)

    (semantic_parser,) = [p for p in parsers if isinstance(p, SemanticSplitterNodeParser)]
    assert semantic_parser.embed_model.model_name == "amazon.titan-embed-text-v2:0"
