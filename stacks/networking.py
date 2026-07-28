"""CDK stack for DIA networking resources.

Builds the EICE endpoint and its security group within the shared org VPC.
EICE provides SSH access (port 22) to the bastion host — confirmed via
live testing that EICE does not support arbitrary ports like Neptune's 8182,
so a bastion is needed as an intermediate stage.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from config import AppConfig


class NetworkingStack(cdk.Stack):
    """Creates networking resources for the DIA infrastructure within the shared VPC.

    Accepts either a resolved ``vpc`` object (for unit tests) or a ``vpc_id``
    string (for production — triggers a Vpc.from_lookup at synth time).

    Resources:
        Security Groups:
            - eice-sg: Outbound allowed (reaches bastion's SSH daemon via EICE)
        EC2 Instance Connect Endpoint:
            - EICE in one isolated subnet, attached to eice-sg
            - Enables `aws ec2-instance-connect ssh` to the bastion (port 22 only)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: AppConfig,
        vpc: ec2.IVpc | None = None,
        vpc_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if vpc is not None:
            self.vpc = vpc
        elif vpc_id is not None:
            self.vpc = ec2.Vpc.from_lookup(self, "SharedVpc", vpc_id=vpc_id)
        else:
            raise ValueError("Either vpc or vpc_id must be provided")

        # Security group for EICE — outbound to reach the bastion's SSH port
        self.eice_security_group = ec2.SecurityGroup(
            self,
            "EiceSecurityGroup",
            vpc=self.vpc,
            description="Security group for EC2 Instance Connect Endpoint",
            allow_all_outbound=True,
        )

        # EC2 Instance Connect Endpoint
        # Placed in the first isolated subnet; used to SSH into the bastion (port 22)
        isolated_subnets = self.vpc.isolated_subnets
        self.instance_connect_endpoint = ec2.CfnInstanceConnectEndpoint(
            self,
            "InstanceConnectEndpoint",
            subnet_id=isolated_subnets[0].subnet_id,
            security_group_ids=[self.eice_security_group.security_group_id],
            preserve_client_ip=False,
        )

        # Output the EICE endpoint ID for use in the tunnel helper script
        cdk.CfnOutput(
            self,
            "EiceEndpointId",
            value=self.instance_connect_endpoint.attr_id,
            description="EC2 Instance Connect Endpoint ID for neptune-tunnel.sh",
        )
