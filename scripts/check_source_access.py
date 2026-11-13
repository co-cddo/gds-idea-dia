"""Check which identity can read each GATS / SR25 source location. Read-only.

Run from a normal dev session (no exported role credentials):

    uv run python scripts/check_source_access.py

For each location it tries two sessions: your own, and one built from the
cross-account role's credentials. It prints which identity each S3 call is made
as, which account owns each bucket, and what can be listed. It never prints
document names or case data: only counts, dates, file types, export file names
and the export's column names.
"""

from __future__ import annotations

from collections import Counter

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from dia.cli_helpers import current_names
from dia.runtime_config import RuntimeConfig

REGION = "eu-west-2"
DEV_ACCOUNT = "992382722318"
PROD_ACCOUNT = "588077357019"

DOCS_BUCKET = "c-af-get-approval-spend-service-business-cases"
META_BUCKET = "c-af-get-approval-spend-service-business-cases-dev"
SR25_BUCKET = "gds-idea-sr-query-documentstore-dev"

# (label, bucket, prefix, what to report)
LOCATIONS = [
    ("GATS documents", DOCS_BUCKET, "files/", "documents"),
    ("prod bucket top-level folders", DOCS_BUCKET, "", "folders"),
    ("GATS export", META_BUCKET, "spend-controls-raw-data/", "export"),
    ("historic metadata", META_BUCKET, "department_files/", "names"),
    ("SR25 documents", SR25_BUCKET, "", "documents"),
]


def _err(e: Exception) -> str:
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        return f"{err.get('Code')}: {err.get('Message')}"
    return str(e)


def sessions() -> dict[str, boto3.Session]:
    """Your own session, and (in dev) one built from the cross-account role's credentials."""
    base = boto3.Session(region_name=REGION)
    role_arn = RuntimeConfig.load(current_names()).cross_account_role_arn
    out = {"own": base}
    if not role_arn:
        print("No cross_account_role_arn in the runtime config (prod?), so only your own session is used.\n")
        return out
    creds = base.client("sts").assume_role(RoleArn=role_arn, RoleSessionName="dia-source-check")["Credentials"]
    out["cross-account"] = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=REGION,
    )
    return out


def owner(s3, bucket: str) -> str:
    """Which account owns the bucket, from head_bucket with ExpectedBucketOwner."""
    for name, account in (("dev", DEV_ACCOUNT), ("prod", PROD_ACCOUNT)):
        try:
            s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
            return f"{name} ({account})"
        except ClientError:
            continue
    return "unknown (not readable as either account's bucket from this session)"


def list_all(s3, bucket: str, prefix: str) -> list[dict]:
    """Every object under the prefix."""
    objects = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


def report(s3, bucket: str, prefix: str, kind: str) -> None:
    """Print what can be seen at one location, without printing document names or case data."""
    if kind == "folders":
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
        print("    folders:", [p["Prefix"] for p in resp.get("CommonPrefixes", [])])
        return

    objects = list_all(s3, bucket, prefix)
    print(f"    objects: {len(objects)}")
    if not objects:
        return
    objects.sort(key=lambda o: o["LastModified"])
    print(f"    oldest: {objects[0]['LastModified']:%Y-%m-%d}  newest: {objects[-1]['LastModified']:%Y-%m-%d}")

    if kind == "documents":
        types = Counter(o["Key"].rsplit(".", 1)[-1].lower() if "." in o["Key"] else "(none)" for o in objects)
        print("    file types:", dict(types.most_common(8)))
        return

    print("    newest files:")
    for o in objects[-5:]:
        print(f"      {o['LastModified']:%Y-%m-%d %H:%M}  {o['Size']:>12,}  {o['Key']}")

    if kind == "export":
        newest = objects[-1]["Key"]
        head = s3.get_object(Bucket=bucket, Key=newest, Range="bytes=0-4095")["Body"].read()
        if head[:2] == b"PK":
            print(f"    {newest} is an Excel/zip file, not CSV: header not shown")
            return
        header = head.decode("utf-8-sig", errors="replace").splitlines()[0]
        columns = [c.strip().strip('"') for c in header.split(",")]
        print(f"    columns ({len(columns)}): {columns}")
        print("    look like dates:", [c for c in columns if "date" in c.lower()])
        print("    look like file lists:", [c for c in columns if "file" in c.lower()])


def main() -> None:
    for name, session in sessions().items():
        arn = session.client("sts").get_caller_identity()["Arn"]
        print(f"=== session '{name}': S3 calls made as {arn}\n")
        s3 = session.client("s3")
        for label, bucket, prefix, kind in LOCATIONS:
            print(f"  {label}: s3://{bucket}/{prefix}")
            print(f"    owner: {owner(s3, bucket)}")
            try:
                report(s3, bucket, prefix, kind)
            except (ClientError, BotoCoreError) as e:
                print(f"    DENIED/ERROR: {_err(e)}")
            print()


if __name__ == "__main__":
    main()
