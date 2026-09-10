"""Persists chunks between the chunking and extraction stages.

Chunking (splitting documents into TextNodes) and graph extraction (LLM
propositions/topics per chunk) are separate stages joined only by chunks on
disk — see docs/adr/0001-lower-level-graphrag-toolkit-usage.md for why. If
extraction fails, chunks already produced are untouched: no need to redo the
(comparatively slow, embedding-heavy) chunking stage to retry extraction.

One JSONL file per source, one TextNode.to_dict() per line — the same
serialisation graphrag_toolkit itself uses for its own temp node files
(indexing/extract/batch_extractor_base.py), so relationships/metadata/
exclusions are known to round-trip correctly.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from llama_index.core.schema import BaseNode, TextNode


class ChunkStore(Protocol):
    """Reads/writes chunks for a source, keyed by source name."""

    def write(self, source_name: str, nodes: Sequence[BaseNode]) -> int:
        """Persist nodes for a source, replacing anything already stored.

        Returns the number of nodes written.
        """
        ...

    def read(self, source_name: str) -> list[TextNode]:
        """Load previously-written nodes for a source. [] if none exist."""
        ...

    def delete(self, source_name: str) -> None:
        """Remove stored nodes for a source. No-op if none exist."""
        ...

    def exists(self, source_name: str) -> bool:
        """Whether nodes are currently stored for a source."""
        ...


class LocalChunkStore:
    """Stores chunks as one JSONL file per source on local disk.

    Path: {base_dir}/chunks/{source_name}.jsonl

    Writes go to a temp file then an atomic rename, so a file is either
    the complete previous write or absent — never a partial one.
    """

    def __init__(self, base_dir: Path | str = "output") -> None:
        self._chunks_dir = Path(base_dir) / "chunks"

    def _path(self, source_name: str) -> Path:
        return self._chunks_dir / f"{source_name}.jsonl"

    def write(self, source_name: str, nodes: Sequence[BaseNode]) -> int:
        path = self._path(source_name)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for node in nodes:
                f.write(json.dumps(node.to_dict(), ensure_ascii=False))
                f.write("\n")
        tmp_path.replace(path)

        return len(nodes)

    def read(self, source_name: str) -> list[TextNode]:
        path = self._path(source_name)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            return [TextNode.from_json(line) for line in f if line.strip()]

    def delete(self, source_name: str) -> None:
        self._path(source_name).unlink(missing_ok=True)

    def exists(self, source_name: str) -> bool:
        return self._path(source_name).exists()


class InMemoryChunkStore:
    """Captures written nodes in memory instead of persisting them.

    Useful for tests (assert on what was written without tmp_path) and for
    programmatic use where you want chunks in-process rather than
    round-tripped through disk.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, list[BaseNode]] = {}

    def write(self, source_name: str, nodes: Sequence[BaseNode]) -> int:
        self._nodes[source_name] = list(nodes)
        return len(nodes)

    def read(self, source_name: str) -> list[TextNode]:
        return list(self._nodes.get(source_name, []))

    def delete(self, source_name: str) -> None:
        self._nodes.pop(source_name, None)

    def exists(self, source_name: str) -> bool:
        return source_name in self._nodes
