"""Tests for dia.pipeline.chunk_store — persisting chunks between stages."""

from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from dia.pipeline.chunk_store import ChunkStore, InMemoryChunkStore, LocalChunkStore


def _node(node_id: str, text: str = "Some chunk text.", **overrides) -> TextNode:
    """Build a TextNode shaped like a real chunk: SOURCE relationship,
    domain metadata, and bookkeeping fields excluded from LLM/embeddings —
    the exact shape the round-trip needs to preserve."""
    node = TextNode(
        id_=node_id,
        text=text,
        metadata={"department": "Home Office", "source_name": "gats-business-cases"},
        excluded_llm_metadata_keys=["source_name"],
        excluded_embed_metadata_keys=["source_name"],
    )
    node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
        node_id=overrides.pop("source_doc_id", "doc-1"),
        metadata={"key": "files/report.pdf"},
    )
    return node


# --- LocalChunkStore ---


def test_local_store_read_returns_empty_list_for_missing_source(tmp_path):
    store = LocalChunkStore(tmp_path)
    assert store.read("no-such-source") == []


def test_local_store_write_returns_count(tmp_path):
    store = LocalChunkStore(tmp_path)
    count = store.write("src", [_node("n1"), _node("n2")])
    assert count == 2


def test_local_store_round_trip_preserves_node_id_and_text(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("n1", text="First chunk."), _node("n2", text="Second chunk.")])

    nodes = store.read("src")

    assert [n.node_id for n in nodes] == ["n1", "n2"]
    assert [n.text for n in nodes] == ["First chunk.", "Second chunk."]


def test_local_store_round_trip_preserves_metadata_and_exclusions(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("n1")])

    (node,) = store.read("src")

    assert node.metadata == {"department": "Home Office", "source_name": "gats-business-cases"}
    assert node.excluded_llm_metadata_keys == ["source_name"]
    assert node.excluded_embed_metadata_keys == ["source_name"]


def test_local_store_round_trip_preserves_source_relationship(tmp_path):
    """The SOURCE relationship is how chunks trace back to their parent
    document — losing it would break traceability and SourceDocument
    grouping downstream in the extraction stage."""
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("n1", source_doc_id="doc-42")])

    (node,) = store.read("src")

    source = node.relationships[NodeRelationship.SOURCE]
    assert source.node_id == "doc-42"
    assert source.metadata == {"key": "files/report.pdf"}


def test_local_store_write_replaces_previous_content(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("old-1"), _node("old-2")])

    store.write("src", [_node("new-1")])

    nodes = store.read("src")
    assert [n.node_id for n in nodes] == ["new-1"]


def test_local_store_keeps_sources_separate(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("source-a", [_node("a1")])
    store.write("source-b", [_node("b1")])

    assert [n.node_id for n in store.read("source-a")] == ["a1"]
    assert [n.node_id for n in store.read("source-b")] == ["b1"]


def test_local_store_delete_removes_file(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("n1")])

    store.delete("src")

    assert store.read("src") == []


def test_local_store_delete_on_missing_source_is_noop(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.delete("no-such-source")  # must not raise


def test_local_store_exists(tmp_path):
    store = LocalChunkStore(tmp_path)
    assert store.exists("src") is False

    store.write("src", [_node("n1")])
    assert store.exists("src") is True

    store.delete("src")
    assert store.exists("src") is False


def test_local_store_accepts_string_base_dir(tmp_path):
    store = LocalChunkStore(str(tmp_path))
    store.write("src", [_node("n1")])
    assert len(store.read("src")) == 1


def test_local_store_does_not_leave_tmp_file_behind(tmp_path):
    store = LocalChunkStore(tmp_path)
    store.write("src", [_node("n1")])

    leftover = list((tmp_path / "chunks").glob("*.tmp"))
    assert leftover == []


# --- InMemoryChunkStore ---


def test_memory_store_read_returns_empty_list_for_missing_source():
    store = InMemoryChunkStore()
    assert store.read("no-such-source") == []


def test_memory_store_round_trip():
    store = InMemoryChunkStore()
    store.write("src", [_node("n1", text="First chunk.")])

    (node,) = store.read("src")
    assert node.node_id == "n1"
    assert node.text == "First chunk."


def test_memory_store_write_replaces_previous_content():
    store = InMemoryChunkStore()
    store.write("src", [_node("old-1")])
    store.write("src", [_node("new-1")])

    assert [n.node_id for n in store.read("src")] == ["new-1"]


def test_memory_store_delete_on_missing_source_is_noop():
    store = InMemoryChunkStore()
    store.delete("no-such-source")  # must not raise


def test_memory_store_exists():
    store = InMemoryChunkStore()
    assert store.exists("src") is False

    store.write("src", [_node("n1")])
    assert store.exists("src") is True


# --- Protocol conformance ---


def test_both_stores_satisfy_protocol(tmp_path):
    stores: list[ChunkStore] = [LocalChunkStore(tmp_path), InMemoryChunkStore()]
    for store in stores:
        assert store.exists("src") is False
        assert store.write("src", [_node("n1")]) == 1
        assert store.exists("src") is True
        assert len(store.read("src")) == 1
        store.delete("src")
        assert store.read("src") == []
