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
    template.resource_count_is("AWS::S3::Bucket", 3)


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
        (DeploymentEnvironment.DEVELOPMENT, "dev", "graph-raw"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "graph-validated"),
        (DeploymentEnvironment.DEVELOPMENT, "dev", "batch"),
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


@pytest.mark.parametrize("purpose", ["graph-raw", "graph-validated"])
def test_data_buckets_are_versioned(synth, purpose):
    template = synth(StorageStack)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketName": f"gds-idea-dia-{purpose}-dev",
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
