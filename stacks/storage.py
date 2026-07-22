"""CDK stack for DIA storage resources."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config import AppConfig


class StorageStack(cdk.Stack):
    """Creates storage resources for the DIA extraction pipeline.

    Resources:
        S3 Buckets:
            - text-extracted: Extracted text JSON (staging area between text and graph extraction)
            - graph-raw: Raw graph extraction JSON output
            - graph-validated: Normalised/validated output ready for Neptune/AOSS
            - batch: Bedrock batch inference working area (transient)
        DynamoDB Tables:
            - ledger: Tracks which documents have been successfully processed
    """

    def __init__(self, scope: Construct, construct_id: str, *, config: AppConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.text_extracted_bucket = s3.Bucket(
            self,
            "TextExtracted",
            bucket_name=config.bucket("text-extracted"),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

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

        self.ledger_table = dynamodb.Table(
            self,
            "Ledger",
            table_name=config.resource_name("ledger"),
            partition_key=dynamodb.Attribute(
                name="document_key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
