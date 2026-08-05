"""CDK stack for DIA Neptune database resources.

Sets up a Neptune Database cluster with IAM authentication
enabled, suitable for development/testing of the knowledge graph pipeline.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_neptune as neptune
from constructs import Construct

from config import AppConfig


class NeptuneStack(cdk.Stack):
    """Creates a Neptune Database cluster for the DIA knowledge graph.

    Resources:
        - Security group for Neptune (incoming connection from bastion on 8182)
        - DB subnet group spanning the VPC's isolated subnets (2 AZs)
        - Neptune cluster with IAM auth + encryption enabled
        - Single db.t3.medium instance (smallest available, can scale later)

    The cluster uses DESTROY removal policy and has deletion protection
    disabled for while we develop this, can change to RETAIN later.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: AppConfig,
        vpc: ec2.IVpc,
        bastion_security_group: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Neptune security group — created here (not in NetworkingStack) to avoid
        # cross-stack dependency cycles. Ingress from bastion on port 8182.
        self.neptune_security_group = ec2.SecurityGroup(
            self,
            "NeptuneSecurityGroup",
            vpc=vpc,
            description="Security group for Neptune cluster",
            allow_all_outbound=False,
        )
        self.neptune_security_group.add_ingress_rule(
            peer=bastion_security_group,
            connection=ec2.Port.tcp(8182),
            description="Allow Neptune access from bastion port-forwarding",
        )

        # Subnet group spanning all isolated subnets (Neptune requires >= 2 AZs)
        subnet_group = neptune.CfnDBSubnetGroup(
            self,
            "SubnetGroup",
            db_subnet_group_name=config.resource_name("neptune-subnets"),
            db_subnet_group_description="Isolated subnets for DIA Neptune cluster",
            subnet_ids=[subnet.subnet_id for subnet in vpc.isolated_subnets],
        )

        # Neptune cluster — IAM auth enabled for SigV4-signed boto3 access
        self.cluster = neptune.CfnDBCluster(
            self,
            "Cluster",
            db_cluster_identifier=config.resource_name("neptune"),
            db_subnet_group_name=subnet_group.ref,
            vpc_security_group_ids=[self.neptune_security_group.security_group_id],
            iam_auth_enabled=True,
            storage_encrypted=True,
            deletion_protection=False,
        )
        self.cluster.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Single writer instance — db.t3.medium is the smallest Neptune instance
        self.instance = neptune.CfnDBInstance(
            self,
            "Instance",
            db_instance_class="db.t3.medium",
            db_cluster_identifier=self.cluster.ref,
            db_instance_identifier=config.resource_name("neptune-instance"),
        )
        self.instance.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Outputs for use by the tunnel helper script
        cdk.CfnOutput(
            self,
            "NeptuneEndpoint",
            value=self.cluster.attr_endpoint,
            description="Neptune cluster endpoint (DNS) for tunnel script",
        )
        cdk.CfnOutput(
            self,
            "NeptunePort",
            value=self.cluster.attr_port,
            description="Neptune cluster port",
        )
