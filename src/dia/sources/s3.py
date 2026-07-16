"""S3-backed document source implementation."""

import mimetypes

import boto3

from dia.types import DataSource, DocumentReference

# Fallback content types for common document extensions
_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _content_type_for(key: str) -> str:
    """Infer content type from a file key."""
    for ext, ct in _CONTENT_TYPES.items():
        if key.lower().endswith(ext):
            return ct
    # Fall back to mimetypes module
    guessed, _ = mimetypes.guess_type(key)
    return guessed or "application/octet-stream"


class S3DocumentSource:
    """Reads documents from an S3 bucket, filtered by a DataSource definition."""

    def __init__(self, data_source: DataSource, s3_client=None) -> None:
        self._data_source = data_source
        self._s3 = s3_client or boto3.client("s3")

    @property
    def data_source(self) -> DataSource:
        return self._data_source

    def list_documents(self) -> list[DocumentReference]:
        """List all documents matching the data source's prefix and file extensions."""
        refs: list[DocumentReference] = []
        paginator = self._s3.get_paginator("list_objects_v2")

        pages = paginator.paginate(
            Bucket=self._data_source.bucket,
            Prefix=self._data_source.prefix,
        )

        for page in pages:
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                if self._matches_extension(key):
                    refs.append(
                        DocumentReference(
                            key=key,
                            content_type=_content_type_for(key),
                            version=obj.get("ETag", ""),
                        )
                    )

        return refs

    def load_document(self, ref: DocumentReference) -> bytes:
        """Load the raw bytes of a document from S3."""
        response = self._s3.get_object(Bucket=self._data_source.bucket, Key=ref.key)
        return response["Body"].read()

    def _matches_extension(self, key: str) -> bool:
        """Check if a key matches the configured file extensions."""
        lower_key = key.lower()
        return any(lower_key.endswith(ext) for ext in self._data_source.file_extensions)
