from stacks.neptune import NeptuneStack


def test_creates_neptune_cluster(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.resource_count_is("AWS::Neptune::DBCluster", 1)


def test_creates_neptune_instance(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.resource_count_is("AWS::Neptune::DBInstance", 1)


def test_creates_subnet_group(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.resource_count_is("AWS::Neptune::DBSubnetGroup", 1)


def test_creates_neptune_security_group(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.resource_count_is("AWS::EC2::SecurityGroup", 1)


def test_neptune_sg_allows_ingress_from_bastion_on_8182(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {
            "FromPort": 8182,
            "ToPort": 8182,
            "IpProtocol": "tcp",
            "Description": "Allow Neptune access from bastion port-forwarding",
        },
    )


def test_cluster_has_iam_auth_enabled(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.has_resource_properties(
        "AWS::Neptune::DBCluster",
        {"IamAuthEnabled": True},
    )


def test_cluster_has_deletion_protection_disabled(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.has_resource_properties(
        "AWS::Neptune::DBCluster",
        {"DeletionProtection": False},
    )


def test_cluster_has_serverless_scaling(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.has_resource_properties(
        "AWS::Neptune::DBCluster",
        {"ServerlessScalingConfiguration": {"MinCapacity": 1, "MaxCapacity": 48}},
    )


def test_instance_is_serverless(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    template.has_resource_properties(
        "AWS::Neptune::DBInstance",
        {"DBInstanceClass": "db.serverless"},
    )


def test_outputs_neptune_endpoint(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    outputs = template.find_outputs("*")
    assert any("NeptuneEndpoint" in key for key in outputs)


def test_neptune_sg_allows_ingress_from_pipeline_tasks_when_given_their_security_group():
    import aws_cdk as cdk
    from aws_cdk import assertions
    from aws_cdk import aws_ec2 as ec2
    from gds_idea_cdk_constructs import DeploymentEnvironment

    from config import AppConfig

    config = AppConfig(environment=DeploymentEnvironment.DEVELOPMENT)
    app = cdk.App()
    env = cdk.Environment(account=config.account_number, region=config.region)
    harness = cdk.Stack(app, "Harness", env=env)
    vpc = ec2.Vpc.from_vpc_attributes(
        harness,
        "Vpc",
        vpc_id="vpc-12345",
        availability_zones=["eu-west-2a", "eu-west-2b"],
        isolated_subnet_ids=["subnet-a", "subnet-b"],
    )
    stack = NeptuneStack(
        app,
        "TestStack",
        config=config,
        vpc=vpc,
        bastion_security_group=ec2.SecurityGroup(harness, "BastionSg", vpc=vpc),
        task_security_group=ec2.SecurityGroup(harness, "TaskSg", vpc=vpc),
        env=env,
    )

    assertions.Template.from_stack(stack).has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {
            "FromPort": 8182,
            "ToPort": 8182,
            "IpProtocol": "tcp",
            "Description": "Allow Neptune access from pipeline tasks",
        },
    )


def test_neptune_sg_has_no_task_ingress_without_a_task_security_group(synth):
    template, _, _ = synth(NeptuneStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="bastion_security_group")
    ingress = template.find_resources("AWS::EC2::SecurityGroupIngress")

    assert all(r["Properties"]["Description"] != "Allow Neptune access from pipeline tasks" for r in ingress.values())
