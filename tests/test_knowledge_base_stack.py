"""Tests for KnowledgeBaseStack, built from the deployed declarations."""

import json
import re

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from gds_idea_cdk_constructs import DeploymentEnvironment, IdeaTags

from config import AppConfig
from knowledge_bases import deployed_knowledge_bases
from stacks.knowledge_base import KnowledgeBaseStack, knowledge_base_name

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
        specs=deployed_knowledge_bases(config),
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
