from stacks.opensearch import OpenSearchStack


def test_creates_collection_group(synth):
    template = synth(OpenSearchStack)
    template.resource_count_is("AWS::OpenSearchServerless::CollectionGroup", 1)


def test_creates_collection(synth):
    template = synth(OpenSearchStack)
    template.resource_count_is("AWS::OpenSearchServerless::Collection", 1)


def test_creates_security_policies(synth):
    template = synth(OpenSearchStack)
    # One encryption policy + one network policy.
    template.resource_count_is("AWS::OpenSearchServerless::SecurityPolicy", 2)


def test_creates_data_access_policy(synth):
    template = synth(OpenSearchStack)
    template.resource_count_is("AWS::OpenSearchServerless::AccessPolicy", 1)


def test_collection_group_is_nextgen_scale_to_zero(synth):
    template = synth(OpenSearchStack)
    template.has_resource_properties(
        "AWS::OpenSearchServerless::CollectionGroup",
        {
            "Generation": "NEXTGEN",
            "StandbyReplicas": "DISABLED",
            "CapacityLimits": {
                "MinIndexingCapacityInOcu": 0,
                "MaxIndexingCapacityInOcu": 10,
                "MinSearchCapacityInOcu": 0,
                "MaxSearchCapacityInOcu": 10,
            },
        },
    )


def test_collection_is_vectorsearch_in_group(synth):
    template = synth(OpenSearchStack)
    template.has_resource_properties(
        "AWS::OpenSearchServerless::Collection",
        {
            "Type": "VECTORSEARCH",
            "StandbyReplicas": "DISABLED",
            "CollectionGroupName": "dia-aoss-group-dev",
        },
    )


def test_encryption_policy_type(synth):
    template = synth(OpenSearchStack)
    template.has_resource_properties(
        "AWS::OpenSearchServerless::SecurityPolicy",
        {"Type": "encryption"},
    )


def test_network_policy_type(synth):
    template = synth(OpenSearchStack)
    template.has_resource_properties(
        "AWS::OpenSearchServerless::SecurityPolicy",
        {"Type": "network"},
    )


def test_outputs_collection_endpoint(synth):
    template = synth(OpenSearchStack)
    outputs = template.find_outputs("*")
    assert any("AossCollectionEndpoint" in key for key in outputs)
