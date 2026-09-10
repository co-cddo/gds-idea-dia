"""Tests for dia.pipeline.chunk_store — persisting chunks between stages."""

import boto3
import pytest
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from moto import mock_aws

from dia.pipeline.chunk_store import ChunkStore, InMemoryChunkStore, LocalChunkStore, S3ChunkStore

FINGERPRINT = "9b55a7e3"


def _node(node_id: str, doc_key: str, version: str, text: str = "Some chunk text.", **overrides) -> TextNode:
    """Build a TextNode shaped like a real chunk: SOURCE relationship,
    domain metadata (including key/version, as to_document() + chunking
    set them), and bookkeeping fields excluded from LLM/embeddings — the
    exact shape the round-trip and present() need to preserve/read."""
    node = TextNode(
        id_=node_id,
        text=text,
        metadata={"department": "Home Office", "key": doc_key, "version": version},
        excluded_llm_metadata_keys=["key", "version"],
        excluded_embed_metadata_keys=["key", "version"],
    )
    node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
        node_id=overrides.pop("source_doc_id", doc_key),
        metadata={"key": doc_key},
    )
    return node


# --- LocalChunkStore ---


def test_local_store_read_returns_empty_list_for_missing_source(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    assert store.read("no-such-source") == []


def test_local_store_present_returns_empty_set_for_missing_source(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    assert store.present("no-such-source") == set()


def test_local_store_write_returns_count(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    count = store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1"), _node("n2", "doc-1.pdf", "v1")])
    assert count == 2


def test_local_store_round_trip_preserves_node_id_and_text(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1", text="First chunk.")])
    store.write("src", "doc-2.pdf", "v1", [_node("n2", "doc-2.pdf", "v1", text="Second chunk.")])

    nodes = sorted(store.read("src"), key=lambda n: n.text)

    assert [n.node_id for n in nodes] == ["n1", "n2"]
    assert [n.text for n in nodes] == ["First chunk.", "Second chunk."]


def test_local_store_round_trip_preserves_metadata_and_exclusions(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")])

    (node,) = store.read("src")

    assert node.metadata == {"department": "Home Office", "key": "doc-1.pdf", "version": "v1"}
    assert node.excluded_llm_metadata_keys == ["key", "version"]
    assert node.excluded_embed_metadata_keys == ["key", "version"]


def test_local_store_round_trip_preserves_source_relationship(tmp_path):
    """The SOURCE relationship is how chunks trace back to their parent
    document — losing it would break traceability and SourceDocument
    grouping downstream in the extraction stage."""
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1", source_doc_id="doc-1.pdf")])

    (node,) = store.read("src")

    source = node.relationships[NodeRelationship.SOURCE]
    assert source.node_id == "doc-1.pdf"
    assert source.metadata == {"key": "doc-1.pdf"}


def test_local_store_write_replaces_previous_content_for_same_document(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("old-1", "doc-1.pdf", "v1"), _node("old-2", "doc-1.pdf", "v1")])

    store.write("src", "doc-1.pdf", "v2", [_node("new-1", "doc-1.pdf", "v2")])

    nodes = store.read("src")
    assert [n.node_id for n in nodes] == ["new-1"]


def test_local_store_keeps_documents_separate(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-a.pdf", "v1", [_node("a1", "doc-a.pdf", "v1")])
    store.write("src", "doc-b.pdf", "v1", [_node("b1", "doc-b.pdf", "v1")])

    nodes = store.read("src")
    assert {n.node_id for n in nodes} == {"a1", "b1"}


def test_local_store_keeps_sources_separate(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("source-a", "doc-1.pdf", "v1", [_node("a1", "doc-1.pdf", "v1")])
    store.write("source-b", "doc-1.pdf", "v1", [_node("b1", "doc-1.pdf", "v1")])

    assert [n.node_id for n in store.read("source-a")] == ["a1"]
    assert [n.node_id for n in store.read("source-b")] == ["b1"]


def test_local_store_keeps_fingerprints_separate(tmp_path):
    """Different fingerprint = different config = must not see each
    other's chunks, even for the same source/document."""
    store_a = LocalChunkStore("fingerprint-a", tmp_path)
    store_b = LocalChunkStore("fingerprint-b", tmp_path)

    store_a.write("src", "doc-1.pdf", "v1", [_node("a1", "doc-1.pdf", "v1")])

    assert [n.node_id for n in store_a.read("src")] == ["a1"]
    assert store_b.read("src") == []
    assert store_b.present("src") == set()


def test_local_store_present_reflects_written_documents(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-a.pdf", "v1", [_node("a1", "doc-a.pdf", "v1")])
    store.write("src", "doc-b.pdf", "v2", [_node("b1", "doc-b.pdf", "v2")])

    assert store.present("src") == {("doc-a.pdf", "v1"), ("doc-b.pdf", "v2")}


def test_local_store_present_reflects_new_version_after_rewrite(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")])
    store.write("src", "doc-1.pdf", "v2", [_node("n2", "doc-1.pdf", "v2")])

    assert store.present("src") == {("doc-1.pdf", "v2")}


def test_local_store_delete_removes_all_documents(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-a.pdf", "v1", [_node("a1", "doc-a.pdf", "v1")])
    store.write("src", "doc-b.pdf", "v1", [_node("b1", "doc-b.pdf", "v1")])

    store.delete("src")

    assert store.read("src") == []
    assert store.present("src") == set()


def test_local_store_delete_on_missing_source_is_noop(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.delete("no-such-source")  # must not raise


def test_local_store_accepts_string_base_dir(tmp_path):
    store = LocalChunkStore(FINGERPRINT, str(tmp_path))
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")])
    assert len(store.read("src")) == 1


def test_local_store_does_not_leave_tmp_file_behind(tmp_path):
    store = LocalChunkStore(FINGERPRINT, tmp_path)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")])

    leftover = list((tmp_path / "chunks").rglob("*.tmp"))
    assert leftover == []


# --- InMemoryChunkStore ---


def test_memory_store_read_returns_empty_list_for_missing_source():
    store = InMemoryChunkStore(FINGERPRINT)
    assert store.read("no-such-source") == []


def test_memory_store_present_returns_empty_set_for_missing_source():
    store = InMemoryChunkStore(FINGERPRINT)
    assert store.present("no-such-source") == set()


def test_memory_store_round_trip():
    store = InMemoryChunkStore(FINGERPRINT)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1", text="First chunk.")])

    (node,) = store.read("src")
    assert node.node_id == "n1"
    assert node.text == "First chunk."


def test_memory_store_write_replaces_previous_content_for_same_document():
    store = InMemoryChunkStore(FINGERPRINT)
    store.write("src", "doc-1.pdf", "v1", [_node("old-1", "doc-1.pdf", "v1")])
    store.write("src", "doc-1.pdf", "v2", [_node("new-1", "doc-1.pdf", "v2")])

    assert [n.node_id for n in store.read("src")] == ["new-1"]


def test_memory_store_present_reflects_written_documents():
    store = InMemoryChunkStore(FINGERPRINT)
    store.write("src", "doc-a.pdf", "v1", [_node("a1", "doc-a.pdf", "v1")])
    store.write("src", "doc-b.pdf", "v2", [_node("b1", "doc-b.pdf", "v2")])

    assert store.present("src") == {("doc-a.pdf", "v1"), ("doc-b.pdf", "v2")}


def test_memory_store_delete_on_missing_source_is_noop():
    store = InMemoryChunkStore(FINGERPRINT)
    store.delete("no-such-source")  # must not raise


# --- S3ChunkStore ---

BUCKET = "test-chunks-bucket"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-west-2"})
        yield client


def test_s3_store_read_returns_empty_list_for_missing_source(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    assert store.read("no-such-source") == []


def test_s3_store_present_returns_empty_set_for_missing_source(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    assert store.present("no-such-source") == set()


def test_s3_store_round_trip_preserves_node_id_and_text(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1", text="First chunk.")])
    store.write("src", "doc-2.pdf", "v1", [_node("n2", "doc-2.pdf", "v1", text="Second chunk.")])

    nodes = sorted(store.read("src"), key=lambda n: n.text)

    assert [n.node_id for n in nodes] == ["n1", "n2"]
    assert [n.text for n in nodes] == ["First chunk.", "Second chunk."]


def test_s3_store_round_trip_preserves_source_relationship(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1", source_doc_id="doc-1.pdf")])

    (node,) = store.read("src")

    source = node.relationships[NodeRelationship.SOURCE]
    assert source.node_id == "doc-1.pdf"


def test_s3_store_present_does_not_require_reading_chunk_content(s3_client):
    """present() must answer from the companion .meta.json objects alone -
    put a chunk .jsonl object that would fail to parse as a TextNode, and
    confirm present() still works (it never touches that object)."""
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")])

    s3_client.put_object(Bucket=BUCKET, Key=store._jsonl_key("src", "doc-1.pdf"), Body=b"not valid json at all")

    assert store.present("src") == {("doc-1.pdf", "v1")}


def test_s3_store_write_replaces_previous_content_for_same_document(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.write("src", "doc-1.pdf", "v1", [_node("old-1", "doc-1.pdf", "v1")])
    store.write("src", "doc-1.pdf", "v2", [_node("new-1", "doc-1.pdf", "v2")])

    assert [n.node_id for n in store.read("src")] == ["new-1"]
    assert store.present("src") == {("doc-1.pdf", "v2")}


def test_s3_store_keeps_fingerprints_separate(s3_client):
    store_a = S3ChunkStore("fingerprint-a", bucket=BUCKET, s3_client=s3_client)
    store_b = S3ChunkStore("fingerprint-b", bucket=BUCKET, s3_client=s3_client)

    store_a.write("src", "doc-1.pdf", "v1", [_node("a1", "doc-1.pdf", "v1")])

    assert [n.node_id for n in store_a.read("src")] == ["a1"]
    assert store_b.read("src") == []
    assert store_b.present("src") == set()


def test_s3_store_delete_removes_all_documents(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.write("src", "doc-a.pdf", "v1", [_node("a1", "doc-a.pdf", "v1")])
    store.write("src", "doc-b.pdf", "v1", [_node("b1", "doc-b.pdf", "v1")])

    store.delete("src")

    assert store.read("src") == []
    assert store.present("src") == set()

    response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="src/")
    assert response.get("KeyCount", 0) == 0


def test_s3_store_delete_on_missing_source_is_noop(s3_client):
    store = S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client)
    store.delete("no-such-source")  # must not raise


# --- Protocol conformance ---


def test_all_stores_satisfy_protocol(tmp_path, s3_client):
    stores: list[ChunkStore] = [
        LocalChunkStore(FINGERPRINT, tmp_path),
        InMemoryChunkStore(FINGERPRINT),
        S3ChunkStore(FINGERPRINT, bucket=BUCKET, s3_client=s3_client),
    ]
    for store in stores:
        assert store.present("src") == set()
        assert store.write("src", "doc-1.pdf", "v1", [_node("n1", "doc-1.pdf", "v1")]) == 1
        assert store.present("src") == {("doc-1.pdf", "v1")}
        assert len(store.read("src")) == 1
        store.delete("src")
        assert store.read("src") == []
