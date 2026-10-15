"""Tests for the NetworkingStack — the EICE endpoint, and the security groups for it and for pipeline tasks."""

from aws_cdk import assertions

from stacks.networking import NetworkingStack


def test_creates_eice_endpoint(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.resource_count_is("AWS::EC2::InstanceConnectEndpoint", 1)


def test_creates_a_security_group_for_the_endpoint_and_one_for_tasks(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.resource_count_is("AWS::EC2::SecurityGroup", 2)


def test_task_security_group_allows_all_outbound_and_no_inbound(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": "Security group for DIA pipeline tasks",
            "SecurityGroupEgress": [{"CidrIp": "0.0.0.0/0", "IpProtocol": "-1"}],
        },
    )
    assert not template.find_resources("AWS::EC2::SecurityGroupIngress")
    for group in template.find_resources("AWS::EC2::SecurityGroup").values():
        assert "SecurityGroupIngress" not in group["Properties"]


def test_eice_endpoint_has_security_group(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.has_resource_properties(
        "AWS::EC2::InstanceConnectEndpoint",
        {"SecurityGroupIds": assertions.Match.any_value()},
    )


def test_outputs_eice_endpoint_id(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    outputs = template.find_outputs("*")
    assert any("EiceEndpointId" in key for key in outputs)
