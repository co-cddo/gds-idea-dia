"""Persists chunks between the chunking and extraction stages.

Chunking (splitting documents into TextNodes) and graph extraction (LLM
propositions/topics per chunk) are separate stages joined only by chunks in
storage — see docs/adr/0001-lower-level-graphrag-toolkit-usage.md for why.
If extraction fails, chunks already produced are untouched: no need to redo
the (comparatively slow, embedding-heavy) chunking stage to retry
extraction.

Stores are scoped by a chunking-config fingerprint (see
ChunkingConfig.to_fingerprint), not tracked via a separate ledger stage: a
config change means a different fingerprint, which means "no chunks found
here" rather than "stale chunks silently reused". One store instance is
scoped to one fingerprint - to chunk the same source with a different
config, construct a new store with the new fingerprint.

One JSONL file per document, one TextNode.to_dict() per line — the same
serialisation graphrag_toolkit itself uses for its own temp node files
(indexing/extract/batch_extractor_base.py), so relationships/metadata/
exclusions are known to round-trip correctly.

present() answers "what have we already got" purely from stored content
(each chunk's own metadata['key']/metadata['version'], set by
to_document()), not from parsing file paths - this sidesteps any question
of whether a document key or version string (e.g. an S3 ETag, which
arrives wrapped in literal quote characters) is safe to embed directly in
a path. File names are content-addressed (a hash of the document key)
purely to give each document a stable, collision-free, filesystem-safe
location.
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from llama_index.core.schema import BaseNode, TextNode


class ChunkStore(Protocol):
    """Reads/writes chunks for a source, keyed by document, scoped to one
    chunking-config fingerprint."""

    def write(self, source_name: str, doc_key: str, version: str, nodes: Sequence[BaseNode]) -> int:
        """Persist nodes for one document, replacing anything already
        stored for that document under this fingerprint.

        Returns the number of nodes written.
        """
        ...

    def read(self, source_name: str) -> list[TextNode]:
        """Load every stored chunk for a source (all documents, this
        fingerprint). [] if none exist."""
        ...

    def present(self, source_name: str) -> set[tuple[str, str]]:
        """(doc_key, version) pairs already chunked for a source under this
        fingerprint - i.e. what's already done, so the caller can work out
        what's new or changed."""
        ...

    def delete(self, source_name: str) -> None:
        """Remove all stored chunks for a source (this fingerprint only).
        No-op if none exist."""
        ...


def _doc_hash(doc_key: str) -> str:
    """Stable, filesystem/path-safe identifier for a document key."""
    return hashlib.sha256(doc_key.encode()).hexdigest()[:16]


class LocalChunkStore:
    """Stores chunks as one JSONL file per document on local disk.

    Path: {base_dir}/chunks/{source_name}/{fingerprint}/{hash(doc_key)}.jsonl

    Writes go to a temp file then an atomic rename, so a file is either
    the complete previous write or absent — never a partial one.
    """

    def __init__(self, fingerprint: str, base_dir: Path | str = "output") -> None:
        self._fingerprint = fingerprint
        self._chunks_dir = Path(base_dir) / "chunks"

    def _dir(self, source_name: str) -> Path:
        return self._chunks_dir / source_name / self._fingerprint

    def _path(self, source_name: str, doc_key: str) -> Path:
        return self._dir(source_name) / f"{_doc_hash(doc_key)}.jsonl"

    def write(self, source_name: str, doc_key: str, version: str, nodes: Sequence[BaseNode]) -> int:
        path = self._path(source_name, doc_key)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for node in nodes:
                f.write(json.dumps(node.to_dict(), ensure_ascii=False))
                f.write("\n")
        tmp_path.replace(path)

        return len(nodes)

    def read(self, source_name: str) -> list[TextNode]:
        source_dir = self._dir(source_name)
        if not source_dir.exists():
            return []

        nodes: list[TextNode] = []
        for path in sorted(source_dir.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as f:
                nodes.extend(TextNode.from_json(line) for line in f if line.strip())
        return nodes

    def present(self, source_name: str) -> set[tuple[str, str]]:
        source_dir = self._dir(source_name)
        if not source_dir.exists():
            return set()

        pairs: set[tuple[str, str]] = set()
        for path in source_dir.glob("*.jsonl"):
            with path.open("r", encoding="utf-8") as f:
                first_line = f.readline()
            if not first_line.strip():
                continue
            node = TextNode.from_json(first_line)
            pairs.add((node.metadata["key"], node.metadata["version"]))
        return pairs

    def delete(self, source_name: str) -> None:
        source_dir = self._dir(source_name)
        if not source_dir.exists():
            return
        for path in source_dir.glob("*.jsonl"):
            path.unlink()
        source_dir.rmdir()


class InMemoryChunkStore:
    """Captures written nodes in memory instead of persisting them.

    Useful for tests (assert on what was written without tmp_path) and for
    programmatic use where you want chunks in-process rather than
    round-tripped through disk.
    """

    def __init__(self, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        # {source_name: {doc_key: (version, nodes)}}
        self._docs: dict[str, dict[str, tuple[str, list[BaseNode]]]] = {}

    def write(self, source_name: str, doc_key: str, version: str, nodes: Sequence[BaseNode]) -> int:
        self._docs.setdefault(source_name, {})[doc_key] = (version, list(nodes))
        return len(nodes)

    def read(self, source_name: str) -> list[TextNode]:
        docs = self._docs.get(source_name, {})
        return [node for _version, nodes in docs.values() for node in nodes]

    def present(self, source_name: str) -> set[tuple[str, str]]:
        docs = self._docs.get(source_name, {})
        return {(doc_key, version) for doc_key, (version, _nodes) in docs.items()}

    def delete(self, source_name: str) -> None:
        self._docs.pop(source_name, None)
