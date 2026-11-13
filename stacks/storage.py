"""CDK stack for DIA storage resources."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from config import AppConfig
from dia.naming import Bucket, Names
from stacks.shared.iam import permissions_boundary


class StorageStack(cdk.Stack):
    """Creates storage resources for the DIA extraction pipeline.

    Resources:
        S3 Buckets:
            - text-extracted: Extracted text JSON (staging area between text and graph extraction)
            - graph-raw: Raw graph extraction JSON output
            - graph-validated: Normalised/validated output ready for Neptune/AOSS
            - batch: Bedrock batch inference working area (transient)
            - agent-reports: agent query outputs (markdown and docx)
            - dbr-reports: DBR source documents for the knowledge bases
              (readouts/: post-DBR letters, reports/: DIA-generated DBR reports)
            - sr25-bids, sr21-bids, nao-reports, reports: source documents for the knowledge
              bases (reports holds efficiency-report and technology-report prefixes)
        DynamoDB Tables:
            - ledger: Tracks which documents have been successfully processed
        IAM:
            - batch-inference role: assumed by Bedrock Batch Inference jobs, scoped to the batch
              bucket (S3 read/write) plus bedrock:InvokeModel (required by the Bedrock batch
              inference service role itself to execute model invocations; resource is "*" since
              cross-region inference profiles fan out to per-region foundation-model ARNs)
    """

    def __init__(self, scope: Construct, construct_id: str, *, config: AppConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.text_extracted_bucket = self._data_bucket("TextExtracted", config.names, Bucket.TEXT_EXTRACTED)
        self.graph_raw_bucket = self._data_bucket("GraphRaw", config.names, Bucket.GRAPH_RAW)
        self.graph_validated_bucket = self._data_bucket("GraphValidated", config.names, Bucket.GRAPH_VALIDATED)

        self.batch_bucket = s3.Bucket(
            self,
            "Batch",
            bucket_name=config.names(Bucket.BATCH),
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

        self.agent_reports_bucket = self._data_bucket("AgentReports", config.names, Bucket.AGENT_REPORTS)
        self.dbr_reports_bucket = self._data_bucket("DbrReports", config.names, Bucket.DBR_REPORTS)

        # Source document buckets for the knowledge bases (and, later, the graph pipeline).
        # They start empty: copy the documents in from the old buckets (see issue #64).
        self.sr25_bids_bucket = self._data_bucket("Sr25Bids", config.names, Bucket.SR25_BIDS)
        self.sr21_bids_bucket = self._data_bucket("Sr21Bids", config.names, Bucket.SR21_BIDS)
        self.nao_reports_bucket = self._data_bucket("NaoReports", config.names, Bucket.NAO_REPORTS)
        self.reports_bucket = self._data_bucket("Reports", config.names, Bucket.REPORTS)

        self.ledger_table = dynamodb.Table(
            self,
            "Ledger",
            table_name=config.names("ledger"),
            partition_key=dynamodb.Attribute(
                name="document_key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Distinct from the pre-existing, Terraform-managed BatchInferenceRole
        # in this account, which is scoped to a different (shared) bucket.
        self.batch_inference_role = iam.Role(
            self,
            "BatchInferenceRole",
            role_name=config.names("batch-inference"),
            description="Assumed by Bedrock Batch Inference jobs to read/write the batch bucket.",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": config.account_number}},
            ),
            permissions_boundary=permissions_boundary(self, "BatchInferencePermissionsBoundary", config=config),
        )
        self.batch_bucket.grant_read_write(self.batch_inference_role)
        self.batch_inference_role.add_to_policy(
            iam.PolicyStatement(
                sid="BatchInference",
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        cdk.CfnOutput(
            self,
            "BatchInferenceRoleArn",
            value=self.batch_inference_role.role_arn,
            description="IAM role ARN for Bedrock Batch Inference jobs (BatchConfig.role_arn)",
        )

    def _data_bucket(self, construct_id: str, names: Names, bucket: Bucket) -> s3.Bucket:
        """A private, versioned, encrypted bucket, kept when the stack is deleted.

        The construct ID becomes part of the bucket's CloudFormation logical ID, so
        changing one makes CloudFormation replace the bucket.

        Args:
            construct_id: The construct ID.
            names: Builds the bucket's name for this environment.
            bucket: Which of our buckets this is.

        Returns:
            The bucket.
        """
        return s3.Bucket(
            self,
            construct_id,
            bucket_name=names(bucket),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
