"""Tests for the reusable KnowledgeBase construct, independent of dia config."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from aws_cdk import aws_s3vectors as s3vectors
from pydantic import ValidationError

from stacks.constructs.knowledge_base import (
    TITAN_EMBED_TEXT_V2,
    DataSourceSpec,
    EmbeddingModel,
    FixedSizeChunking,
    KnowledgeBase,
    KnowledgeBaseSpec,
    NoChunking,
)

ACCOUNT = "111111111111"
OTHER_ACCOUNT = "222222222222"
REGION = "eu-west-2"
PARSER = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _spec(**overrides) -> KnowledgeBaseSpec:
    fields = {
        "key": "reports",
        "description": "Test reports",
        "data_sources": [DataSourceSpec(bucket_name="source-bucket", prefix="files/")],
    }
    return KnowledgeBaseSpec(**{**fields, **overrides})


def _synth(spec: KnowledgeBaseSpec, name: str = "app-kb-reports-dev") -> assertions.Template:
    app = cdk.App()
    stack = cdk.Stack(app, "TestStack", env=cdk.Environment(account=ACCOUNT, region=REGION))
    bucket = s3vectors.CfnVectorBucket(stack, "VectorBucket", vector_bucket_name="app-vectors")
    KnowledgeBase(stack, "Kb", spec=spec, name=name, vector_bucket=bucket)
    return assertions.Template.from_stack(stack)


def _policy_statements(template: assertions.Template) -> dict[str, dict]:
    policies = template.find_resources("AWS::IAM::Policy")
    statements = [s for p in policies.values() for s in p["Properties"]["PolicyDocument"]["Statement"]]
    return {s["Sid"]: s for s in statements}


# --- resources ---


def test_creates_one_kb_index_role_and_data_source_per_source():
    template = _synth(
        _spec(data_sources=[DataSourceSpec(bucket_name="bucket-a"), DataSourceSpec(bucket_name="bucket-b")])
    )
    template.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)
    template.resource_count_is("AWS::S3Vectors::Index", 1)
    template.resource_count_is("AWS::IAM::Role", 1)
    template.resource_count_is("AWS::Bedrock::DataSource", 2)


def test_names_derive_from_supplied_name():
    template = _synth(_spec())
    template.has_resource_properties("AWS::Bedrock::KnowledgeBase", {"Name": "app-kb-reports-dev"})
    template.has_resource_properties("AWS::S3Vectors::Index", {"IndexName": "app-kb-reports-dev-index"})
    template.has_resource_properties("AWS::Bedrock::DataSource", {"Name": "app-kb-reports-dev-ds-0"})


def test_knowledge_base_uses_s3_vectors_and_embedding_model():
    template = _synth(_spec())
    template.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {
            "KnowledgeBaseConfiguration": {
                "Type": "VECTOR",
                "VectorKnowledgeBaseConfiguration": {
                    "EmbeddingModelArn": f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
                },
            },
            "StorageConfiguration": {"Type": "S3_VECTORS"},
        },
    )


def test_index_dimension_follows_embedding_model():
    template = _synth(_spec(embedding_model=EmbeddingModel(model_id="cohere.embed-v4:0", dimension=1536)))
    template.has_resource_properties("AWS::S3Vectors::Index", {"Dimension": 1536, "DistanceMetric": "cosine"})


def test_only_bedrock_internal_keys_are_non_filterable():
    template = _synth(_spec(metadata_keys=("department", "year")))
    template.has_resource_properties(
        "AWS::S3Vectors::Index",
        {
            "MetadataConfiguration": {
                "NonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"],
            }
        },
    )


def test_knowledge_base_waits_for_role_policy():
    template = _synth(_spec())
    kb = next(iter(template.find_resources("AWS::Bedrock::KnowledgeBase").values()))
    policy_id = next(iter(template.find_resources("AWS::IAM::Policy")))
    assert policy_id in kb["DependsOn"]


# --- data sources ---


def test_same_account_data_source_has_prefix_and_no_owner_account():
    template = _synth(_spec())
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "DataSourceConfiguration": {
                "Type": "S3",
                "S3Configuration": {
                    "BucketArn": "arn:aws:s3:::source-bucket",
                    "InclusionPrefixes": ["files/"],
                    "BucketOwnerAccountId": assertions.Match.absent(),
                },
            }
        },
    )


def test_cross_account_data_source_sets_bucket_owner():
    template = _synth(
        _spec(data_sources=[DataSourceSpec(bucket_name="their-bucket", bucket_owner_account=OTHER_ACCOUNT)])
    )
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "DataSourceConfiguration": {
                "S3Configuration": {
                    "BucketOwnerAccountId": OTHER_ACCOUNT,
                    "InclusionPrefixes": assertions.Match.absent(),
                }
            }
        },
    )


def test_semantic_chunking_is_default():
    template = _synth(_spec())
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "VectorIngestionConfiguration": {
                "ChunkingConfiguration": {
                    "ChunkingStrategy": "SEMANTIC",
                    "SemanticChunkingConfiguration": {
                        "MaxTokens": 512,
                        "BufferSize": 1,
                        "BreakpointPercentileThreshold": 91,
                    },
                }
            }
        },
    )


def test_fixed_size_chunking():
    template = _synth(_spec(chunking=FixedSizeChunking(max_tokens=200, overlap_percentage=10)))
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "VectorIngestionConfiguration": {
                "ChunkingConfiguration": {
                    "ChunkingStrategy": "FIXED_SIZE",
                    "FixedSizeChunkingConfiguration": {"MaxTokens": 200, "OverlapPercentage": 10},
                }
            }
        },
    )


def test_no_chunking():
    template = _synth(_spec(chunking=NoChunking()))
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {"VectorIngestionConfiguration": {"ChunkingConfiguration": {"ChunkingStrategy": "NONE"}}},
    )


def test_parsing_config_only_when_parsing_model_set():
    template = _synth(
        _spec(
            data_sources=[
                DataSourceSpec(bucket_name="plain-bucket"),
                DataSourceSpec(bucket_name="parsed-bucket", parsing_model=PARSER),
            ]
        )
    )
    sources = {
        r["Properties"]["DataSourceConfiguration"]["S3Configuration"]["BucketArn"]: r["Properties"]
        for r in template.find_resources("AWS::Bedrock::DataSource").values()
    }
    assert "ParsingConfiguration" not in sources["arn:aws:s3:::plain-bucket"]["VectorIngestionConfiguration"]
    assert sources["arn:aws:s3:::parsed-bucket"]["VectorIngestionConfiguration"]["ParsingConfiguration"] == {
        "ParsingStrategy": "BEDROCK_FOUNDATION_MODEL",
        "BedrockFoundationModelConfiguration": {
            "ModelArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/{PARSER}",
        },
    }


# --- IAM ---


def test_role_trusts_bedrock_scoped_to_account_knowledge_bases():
    template = _synth(_spec())
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Principal": {"Service": "bedrock.amazonaws.com"},
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": ACCOUNT},
                            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:knowledge-base/*"},
                        },
                    }
                ]
            }
        },
    )


def test_source_read_is_scoped_to_prefix_and_owner_account():
    statements = _policy_statements(_synth(_spec()))
    owner = {"StringEquals": {"aws:ResourceAccount": ACCOUNT}}
    assert statements["ListSourceBucket0"]["Action"] == "s3:ListBucket"
    assert statements["ListSourceBucket0"]["Resource"] == "arn:aws:s3:::source-bucket"
    assert statements["ListSourceBucket0"]["Condition"] == owner
    assert statements["GetSourceObjects0"]["Action"] == "s3:GetObject"
    assert statements["GetSourceObjects0"]["Resource"] == "arn:aws:s3:::source-bucket/files/*"
    assert statements["GetSourceObjects0"]["Condition"] == owner


def test_cross_account_source_read_pins_owner_account():
    statements = _policy_statements(
        _synth(_spec(data_sources=[DataSourceSpec(bucket_name="their-bucket", bucket_owner_account=OTHER_ACCOUNT)]))
    )
    owner = {"StringEquals": {"aws:ResourceAccount": OTHER_ACCOUNT}}
    assert statements["ListSourceBucket0"]["Condition"] == owner
    assert statements["GetSourceObjects0"]["Resource"] == "arn:aws:s3:::their-bucket/*"
    assert statements["GetSourceObjects0"]["Condition"] == owner


def test_vector_access_is_scoped_to_own_index():
    template = _synth(_spec())
    index_id = next(iter(template.find_resources("AWS::S3Vectors::Index")))
    statement = _policy_statements(template)["VectorIndexReadWrite"]
    assert sorted(statement["Action"]) == [
        "s3vectors:DeleteVectors",
        "s3vectors:GetIndex",
        "s3vectors:GetVectors",
        "s3vectors:PutVectors",
        "s3vectors:QueryVectors",
    ]
    assert statement["Resource"] == {"Fn::GetAtt": [index_id, "IndexArn"]}


def test_embedding_invoke_is_scoped_to_model():
    statement = _policy_statements(_synth(_spec()))["InvokeEmbeddingModel"]
    assert statement["Action"] == "bedrock:InvokeModel"
    assert statement["Resource"] == f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"


def test_parsing_model_grants_profile_and_foundation_model_once_per_profile():
    statements = _policy_statements(
        _synth(
            _spec(
                data_sources=[
                    DataSourceSpec(bucket_name="bucket-a", parsing_model=PARSER),
                    DataSourceSpec(bucket_name="bucket-b", parsing_model=PARSER),
                ]
            )
        )
    )
    assert statements["InvokeParsingProfile0"]["Resource"] == (
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/{PARSER}"
    )
    assert statements["InvokeParsingFoundationModel0"]["Resource"] == (
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    assert "InvokeParsingProfile1" not in statements


def test_no_parsing_grants_without_parsing_model():
    statements = _policy_statements(_synth(_spec()))
    assert not any(sid.startswith("InvokeParsing") for sid in statements)


def test_no_assume_role_or_wildcard_resources():
    statements = _policy_statements(
        _synth(_spec(data_sources=[DataSourceSpec(bucket_name="their-bucket", bucket_owner_account=OTHER_ACCOUNT)]))
    )
    for statement in statements.values():
        actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        assert "sts:AssumeRole" not in actions
        assert statement["Resource"] != "*"


# --- spec validation ---


def test_titan_v2_is_default_embedding_model():
    assert _spec().embedding_model == TITAN_EMBED_TEXT_V2


@pytest.mark.parametrize(
    "overrides",
    [
        {"key": "Not-Snake"},
        {"description": ""},
        {"data_sources": []},
        {"metadata_keys": ("department", "department")},
        {"metadata_keys": ("AMAZON_BEDROCK_TEXT",)},
        {"metadata_keys": ("x-amz-bedrock-kb-source-uri",)},
        {"metadata_keys": tuple(f"k{i}" for i in range(36))},
        {"chunking": {"strategy": "SEMANTIC", "buffer_size": 2}},
    ],
)
def test_invalid_spec_rejected(overrides):
    with pytest.raises(ValidationError):
        _spec(**overrides)


@pytest.mark.parametrize(
    "fields",
    [
        {"bucket_name": "Bad_Bucket"},
        {"bucket_name": "ok-bucket", "bucket_owner_account": "123"},
        {"bucket_name": "ok-bucket", "parsing_model": "anthropic.claude-haiku-4-5-20251001-v1:0"},
    ],
)
def test_invalid_data_source_rejected(fields):
    with pytest.raises(ValidationError):
        DataSourceSpec(**fields)


@pytest.mark.parametrize("name", ["Upper-Case", "double--hyphen", "under_score", "x" * 58])
def test_invalid_name_rejected(name):
    with pytest.raises(ValueError):
        _synth(_spec(), name=name)
