"""Tests for KnowledgeBaseStack and the specs built from the declared sources."""

import json
import re

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from gds_idea_cdk_constructs import DeploymentEnvironment, IdeaTags

from config import AppConfig
from dia.sources.definitions import SOURCES
from stacks.knowledge_base import KnowledgeBaseStack, knowledge_base_name, knowledge_base_specs

DEV = DeploymentEnvironment.DEVELOPMENT
PROD = DeploymentEnvironment.PRODUCTION
ENVIRONMENTS = [DEV, PROD]


def _template(environment: DeploymentEnvironment, *, tagged: bool = False) -> assertions.Template:
    config = AppConfig(environment=environment)
    app = cdk.App()
    stack = KnowledgeBaseStack(
        app,
        "KnowledgeBases",
        config=config,
        specs=knowledge_base_specs(config, SOURCES),
        env=cdk.Environment(account=config.account_number, region=config.region),
    )
    if tagged:
        IdeaTags(environment=environment, app_name="dia", repository="gds-idea-dia").apply(app)
    return assertions.Template.from_stack(stack)


@pytest.fixture(scope="module")
def dev():
    return _template(DEV)


@pytest.fixture(scope="module")
def prod():
    return _template(PROD)


def test_deploys_only_the_dbr_knowledge_bases(dev):
    dev.resource_count_is("AWS::Bedrock::KnowledgeBase", 2)
    dev.resource_count_is("AWS::Bedrock::DataSource", 2)
    dev.resource_count_is("AWS::S3Vectors::Index", 2)
    dev.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    names = {r["Properties"]["Name"] for r in dev.find_resources("AWS::Bedrock::KnowledgeBase").values()}
    assert names == {"dia-kb-dbr-readouts-letter-dev", "dia-kb-dbr-reports-dev"}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_names_include_the_phase(environment):
    template = _template(environment)
    phase = environment.short_name
    template.has_resource_properties("AWS::S3Vectors::VectorBucket", {"VectorBucketName": f"dia-kb-vectors-{phase}"})
    template.has_resource_properties("AWS::Bedrock::KnowledgeBase", {"Name": f"dia-kb-dbr-reports-{phase}"})


def test_knowledge_base_name_turns_the_key_into_a_resource_name():
    assert knowledge_base_name(AppConfig(environment=DEV), "dbr_readouts_letter") == "dia-kb-dbr-readouts-letter-dev"


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_dbr_data_sources_read_their_prefix_of_this_environments_bucket(environment):
    template = _template(environment)
    bucket_arn = f"arn:aws:s3:::gds-idea-dia-dbr-reports-{environment.short_name}"
    sources = [r["Properties"] for r in template.find_resources("AWS::Bedrock::DataSource").values()]
    configs = [s["DataSourceConfiguration"]["S3Configuration"] for s in sources]
    assert {c["BucketArn"] for c in configs} == {bucket_arn}
    assert sorted(c["InclusionPrefixes"][0] for c in configs) == ["readouts/", "reports/"]
    assert not any("BucketOwnerAccountId" in c for c in configs)


@pytest.mark.parametrize("resource_type", ["AWS::S3Vectors::VectorBucket", "AWS::S3Vectors::Index"])
def test_vector_storage_is_retained(prod, resource_type):
    for resource in prod.find_resources(resource_type).values():
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_every_role_has_the_permissions_boundary(dev):
    roles = dev.find_resources("AWS::IAM::Role")
    assert len(roles) == 2
    for role in roles.values():
        assert role["Properties"]["PermissionsBoundary"] == (
            f"arn:aws:iam::{DEV.value}:policy/DenyUserPermissionsPolicy"
        )


def test_each_role_reads_only_its_own_prefix(dev):
    policies = dev.find_resources("AWS::IAM::Policy").values()
    object_reads = sorted(
        s["Resource"]
        for p in policies
        for s in p["Properties"]["PolicyDocument"]["Statement"]
        if s["Action"] == "s3:GetObject"
    )
    assert object_reads == [
        "arn:aws:s3:::gds-idea-dia-dbr-reports-dev/readouts/*",
        "arn:aws:s3:::gds-idea-dia-dbr-reports-dev/reports/*",
    ]


def test_outputs_knowledge_base_ids_and_role_arns(dev):
    outputs = dev.find_outputs("*")
    for prefix in ("DbrReadoutsLetter", "DbrReports"):
        assert f"{prefix}KnowledgeBaseId" in outputs
        assert f"{prefix}RoleArn" in outputs


def test_stack_tags_classify_the_resources(dev):
    bucket = next(iter(dev.find_resources("AWS::S3Vectors::VectorBucket").values()))
    tags = {t["Key"]: t["Value"] for t in bucket["Properties"]["Tags"]}
    assert tags["ResourceType"] == "BedrockKnowledgeBase"
    assert tags["Service"] == "KnowledgeBases"


def test_app_tags_reach_the_knowledge_base_resources():
    template = _template(DEV, tagged=True)
    required = {"AppName", "Environment", "ManagedBy", "Repository"}
    for resource_type in ("AWS::S3Vectors::VectorBucket", "AWS::S3Vectors::Index"):
        for resource in template.find_resources(resource_type).values():
            assert required <= {t["Key"] for t in resource["Properties"]["Tags"]}, resource_type
    for resource in template.find_resources("AWS::Bedrock::KnowledgeBase").values():
        assert required <= set(resource["Properties"]["Tags"]), "AWS::Bedrock::KnowledgeBase"


def test_no_account_ids_other_than_the_deploying_account(dev):
    body = json.dumps(dev.to_json())
    accounts = set(re.findall(r"\b\d{12}\b", body))
    assert accounts <= {DEV.value}


# --- specs built from the declared sources ---

DEV_ACCOUNT_BUCKET_SOURCES = {"sr25_bids", "sr21_bids", "nao_reports", "efficiency_reports", "other_reports"}


def _specs_by_key(environment: DeploymentEnvironment) -> dict:
    specs = knowledge_base_specs(AppConfig(environment=environment), SOURCES, deployed_only=False)
    return {spec.key: spec for spec in specs}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_deployed_specs_are_the_two_dbr_knowledge_bases(environment):
    specs = knowledge_base_specs(AppConfig(environment=environment), SOURCES)
    assert [spec.key for spec in specs] == ["dbr_readouts_letter", "dbr_reports"]


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_source_with_a_knowledge_base_gets_a_spec(environment):
    expected = {key for key, source in SOURCES.items() if source.knowledge_base is not None}
    assert set(_specs_by_key(environment)) == expected


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_each_spec_has_one_data_source_keyed_like_the_knowledge_base(environment):
    for spec in _specs_by_key(environment).values():
        (data_source,) = spec.data_sources
        assert data_source.key == spec.key


def test_spec_metadata_keys_come_from_the_source():
    specs = _specs_by_key(DEV)
    assert specs["dbr_reports"].metadata_keys == SOURCES["dbr_reports"].metadata_keys
    assert "is_latest" in specs["dbr_reports"].metadata_keys


def test_gats_is_read_cross_account_from_dev_only():
    (dev_source,) = _specs_by_key(DEV)["gats_business_cases"].data_sources
    (prod_source,) = _specs_by_key(PROD)["gats_business_cases"].data_sources
    assert dev_source.bucket_owner_account == PROD.value
    assert prod_source.bucket_owner_account is None
    assert dev_source.bucket_name == prod_source.bucket_name


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize("key", sorted(DEV_ACCOUNT_BUCKET_SOURCES))
def test_our_own_buckets_are_never_cross_account(environment, key):
    (data_source,) = _specs_by_key(environment)[key].data_sources
    assert data_source.bucket_owner_account is None
    assert data_source.bucket_name.endswith(f"-{environment.short_name}")


@pytest.mark.parametrize("key", ["nao_reports", "efficiency_reports"])
def test_report_knowledge_bases_parse_with_a_foundation_model(key):
    (data_source,) = _specs_by_key(DEV)[key].data_sources
    assert data_source.parsing_model is not None
