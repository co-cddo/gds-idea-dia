"""Writes output to local disk."""

import json
from pathlib import Path


class LocalOutputWriter:
    """Writes JSON payloads to local disk, mirroring the given key as a path.

    Useful for local development/testing without touching S3.
    """

    def __init__(self, output_dir: Path | str) -> None:
        self._output_dir = Path(output_dir)

    def write(self, key: str, payload: dict) -> None:
        """Write a payload to {output_dir}/{key}, creating parent dirs as needed."""
        path = self._output_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
