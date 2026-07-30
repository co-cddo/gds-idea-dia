"""Tests for the NetworkingStack — EICE endpoint and its security group."""

from aws_cdk import assertions

from stacks.networking import NetworkingStack


def test_creates_eice_endpoint(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.resource_count_is("AWS::EC2::InstanceConnectEndpoint", 1)


def test_creates_one_security_group(synth):
    template, _ = synth(NetworkingStack, needs_vpc=True)
    template.resource_count_is("AWS::EC2::SecurityGroup", 1)


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
