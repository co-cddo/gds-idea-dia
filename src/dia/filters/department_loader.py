"""Loads department metadata CSVs from S3.

Historic metadata lives at a single, fixed key. GATS metadata is exported
periodically to a prefix — this loads whichever file was modified most
recently, matching the old pipeline's "latest export wins" behaviour.
"""

import csv
import io

import boto3


def load_csv_from_s3(bucket: str, key: str, s3_client=None) -> list[dict]:
    """Load a CSV object from S3 into a list of dict rows.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.
        s3_client: Optional injected S3 client (for testing).

    Returns:
        One dict per CSV row, keyed by column header.
    """
    client = s3_client or boto3.client("s3")
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(body)))


def find_latest_key(bucket: str, prefix: str, s3_client=None) -> str:
    """Find the most recently modified object key under a prefix.

    Ties in LastModified (common with rapid uploads/tests) are broken by
    key name — export filenames are date-prefixed, so lexicographic order
    matches chronological order.

    Args:
        bucket: S3 bucket name.
        prefix: S3 prefix to search.
        s3_client: Optional injected S3 client (for testing).

    Returns:
        The key of the most recently modified object.

    Raises:
        FileNotFoundError: If no objects exist under the prefix.
    """
    client = s3_client or boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")

    objects: list[dict] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))

    if not objects:
        msg = f"No files found in s3://{bucket}/{prefix}"
        raise FileNotFoundError(msg)

    latest = max(objects, key=lambda obj: (obj["LastModified"], obj["Key"]))
    return latest["Key"]


def load_latest_csv_from_s3(bucket: str, prefix: str, s3_client=None) -> list[dict]:
    """Load the most recently modified CSV under a prefix.

    Args:
        bucket: S3 bucket name.
        prefix: S3 prefix to search for CSV exports.
        s3_client: Optional injected S3 client (for testing).

    Returns:
        One dict per CSV row from the latest file, keyed by column header.

    Raises:
        FileNotFoundError: If no objects exist under the prefix.
    """
    client = s3_client or boto3.client("s3")
    key = find_latest_key(bucket, prefix, s3_client=client)
    return load_csv_from_s3(bucket, key, s3_client=client)
