from stacks.bastion import BastionStack


def test_creates_bastion_instance(synth):
    template, _, _ = synth(BastionStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="eice_security_group")
    template.resource_count_is("AWS::EC2::Instance", 1)


def test_instance_type_is_t3_nano(synth):
    template, _, _ = synth(BastionStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="eice_security_group")
    template.has_resource_properties("AWS::EC2::Instance", {"InstanceType": "t3.nano"})


def test_creates_bastion_security_group(synth):
    template, _, _ = synth(BastionStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="eice_security_group")
    template.resource_count_is("AWS::EC2::SecurityGroup", 1)


def test_bastion_sg_allows_inbound_ssh(synth):
    template, _, _ = synth(BastionStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="eice_security_group")
    template.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {
            "FromPort": 22,
            "ToPort": 22,
            "IpProtocol": "tcp",
            "Description": "SSH access from EICE tunnel",
        },
    )


def test_outputs_bastion_instance_id(synth):
    template, _, _ = synth(BastionStack, needs_vpc=True, needs_sg=True, sg_kwarg_name="eice_security_group")
    outputs = template.find_outputs("*")
    assert any("BastionInstanceId" in key for key in outputs)
