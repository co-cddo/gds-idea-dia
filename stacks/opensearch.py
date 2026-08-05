"""CDK stack for DIA OpenSearch Serverless resources.

Provisions a next-generation (NEXTGEN) OpenSearch Serverless vector-search
collection inside a collection group configured for scale-to-zero, suitable
for the knowledge-graph / embeddings side of the DIA pipeline.
"""

from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk import aws_opensearchserverless as aoss
from constructs import Construct

from config import AppConfig


class OpenSearchStack(cdk.Stack):
    """Creates a scale-to-zero OpenSearch Serverless (AOSS) vector collection.

    Resources:
        - Encryption security policy (AWS-owned KMS key) scoped to the collection
        - Network security policy exposing the collection + dashboards publicly
        - NEXTGEN collection group with scale-to-zero (min 0, max 8 OCU for
          both indexing and search); standby replicas enabled (required for
          NEXTGEN groups)
        - VECTORSEARCH collection joined to the collection group
        - Data-access policy granting the account root principal collection +
          index permissions (dev placeholder — tighten to a specific role later)

    Scale-to-zero: because the collection group is generation=NEXTGEN with a
    minimum OCU of 0 for both indexing and search, compute scales to zero (and
    billing stops) after ~10 minutes with no requests across the group. The
    first request after idle incurs 10-30s of cold-start latency. Only the
    S3-backed storage continues to bill while idle.

    Network access is public but restricted by the data-access policy to the
    account's IAM principals (SigV4-signed requests). Unlike Neptune, this stack
    has no VPC dependency.
    """

    def __init__(self, scope: Construct, construct_id: str, *, config: AppConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        collection_name = config.resource_name("aoss")
        group_name = config.resource_name("aoss-group")
        collection_resource = f"collection/{collection_name}"

        # Encryption policy — required before a collection can be created.
        # Uses an AWS-owned KMS key (aws_owned_key=True).
        encryption_policy = aoss.CfnSecurityPolicy(
            self,
            "EncryptionPolicy",
            name=config.resource_name("aoss-encryption"),
            type="encryption",
            policy=json.dumps(
                {
                    "Rules": [
                        {
                            "ResourceType": "collection",
                            "Resource": [collection_resource],
                        }
                    ],
                    "AWSOwnedKey": True,
                }
            ),
        )

        # Network policy — public access to both the collection endpoint and
        # the OpenSearch Dashboards endpoint. Access is still gated by the
        # data-access policy (IAM SigV4).
        network_policy = aoss.CfnSecurityPolicy(
            self,
            "NetworkPolicy",
            name=config.resource_name("aoss-network"),
            type="network",
            policy=json.dumps(
                [
                    {
                        "Rules": [
                            {
                                "ResourceType": "collection",
                                "Resource": [collection_resource],
                            },
                            {
                                "ResourceType": "dashboard",
                                "Resource": [collection_resource],
                            },
                        ],
                        "AllowFromPublic": True,
                    }
                ]
            ),
        )

        # NEXTGEN collection group with scale-to-zero (min OCU 0 for both
        # indexing and search). Max capped at 8 OCU each to bound cost.
        # Valid OCU values are 0, 2, 4, 8, 16, or any multiple of 16.
        # NEXTGEN groups require StandbyReplicas=ENABLED; scale-to-zero is
        # driven by min OCU=0, independent of standby replicas.
        self.collection_group = aoss.CfnCollectionGroup(
            self,
            "CollectionGroup",
            name=group_name,
            standby_replicas="ENABLED",
            generation="NEXTGEN",
            capacity_limits=aoss.CfnCollectionGroup.CapacityLimitsProperty(
                min_indexing_capacity_in_ocu=0,
                max_indexing_capacity_in_ocu=8,
                min_search_capacity_in_ocu=0,
                max_search_capacity_in_ocu=8,
            ),
        )

        # Vector-search collection joined to the group. Must be created after
        # the encryption + network policies and the collection group exist.
        # Standby matches the NEXTGEN group requirement (ENABLED).
        self.collection = aoss.CfnCollection(
            self,
            "Collection",
            name=collection_name,
            type="VECTORSEARCH",
            standby_replicas="ENABLED",
            collection_group_name=group_name,
        )
        self.collection.add_dependency(encryption_policy)
        self.collection.add_dependency(network_policy)
        self.collection.add_dependency(self.collection_group)

        # Data-access policy — grants the account root principal full collection
        # and index permissions. Dev placeholder; tighten to the specific
        # pipeline/Lambda role ARN before production.
        root_principal = f"arn:aws:iam::{config.account_number}:root"
        data_access_policy = aoss.CfnAccessPolicy(
            self,
            "DataAccessPolicy",
            name=config.resource_name("aoss-access"),
            type="data",
            policy=json.dumps(
                [
                    {
                        "Rules": [
                            {
                                "ResourceType": "collection",
                                "Resource": [collection_resource],
                                "Permission": [
                                    "aoss:CreateCollectionItems",
                                    "aoss:DeleteCollectionItems",
                                    "aoss:UpdateCollectionItems",
                                    "aoss:DescribeCollectionItems",
                                ],
                            },
                            {
                                "ResourceType": "index",
                                "Resource": [f"index/{collection_name}/*"],
                                "Permission": [
                                    "aoss:CreateIndex",
                                    "aoss:DeleteIndex",
                                    "aoss:UpdateIndex",
                                    "aoss:DescribeIndex",
                                    "aoss:ReadDocument",
                                    "aoss:WriteDocument",
                                ],
                            },
                        ],
                        "Principal": [root_principal],
                    }
                ]
            ),
        )
        data_access_policy.add_dependency(self.collection)

        # Outputs for wiring the collection endpoint into the aoss-endpoint secret.
        cdk.CfnOutput(
            self,
            "AossCollectionEndpoint",
            value=self.collection.attr_collection_endpoint,
            description="OpenSearch Serverless collection endpoint (DNS)",
        )
        cdk.CfnOutput(
            self,
            "AossDashboardEndpoint",
            value=self.collection.attr_dashboard_endpoint,
            description="OpenSearch Serverless dashboards endpoint",
        )
