"""CDK stack for DIA S3 storage buckets."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config import AppConfig


class StorageStack(cdk.Stack):
    """Creates S3 buckets for the DIA extraction pipeline.

    Buckets:
        - graph-raw: Raw extraction JSON output
        - graph-validated: Normalised/validated output ready for Neptune/AOSS
        - batch: Bedrock batch inference working area (transient)
    """

    def __init__(self, scope: Construct, construct_id: str, *, config: AppConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.graph_raw_bucket = s3.Bucket(
            self,
            "GraphRaw",
            bucket_name=config.bucket("graph-raw"),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        self.graph_validated_bucket = s3.Bucket(
            self,
            "GraphValidated",
            bucket_name=config.bucket("graph-validated"),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        self.batch_bucket = s3.Bucket(
            self,
            "Batch",
            bucket_name=config.bucket("batch"),
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(30),
                        )
                    ],
                    expiration=cdk.Duration.days(90),
                ),
            ],
        )
