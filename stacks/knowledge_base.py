"""CDK stack for DIA's Bedrock knowledge bases."""

from __future__ import annotations

from collections.abc import Sequence

import aws_cdk as cdk
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

from config import AppConfig
from stacks.constructs.knowledge_base import KnowledgeBase, KnowledgeBaseSpec
from stacks.shared.iam import permissions_boundary


def knowledge_base_name(config: AppConfig, key: str) -> str:
    """Physical name of a knowledge base, e.g. `dia-kb-dbr-reports-dev` for key `dbr_reports`."""
    return config.names(f"kb-{key.replace('_', '-')}")


class KnowledgeBaseStack(cdk.Stack):
    """One S3 Vectors bucket, shared by a Bedrock knowledge base per spec.

    Resources:
        - S3 Vectors bucket, retained on delete because rebuilding the vectors
          means re-ingesting every document
        - Per spec: a vector index (retained), a service role with the account's
          permissions boundary, the knowledge base and its S3 data sources
          (see `KnowledgeBase`)

    Deploying creates the knowledge bases but does not ingest anything. Start an
    ingestion job for each data source afterwards.

    Attributes:
        knowledge_bases: The knowledge base constructs, keyed by spec key.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: AppConfig,
        specs: Sequence[KnowledgeBaseSpec],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        cdk.Tags.of(self).add("ResourceType", "BedrockKnowledgeBase")
        cdk.Tags.of(self).add("Service", "KnowledgeBases")

        vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "VectorBucket",
            vector_bucket_name=config.names("kb-vectors"),
        )
        vector_bucket.apply_removal_policy(cdk.RemovalPolicy.RETAIN)

        boundary = permissions_boundary(self, "PermissionsBoundary", config=config)

        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        for spec in specs:
            construct_id_base = spec.key.replace("_", " ").title().replace(" ", "")
            kb = KnowledgeBase(
                self,
                construct_id_base,
                spec=spec,
                name=knowledge_base_name(config, spec.key),
                vector_bucket=vector_bucket,
                permissions_boundary=boundary,
            )
            self.knowledge_bases[spec.key] = kb

            cdk.CfnOutput(self, f"{construct_id_base}KnowledgeBaseId", value=kb.knowledge_base_id)
            cdk.CfnOutput(self, f"{construct_id_base}RoleArn", value=kb.role.role_arn)
