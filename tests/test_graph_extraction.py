"""Tests for dia.pipeline.graph_extraction — chunking builder and checkpoint helpers."""

from unittest.mock import MagicMock, patch

from graphrag_toolkit.lexical_graph.indexing.extract import BatchConfig
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter

from dia.config import ChunkingConfig, ExtractionConfig
from dia.document_types import DocumentType
from dia.ledger.memory import InMemoryLedger
from dia.pipeline.graph_extraction import (
    GraphExtractionRunner,
    _build_chunking_pipeline,
    _checkpoint_name,
    clear_checkpoint_dir,
)
from dia.pipeline.graph_extraction_prompts import TOPIC_EXTRACTION_PROMPT
from dia.pipeline.models import TextExtractionOutput
from dia.types import DocumentReference

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


# ---------------------------------------------------------------------------
# GraphExtractionRunner
# ---------------------------------------------------------------------------


class InMemoryOutputSource:
    """In-memory TextExtractionOutputSource for testing."""

    def __init__(self, outputs: dict[str, list[TextExtractionOutput]]) -> None:
        self._outputs = outputs

    def list_outputs(self, source_name: str) -> list[TextExtractionOutput]:
        return self._outputs.get(source_name, [])


def _output(key: str, department: str | None = None, version: str = "v1") -> TextExtractionOutput:
    return TextExtractionOutput(
        key=key,
        source_name="test-source",
        content_type="application/pdf",
        version=version,
        text=f"extracted text for {key}",
        chars=20,
        metadata={"department": department} if department else {},
        extracted_at="2026-01-01T00:00:00+00:00",
        code_version="0.1.0",
    )


def _ref(key: str, version: str = "v1") -> DocumentReference:
    return DocumentReference(key=key, content_type="application/pdf", version=version)


def _make_runner(output_source, ledger, extraction_config, tmp_path, force=False, batch_config=None):
    return GraphExtractionRunner(
        source_name="test-source",
        document_type=DocumentType.BUSINESS_CASE,
        output_source=output_source,
        ledger=ledger,
        extraction_config=extraction_config,
        graph_output_handler=MagicMock(),
        batch_config=batch_config,
        checkpoint_dir=str(tmp_path),
        force=force,
        log_dir=str(tmp_path),
    )


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_processes_pending_documents(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf"), _output("b.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    result = runner.run()

    assert result.total == 2
    assert result.processed == 2
    assert result.skipped == 0
    assert result.failed == 0
    mock_index_cls.return_value.extract.assert_called_once()


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_marks_documents_processed_in_ledger(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    ledger = InMemoryLedger()
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path)

    runner.run()

    assert ledger.get_unprocessed([_ref("a.pdf")], "test-source", "graph") == []


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_stores_department_in_ledger(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf", department="Home Office")]})
    ledger = InMemoryLedger()
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path)

    runner.run()

    assert ledger.records["graph#test-source#a.pdf#v1"].department == "Home Office"


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_skips_already_processed_documents(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf"), _output("b.pdf")]})
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf"), "test-source", "graph")
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path)

    result = runner.run()

    assert result.total == 2
    assert result.skipped == 1
    assert result.processed == 1
    (call_args,) = mock_index_cls.return_value.extract.call_args_list
    documents = call_args.args[0]
    assert [d.doc_id for d in documents] == ["b.pdf"]


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_nothing_pending_does_not_construct_index(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf"), "test-source", "graph")
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path)

    result = runner.run()

    assert result.processed == 0
    assert result.skipped == 1
    mock_index_cls.assert_not_called()


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_force_reprocesses_already_processed_documents(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    ledger = InMemoryLedger()
    ledger.mark_processed(_ref("a.pdf"), "test-source", "graph")
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path, force=True)

    result = runner.run()

    assert result.processed == 1
    assert result.skipped == 0


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_force_clears_checkpoint_dir(mock_index_cls, tmp_path):
    checkpoint_dir = tmp_path / "save_points" / _checkpoint_name("test-source")
    checkpoint_dir.mkdir(parents=True)
    stale_file = checkpoint_dir / "stale-chunk"
    stale_file.write_text("")
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path, force=True)

    runner.run()

    # The real (unmocked) Checkpoint() recreates an empty directory right
    # after clearing it, ready for the new run — so check the stale file is
    # gone, not that the directory itself no longer exists.
    assert not stale_file.exists()


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_failure_does_not_mark_ledger(mock_index_cls, tmp_path):
    mock_index_cls.return_value.extract.side_effect = RuntimeError("boom")
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    ledger = InMemoryLedger()
    runner = _make_runner(source, ledger, ExtractionConfig(), tmp_path)

    result = runner.run()

    assert result.processed == 0
    assert result.failed == 1
    assert result.failed_keys == ["a.pdf"]
    assert result.error == "boom"
    assert ledger.get_unprocessed([_ref("a.pdf")], "test-source", "graph") == [_ref("a.pdf")]


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_run_failure_does_not_raise(mock_index_cls, tmp_path):
    mock_index_cls.return_value.extract.side_effect = RuntimeError("boom")
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    runner.run()  # should not raise


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_uses_dummy_stores(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    assert kwargs["graph_store"] == "dummy://"
    assert kwargs["vector_store"] == "dummy://"


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_uses_document_type_entity_classifications(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    indexing_config = kwargs["indexing_config"]
    expected = DocumentType.BUSINESS_CASE.entity_classifications
    assert indexing_config.extraction.preferred_entity_classifications == expected


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_uses_ported_prompt(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    assert kwargs["indexing_config"].extraction.extract_topics_prompt_template == TOPIC_EXTRACTION_PROMPT


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_passes_batch_config_through(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    batch_config = BatchConfig(role_arn="arn:aws:iam::123:role/test", region="eu-west-2", bucket_name="test-bucket")
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path, batch_config=batch_config)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    assert kwargs["indexing_config"].batch_config is batch_config


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_defaults_batch_config_to_none(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    runner = _make_runner(source, InMemoryLedger(), ExtractionConfig(), tmp_path)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    assert kwargs["indexing_config"].batch_config is None


@patch("dia.pipeline.graph_extraction.LexicalGraphIndex")
def test_build_index_uses_llm_from_extraction_config(mock_index_cls, tmp_path):
    source = InMemoryOutputSource({"test-source": [_output("a.pdf")]})
    extraction_config = ExtractionConfig(max_tokens=1234)
    runner = _make_runner(source, InMemoryLedger(), extraction_config, tmp_path)

    runner.run()

    _, kwargs = mock_index_cls.call_args
    assert kwargs["indexing_config"].extraction.extraction_llm.max_tokens == 1234
