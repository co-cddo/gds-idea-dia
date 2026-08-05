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
            "StandbyReplicas": "ENABLED",
            "CapacityLimits": {
                "MinIndexingCapacityInOcu": 0,
                "MaxIndexingCapacityInOcu": 8,
                "MinSearchCapacityInOcu": 0,
                "MaxSearchCapacityInOcu": 8,
            },
        },
    )


def test_collection_is_vectorsearch_in_group(synth):
    template = synth(OpenSearchStack)
    template.has_resource_properties(
        "AWS::OpenSearchServerless::Collection",
        {
            "Type": "VECTORSEARCH",
            "StandbyReplicas": "ENABLED",
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


def test_nextgen_group_requires_standby_replicas_enabled(synth):
    """AWS rejects StandbyReplicas=DISABLED for NEXTGEN collection groups.

    Guards against reintroducing DISABLED, which fails at deploy time with
    CREATE_FAILED. Applies to both the group and any collection in it.
    """
    template = synth(OpenSearchStack)
    groups = template.find_resources(
        "AWS::OpenSearchServerless::CollectionGroup",
        {"Properties": {"Generation": "NEXTGEN"}},
    )
    assert groups, "expected a NEXTGEN collection group"
    for resource in groups.values():
        assert resource["Properties"]["StandbyReplicas"] == "ENABLED"

    collections = template.find_resources("AWS::OpenSearchServerless::Collection")
    for resource in collections.values():
        assert resource["Properties"]["StandbyReplicas"] == "ENABLED"


def test_capacity_limits_use_valid_ocu_values(synth):
    """AWS only allows OCU values of 0, 2, 4, 8, 16, or any multiple of 16.

    Guards against illegal capacities (e.g. 10) that fail at deploy time.
    """
    valid = {0, 2, 4, 8, 16}

    def is_valid_ocu(value: float) -> bool:
        return value in valid or (value >= 16 and value % 16 == 0)

    template = synth(OpenSearchStack)
    groups = template.find_resources("AWS::OpenSearchServerless::CollectionGroup")
    assert groups, "expected a collection group"
    for resource in groups.values():
        limits = resource["Properties"]["CapacityLimits"]
        for key in (
            "MinIndexingCapacityInOcu",
            "MaxIndexingCapacityInOcu",
            "MinSearchCapacityInOcu",
            "MaxSearchCapacityInOcu",
        ):
            assert is_valid_ocu(limits[key]), f"{key}={limits[key]} is not a valid OCU value"
