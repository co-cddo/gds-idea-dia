"""Schema for the knowledge base table in `knowledge_bases.py`, and its conversion to specs.

`KnowledgeBaseEntry` and `Source` are what is written in the table. The
functions here turn entries into the `KnowledgeBaseSpec`s the CDK stack builds,
working out bucket names and which sources are cross-account.

Usage:
    from knowledge_bases import KNOWLEDGE_BASES

    config = AppConfig(environment=DeploymentEnvironment.DEVELOPMENT)
    for spec in deployed_knowledge_bases(config, KNOWLEDGE_BASES):
        ...
"""

from __future__ import annotations

from collections.abc import Mapping

from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import BaseModel, Field, model_validator

from config import AppConfig
from dia.document_types import DocumentType
from dia.naming import Bucket
from stacks.constructs.knowledge_base import DataSourceSpec, KnowledgeBaseSpec

# Keys every document may carry in its .metadata.json sidecar.
COMMON_METADATA_KEYS: tuple[str, ...] = ("department_name", "alb", "document_type", "report_type", "year")


class Source(BaseModel, frozen=True):
    """An S3 location a knowledge base ingests.

    Attributes:
        key: Stable identifier (snake_case) the data source is named by. Leave
            out when the knowledge base has one source: it then uses the
            knowledge base's key. Required when there are several.
        bucket: Literal name of a bucket owned by another project, or a `Bucket`
            member for a bucket this repo creates.
        owner: Environment whose account owns a literal bucket. Leave out for a
            `Bucket` member (it is always in the account being deployed to).
        prefix: Only ingest objects under this prefix. Empty means the whole bucket.
        parsing_model: Inference profile ID to parse documents with a foundation
            model (for pptx or image-heavy PDFs). `None` uses the default parser.
    """

    key: str | None = None
    bucket: str | Bucket
    owner: DeploymentEnvironment | None = None
    prefix: str = ""
    parsing_model: str | None = None

    @model_validator(mode="after")
    def _owner_matches_bucket(self) -> Source:
        if isinstance(self.bucket, Bucket) and self.owner is not None:
            raise ValueError(f"{self.bucket!r} is created by this repo: leave out owner")
        if not isinstance(self.bucket, Bucket) and self.owner is None:
            raise ValueError(f"{self.bucket!r} is a literal bucket name: say which environment owns it with owner=")
        return self


class KnowledgeBaseEntry(BaseModel, frozen=True):
    """One knowledge base.

    Attributes:
        description: Stored on the knowledge base.
        document_type: The `document_type` value written to its metadata sidecars.
        data_sources: Where it reads from. At least one.
        extra_metadata_keys: Metadata keys beyond `COMMON_METADATA_KEYS`.
        deployed: Whether the stack creates it. Entries with `False` are declared only.
    """

    description: str
    document_type: DocumentType
    data_sources: list[Source] = Field(min_length=1)
    extra_metadata_keys: tuple[str, ...] = ()
    deployed: bool = False

    @model_validator(mode="after")
    def _several_sources_have_keys(self) -> KnowledgeBaseEntry:
        if len(self.data_sources) > 1 and any(source.key is None for source in self.data_sources):
            raise ValueError("every source needs a key when a knowledge base has more than one")
        return self


def knowledge_bases(config: AppConfig, entries: Mapping[str, KnowledgeBaseEntry]) -> list[KnowledgeBaseSpec]:
    """Specs for every entry, deployed or not.

    Args:
        config: The deployment's configuration, used for bucket names and to
            decide which sources are cross-account.
        entries: The table, keyed by knowledge base key.

    Returns:
        One spec per entry.
    """
    return [_to_spec(config, key, entry) for key, entry in entries.items()]


def deployed_knowledge_bases(config: AppConfig, entries: Mapping[str, KnowledgeBaseEntry]) -> list[KnowledgeBaseSpec]:
    """Specs for the entries with `deployed=True`, for the given environment."""
    return [_to_spec(config, key, entry) for key, entry in entries.items() if entry.deployed]


def _to_spec(config: AppConfig, key: str, entry: KnowledgeBaseEntry) -> KnowledgeBaseSpec:
    return KnowledgeBaseSpec(
        key=key,
        description=entry.description,
        data_sources=[_to_data_source(config, source, default_key=key) for source in entry.data_sources],
        metadata_keys=(*COMMON_METADATA_KEYS, *entry.extra_metadata_keys),
    )


def _to_data_source(config: AppConfig, source: Source, *, default_key: str) -> DataSourceSpec:
    if isinstance(source.bucket, Bucket):
        bucket_name, owner_account = config.names(source.bucket), None
    else:
        bucket_name = source.bucket
        owner_account = None if source.owner == config.environment else source.owner.value
    return DataSourceSpec(
        key=source.key or default_key,
        bucket_name=bucket_name,
        prefix=source.prefix,
        bucket_owner_account=owner_account,
        parsing_model=source.parsing_model,
    )
