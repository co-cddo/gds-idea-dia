"""Names for deployed resources, derived from one place.

Both the CDK app and the runtime code build names through `Names`, so a bucket,
table or stack is called the same thing everywhere. A `Names` is created from a
`DeploymentEnvironment`, which supplies the phase (dev or prod).

    names = Names(DeploymentEnvironment.DEVELOPMENT)
    names("ledger")                 # "dia-ledger-dev"
    names(Bucket.TEXT_EXTRACTED)    # "gds-idea-dia-text-extracted-dev"

In CDK code, build it from the CDK environment (no AWS call is made):

    names = Names(DeploymentEnvironment.from_cdk_env(cdk_env))

At runtime, `dia.cli_helpers.current_names()` works out the environment from
the AWS account of the active credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gds_idea_cdk_constructs import DeploymentEnvironment

TEAM = "gds-idea"
PROJECT = "dia"
REGION = "eu-west-2"


class Bucket(StrEnum):
    """The S3 buckets this project creates."""

    TEXT_EXTRACTED = "text-extracted"
    GRAPH_RAW = "graph-raw"
    GRAPH_VALIDATED = "graph-validated"
    BATCH = "batch"
    AGENT_REPORTS = "agent-reports"
    DBR_REPORTS = "dbr-reports"
    SR25_BIDS = "sr25-bids"
    SR21_BIDS = "sr21-bids"
    NAO_REPORTS = "nao-reports"
    REPORTS = "reports"


_BUCKET_VALUES = frozenset(bucket.value for bucket in Bucket)


@dataclass(frozen=True)
class Names:
    """Builds resource names for one deployment environment."""

    environment: DeploymentEnvironment

    @property
    def phase(self) -> str:
        """Short phase name, for example "dev" or "prod"."""
        return self.environment.short_name

    def __call__(self, name: str) -> str:
        """Name of a resource, stack or bucket.

        A `Bucket` gives `{team}-{project}-{bucket}-{phase}`. Any other name
        gives `{project}-{name}-{phase}`.

        Raises:
            ValueError: If `name` is a plain string that matches a bucket.
                Buckets must be named with the `Bucket` enum, so a bucket can
                never silently get the resource pattern.
        """
        if isinstance(name, Bucket):
            return f"{TEAM}-{PROJECT}-{name.value}-{self.phase}"
        if name in _BUCKET_VALUES:
            raise ValueError(f"{name!r} is a bucket: use Bucket.{Bucket(name).name}")
        return f"{PROJECT}-{name}-{self.phase}"
