"""How a source declares where its documents are, and which pipelines use it.

Every dataset is declared once, in `dia.sources.definitions`, whichever pipeline
consumes it: the graph pipeline (our extraction) or a Bedrock knowledge base.
The CDK, preflight and the pipeline all read the same declarations. This module
has no CDK imports, so the task image can use it.

A source's documents are in one of two kinds of bucket:

- **One of ours**, given as a `Bucket` member. It exists in both phases, named by
  `Names`, and we can write to it.
- **Someone else's**, given as an `ExternalBucket` with every name written out.
  Dev either reads its own copy of the bucket, or reads the prod bucket through the
  cross-account role. Names are never derived or guessed.

`resolve` turns a location into the bucket to read for one environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import BaseModel, Field, model_validator

from dia.document_types import DocumentType
from dia.naming import Bucket, Names

# Metadata keys every document may carry in its sidecar. A source adds its own on top.
COMMON_METADATA_KEYS: tuple[str, ...] = ("department_name", "alb", "document_type", "report_type", "year")


class ExternalBucket(BaseModel, frozen=True):
    """A bucket that another team owns, and the names to read it by in each phase.

    Attributes:
        prod: The bucket in the production account. Read directly in prod.
        dev: A separate bucket for dev to read directly, with dev's own credentials.
        dev_via_cross_account: Dev reads `prod` through the cross-account role instead.
            Exactly one of `dev` and this must be given.
    """

    prod: str = Field(min_length=3)
    dev: str | None = Field(default=None, min_length=3)
    dev_via_cross_account: bool = False

    @model_validator(mode="after")
    def _dev_is_one_or_the_other(self) -> ExternalBucket:
        if (self.dev is None) == (not self.dev_via_cross_account):
            raise ValueError("give exactly one of dev=<bucket> or dev_via_cross_account=True")
        return self


class Location(BaseModel, frozen=True):
    """Where a source's documents are.

    Attributes:
        bucket: One of our buckets, or an external bucket.
        prefix: Only documents under this prefix. Empty means the whole bucket.
    """

    bucket: Bucket | ExternalBucket
    prefix: str = ""


@dataclass(frozen=True)
class ResolvedLocation:
    """The bucket to read for one environment.

    Attributes:
        bucket: Bucket name.
        prefix: Key prefix within the bucket.
        cross_account: Whether the bucket is in the production account and is read from
            dev through the cross-account role.
        ours: Whether the bucket is one of ours, so we may write to it.
    """

    bucket: str
    prefix: str
    cross_account: bool
    ours: bool


def resolve(location: Location, environment: DeploymentEnvironment) -> ResolvedLocation:
    """The bucket a source's documents are read from in an environment.

    Args:
        location: The source's declared location.
        environment: The environment doing the reading.

    Returns:
        The bucket name, prefix, and how it has to be read.
    """
    bucket = location.bucket
    if isinstance(bucket, Bucket):
        return ResolvedLocation(Names(environment)(bucket), location.prefix, cross_account=False, ours=True)

    if environment == DeploymentEnvironment.PRODUCTION:
        return ResolvedLocation(bucket.prod, location.prefix, cross_account=False, ours=False)
    if bucket.dev_via_cross_account:
        return ResolvedLocation(bucket.prod, location.prefix, cross_account=True, ours=False)
    return ResolvedLocation(bucket.dev, location.prefix, cross_account=False, ours=False)


class KnowledgeBaseSettings(BaseModel, frozen=True):
    """Settings for a source that has a Bedrock knowledge base.

    Attributes:
        parsing_model: Inference profile ID to parse documents with a foundation model
            (for pptx or image-heavy PDFs). `None` uses the default parser.
        deployed: Whether the knowledge base stack creates it. Sources with `False`
            are declared only.
    """

    parsing_model: str | None = None
    deployed: bool = False


class SourceDefinition(BaseModel, frozen=True):
    """One dataset, and the pipelines that use it.

    Attributes:
        description: What the dataset holds.
        document_type: The `document_type` metadata value for its documents.
        location: Where its documents are.
        extra_metadata_keys: Metadata keys beyond `COMMON_METADATA_KEYS`.
        graph: Whether it goes through our extraction into the graph.
        knowledge_base: Settings if it has a Bedrock knowledge base, else `None`.
    """

    description: str = Field(min_length=1)
    document_type: DocumentType
    location: Location
    extra_metadata_keys: tuple[str, ...] = ()
    graph: bool = False
    knowledge_base: KnowledgeBaseSettings | None = None

    @model_validator(mode="after")
    def _used_by_a_pipeline(self) -> SourceDefinition:
        if not self.graph and self.knowledge_base is None:
            raise ValueError("a source must feed the graph, a knowledge base, or both")
        return self

    @property
    def metadata_keys(self) -> tuple[str, ...]:
        """Every metadata key a document of this source may carry."""
        return (*COMMON_METADATA_KEYS, *self.extra_metadata_keys)
