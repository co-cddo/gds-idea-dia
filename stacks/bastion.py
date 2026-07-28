"""CDK stack for DIA bastion host.

Minimal EC2 instance for SSH port-forwarding to Neptune via EICE.
No IAM instance profile — purely a TCP relay for tunnel-based access.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from config import AppConfig


class BastionStack(cdk.Stack):
    """Creates a minimal bastion EC2 instance for Neptune tunnel access.

    The bastion sits in an isolated private subnet, reachable only via
    EC2 Instance Connect Endpoint (EICE) on port 22. Developers SSH into
    it with port-forwarding (-L 8182:<neptune>:8182) to reach Neptune
    from their local machine.

    No IAM instance profile is attached — this instance makes no AWS API
    calls itself. It's purely an SSH relay. IAM role + S3/Neptune permissions
    can be added in a future phase if load scripts need to run directly
    on the bastion.

    Resources:
        - EC2 instance (t3.nano)
        - Security group: inbound 22 from EICE SG, all outbound allowed
          (acceptable: isolated subnet has no internet route, so outbound
          can only reach other VPC resources like Neptune)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: AppConfig,
        vpc: ec2.IVpc,
        eice_security_group: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Security group for the bastion
        # allow_all_outbound=True is acceptable here because the bastion sits in
        # an isolated subnet with no internet route — egress can only reach other
        # VPC resources (Neptune, S3 via endpoint). This avoids a cross-stack
        # dependency cycle that would occur if we referenced neptune_security_group.
        self.bastion_security_group = ec2.SecurityGroup(
            self,
            "BastionSecurityGroup",
            vpc=vpc,
            description="Bastion host - inbound SSH from EICE, outbound within VPC",
            allow_all_outbound=True,
        )

        # Inbound: SSH from EICE only
        self.bastion_security_group.add_ingress_rule(
            peer=eice_security_group,
            connection=ec2.Port.tcp(22),
            description="SSH access from EICE tunnel",
        )

        # Minimal bastion instance — Amazon Linux 2023 (EC2 Instance Connect pre-installed)
        self.instance = ec2.Instance(
            self,
            "BastionInstance",
            instance_type=ec2.InstanceType("t3.nano"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_group=self.bastion_security_group,
            instance_name=config.resource_name("bastion"),
            # No key pair — access exclusively via EC2 Instance Connect (ephemeral keys)
        )
        self.instance.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        # Output the instance ID for the tunnel script
        cdk.CfnOutput(
            self,
            "BastionInstanceId",
            value=self.instance.instance_id,
            description="Bastion instance ID for neptune-tunnel.sh",
        )
