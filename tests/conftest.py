import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from aws_cdk import aws_ec2 as ec2
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig


@pytest.fixture
def synth():
    """Factory fixture that synthesises any CDK stack and returns its template.

    Handles both simple stacks (like StorageStack, which only need config/env)
    and VPC-dependent stacks (like NetworkingStack, NeptuneStack, BastionStack)
    via optional flags.

    Args:
        stack_class: The CDK Stack class to synthesise.
        environment: DeploymentEnvironment (default: DEVELOPMENT).
        needs_vpc: If True, creates a dummy VPC (2 AZs, isolated subnets,
            no NAT) in a sibling harness stack and passes it as vpc= to the
            stack constructor. Required for stacks that accept a vpc parameter e.g networking, bastion.
        needs_sg: If True (requires needs_vpc=True), creates a security group
            in the harness stack and injects it via sg_kwarg_name.
        sg_kwarg_name: The keyword argument name to pass the security group as
            (e.g. "bastion_security_group" for NeptuneStack, "eice_security_group"
            for BastionStack).
        **extra_kwargs: Additional kwargs passed to the stack constructor.

    Returns:
        - template (if needs_vpc=False)
        - (template, vpc) (if needs_vpc=True, needs_sg=False)
        - (template, vpc, security_group) (if needs_vpc=True, needs_sg=True)
    """

    def _synth(
        stack_class,
        environment=DeploymentEnvironment.DEVELOPMENT,
        needs_vpc=False,
        needs_sg=False,
        sg_kwarg_name="security_group",
        **extra_kwargs,
    ):
        config = AppConfig(environment=environment)
        app = cdk.App()
        env = cdk.Environment(account=config.account_number, region=config.region)

        vpc = None
        sg = None

        if needs_vpc:
            # Build VPC inside the same app (as a sibling stack for construct scoping)
            # to avoid CDK's 'CannotReferenceAcrossApps' error
            harness_stack = cdk.Stack(app, "HarnessStack", env=env)
            vpc = ec2.Vpc(
                harness_stack,
                "Vpc",
                max_azs=2,
                nat_gateways=0,
                subnet_configuration=[
                    ec2.SubnetConfiguration(name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
                ],
            )
            extra_kwargs["vpc"] = vpc

            if needs_sg:
                sg = ec2.SecurityGroup(harness_stack, "Sg", vpc=vpc)
                extra_kwargs[sg_kwarg_name] = sg

        stack = stack_class(
            app,
            "TestStack",
            config=config,
            env=env,
            **extra_kwargs,
        )
        template = assertions.Template.from_stack(stack)

        if needs_vpc:
            if needs_sg:
                return template, vpc, sg
            return template, vpc
        return template

    return _synth
