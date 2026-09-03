import pytest
from aws_cdk import assertions
from gds_idea_cdk_constructs import DeploymentEnvironment

from stacks.storage import StorageStack


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_creates_three_buckets(synth, environment, phase):
    template = synth(StorageStack, environment)
    template.resource_count_is("AWS::S3::Bucket", 4)


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_creates_one_dynamodb_table(synth, environment, phase):
    template = synth(StorageStack, environment)
    template.resource_count_is("AWS::DynamoDB::Table", 1)


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_bucket_names_follow_pattern(synth, environment, phase):
    template = synth(StorageStack, environment)
    resources = template.find_resources("AWS::S3::Bucket")
    for resource in resources.values():
        name = resource["Properties"]["BucketName"]
        assert name.startswith("gds-idea-dia-")
        assert name.endswith(f"-{phase}")


@pytest.mark.parametrize(
    "environment,phase,purpose",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev", "text-extracted"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "graph-raw"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "graph-validated"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "batch"),
        (DeploymentEnvironment.PRODUCTION, "prod", "text-extracted"),
        (DeploymentEnvironment.PRODUCTION, "prod", "graph-raw"),
        (DeploymentEnvironment.PRODUCTION, "prod", "graph-validated"),
        (DeploymentEnvironment.PRODUCTION, "prod", "batch"),
    ],
)
def test_expected_bucket_exists(synth, environment, phase, purpose):
    template = synth(StorageStack, environment)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {"BucketName": f"gds-idea-dia-{purpose}-{phase}"},
    )


def test_batch_bucket_has_lifecycle_rule(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketName": "gds-idea-dia-batch-dev",
            "LifecycleConfiguration": assertions.Match.any_value(),
        },
    )


@pytest.mark.parametrize("purpose", ["text-extracted", "graph-raw", "graph-validated"])
def test_data_buckets_are_versioned(synth, purpose):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketName": f"gds-idea-dia-{purpose}-dev",
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )


# --- Ledger table ---


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_ledger_table_name_follows_pattern(synth, environment, phase):
    template = synth(StorageStack, environment)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"TableName": f"dia-ledger-{phase}"},
    )


def test_ledger_table_has_pay_per_request(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"BillingMode": "PAY_PER_REQUEST"},
    )


def test_ledger_table_has_point_in_time_recovery(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True}},
    )


def test_ledger_table_partition_key(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "KeySchema": [{"AttributeName": "document_key", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "document_key", "AttributeType": "S"}],
        },
    )


# --- Batch inference role ---


@pytest.mark.parametrize(
    "environment,phase",
    [
        (DeploymentEnvironment.DEVELOPMENT, "dev"),
        (DeploymentEnvironment.PRODUCTION, "prod"),
    ],
)
def test_batch_inference_role_name_follows_pattern(synth, environment, phase):
    template = synth(StorageStack, environment)
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"RoleName": f"dia-batch-inference-{phase}"},
    )


def test_batch_inference_role_trust_policy(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "bedrock.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Condition": {"StringEquals": {"aws:SourceAccount": "992382722318"}},
                    }
                ],
            }
        },
    )


def test_batch_inference_role_has_permissions_boundary(synth):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"PermissionsBoundary": "arn:aws:iam::992382722318:policy/DenyUserPermissionsPolicy"},
    )


def test_batch_inference_role_grants_access_to_batch_bucket_only(synth):
    template = synth(StorageStack)

    buckets = template.find_resources("AWS::S3::Bucket")
    (batch_bucket_id,) = [
        logical_id
        for logical_id, resource in buckets.items()
        if resource["Properties"]["BucketName"] == "gds-idea-dia-batch-dev"
    ]

    policies = template.find_resources("AWS::IAM::Policy")
    (policy,) = [
        p for p in policies.values() if p["Properties"]["PolicyName"].startswith("BatchInferenceRoleDefaultPolicy")
    ]
    (statement,) = policy["Properties"]["PolicyDocument"]["Statement"]
    resources = statement["Resource"]

    assert statement["Effect"] == "Allow"
    assert resources[0] == {"Fn::GetAtt": [batch_bucket_id, "Arn"]}
    assert resources[1] == {"Fn::Join": ["", [{"Fn::GetAtt": [batch_bucket_id, "Arn"]}, "/*"]]}


def test_outputs_batch_inference_role_arn(synth):
    template = synth(StorageStack)
    outputs = template.find_outputs("*")
    assert any("BatchInferenceRoleArn" in key for key in outputs)
