"""Reads Stage 1 (text extraction) output to feed Stage 2 (graph extraction).

Stage 1 writes one JSON file per document (TextExtractionOutput, see
pipeline/models.py) to output/<source_name>/<key>.json locally
(LocalOutputWriter) or s3://<bucket>/<source_name>/<key>.json in production
(S3OutputWriter). <key> may itself contain slashes (e.g. "files/report.pdf"),
so output lives in nested paths, not a flat directory — listing must be
recursive.

There's no cheap "list without loading" step here, unlike DocumentSource:
each output's `version` field lives inside the JSON body, not in filesystem/
S3 object metadata, so listing requires reading every file's content anyway.
"""

import json
from pathlib import Path
from typing import Protocol

import boto3

from dia.pipeline.models import TextExtractionOutput


class TextExtractionOutputSource(Protocol):
    """Reads previously-extracted text (Stage 1 output) for a source."""

    def list_outputs(self, source_name: str) -> list[TextExtractionOutput]:
        """Load every TextExtractionOutput recorded for this source."""
        ...


class LocalTextExtractionOutputSource:
    """Reads Stage 1 output from local disk (output/<source_name>/**/*.json)."""

    def __init__(self, base_dir: Path | str = "output") -> None:
        self._base_dir = Path(base_dir)

    def list_outputs(self, source_name: str) -> list[TextExtractionOutput]:
        """Load every TextExtractionOutput JSON file under base_dir/source_name/."""
        source_dir = self._base_dir / source_name
        if not source_dir.exists():
            return []
        return [_parse_output(path.read_text(encoding="utf-8")) for path in sorted(source_dir.rglob("*.json"))]


class S3TextExtractionOutputSource:
    """Reads Stage 1 output from S3 (s3://bucket/source_name/**/*.json)."""

    def __init__(self, bucket: str, s3_client=None) -> None:
        self._bucket = bucket
        self._s3 = s3_client or boto3.client("s3")

    def list_outputs(self, source_name: str) -> list[TextExtractionOutput]:
        """Load every TextExtractionOutput JSON object under s3://bucket/source_name/."""
        outputs: list[TextExtractionOutput] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=f"{source_name}/")

        for page in pages:
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                if not key.endswith(".json"):
                    continue
                response = self._s3.get_object(Bucket=self._bucket, Key=key)
                outputs.append(_parse_output(response["Body"].read().decode("utf-8")))

        return outputs


def _parse_output(raw: str) -> TextExtractionOutput:
    """Parse a TextExtractionOutput JSON string, as written by an OutputWriter."""
    return TextExtractionOutput(**json.loads(raw))
