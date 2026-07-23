"""Writes output to an S3 bucket."""

import json

import boto3


class S3OutputWriter:
    """Writes JSON payloads to an S3 bucket.

    Args:
        bucket: Target S3 bucket name.
        s3_client: Optional injected S3 client (for testing).
    """

    def __init__(self, bucket: str, s3_client=None) -> None:
        self._bucket = bucket
        self._s3 = s3_client or boto3.client("s3")

    def write(self, key: str, payload: dict) -> None:
        """Write a payload to s3://{bucket}/{key} as JSON."""
        body = json.dumps(payload, ensure_ascii=False)
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body.encode(),
            ContentType="application/json",
        )
