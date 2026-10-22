"""Reusable Bedrock Knowledge Base construct backed by S3 Vectors.

A ``KnowledgeBase`` provisions everything a single knowledge base needs:

- an S3 Vectors index inside a caller-supplied vector bucket,
- a least-privilege Bedrock service role,
- the Bedrock knowledge base,
- one S3 data source per ``DataSourceSpec``.

The construct is application-agnostic: what to build is described by a
``KnowledgeBaseSpec``, and the physical name is supplied by the caller.

Usage:
    spec = KnowledgeBaseSpec(
        key="reports",
        description="Published reports",
        data_sources=[DataSourceSpec(key="files", bucket_name="my-reports", prefix="files/")],
        metadata_keys=("department", "year"),
    )
    kb = KnowledgeBase(self, "Reports", spec=spec, name="myapp-kb-reports-dev", vector_bucket=bucket)
    kb.knowledge_base_id
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

import aws_cdk as cdk
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct
from pydantic import BaseModel, Field, field_validator

# Bedrock stores chunk text and its own metadata under these keys. They exceed
# the S3 Vectors filterable-metadata size limit, so must be non-filterable.
BEDROCK_NON_FILTERABLE_KEYS: tuple[str, ...] = ("AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA")

# S3 Vectors limit for custom metadata keys per vector when used with Bedrock.
MAX_METADATA_KEYS = 35

# Geography prefixes of Bedrock cross-region inference profile IDs.
INFERENCE_PROFILE_GEOGRAPHIES = frozenset({"eu", "global"})

# Lowercase alphanumerics with single hyphens: valid for both S3 Vectors index
# names and Bedrock knowledge base / data source names.
_NAME_PATTERN = re.compile(r"^[a-z0-9](-?[a-z0-9])*$")
_INDEX_SUFFIX = "-index"
_DATA_SOURCE_INFIX = "-ds-"
# snake_case: lowercase alphanumerics separated by single underscores.
_KEY_PATTERN = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
# Keeps `{name}-ds-{key}` inside Bedrock's 100 character limit for names up to 57.
_MAX_DATA_SOURCE_KEY_LENGTH = 30
_MAX_INDEX_NAME_LENGTH = 63


class EmbeddingModel(BaseModel, frozen=True):
    """A Bedrock embedding model and the vector dimension it produces."""

    model_id: str = Field(min_length=1)
    dimension: int = Field(gt=0)


TITAN_EMBED_TEXT_V2 = EmbeddingModel(model_id="amazon.titan-embed-text-v2:0", dimension=1024)


class SemanticChunking(BaseModel, frozen=True):
    """Split on meaning, using embedding similarity between sentences."""

    strategy: Literal["SEMANTIC"] = "SEMANTIC"
    max_tokens: int = Field(default=512, gt=0)
    buffer_size: int = Field(default=1, ge=0, le=1)
    breakpoint_percentile_threshold: int = Field(default=91, ge=50, le=99)


class FixedSizeChunking(BaseModel, frozen=True):
    """Split into fixed-size token windows with overlap."""

    strategy: Literal["FIXED_SIZE"] = "FIXED_SIZE"
    max_tokens: int = Field(default=300, gt=0)
    overlap_percentage: int = Field(default=20, ge=1, le=99)


class NoChunking(BaseModel, frozen=True):
    """Treat each document as a single chunk."""

    strategy: Literal["NONE"] = "NONE"


Chunking = Annotated[SemanticChunking | FixedSizeChunking | NoChunking, Field(discriminator="strategy")]


class DataSourceSpec(BaseModel, frozen=True):
    """An S3 location ingested into a knowledge base.

    Attributes:
        key: Stable identifier (snake_case, unique within the knowledge base).
            The data source's name and construct ID come from it, not from its
            position, so reordering or removing other sources never renames it.
            Renaming a key replaces the data source, and the documents are
            ingested again.
        bucket_name: Source S3 bucket.
        prefix: Only ingest objects under this prefix. Empty means the whole bucket.
        bucket_owner_account: Account that owns the bucket, if not the deploying
            account. The bucket policy must then allow the knowledge base role.
        parsing_model: Cross-region inference profile ID (e.g.
            ``eu.anthropic.claude-haiku-4-5-20251001-v1:0``) to parse documents with
            a foundation model. ``None`` uses Bedrock's default text parser.
    """

    key: str = Field(pattern=_KEY_PATTERN, max_length=_MAX_DATA_SOURCE_KEY_LENGTH)
    bucket_name: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
    prefix: str = ""
    bucket_owner_account: str | None = Field(default=None, pattern=r"^\d{12}$")
    parsing_model: str | None = None

    @field_validator("parsing_model")
    @classmethod
    def _parsing_model_is_inference_profile(cls, value: str | None) -> str | None:
        if value is not None and value.split(".", 1)[0] not in INFERENCE_PROFILE_GEOGRAPHIES:
            raise ValueError(
                f"parsing_model must be a cross-region inference profile ID starting with one of "
                f"{sorted(INFERENCE_PROFILE_GEOGRAPHIES)}, got {value!r}"
            )
        return value


class KnowledgeBaseSpec(BaseModel, frozen=True):
    """Declarative description of one knowledge base.

    Attributes:
        key: Stable identifier (snake_case), used by callers for naming and lookups.
        description: Human-readable description stored on the knowledge base.
        data_sources: S3 locations to ingest. At least one is required. Their keys
            must be unique.
        embedding_model: Model used to embed chunks; sets the index dimension.
        chunking: How documents are split before embedding.
        metadata_keys: Custom metadata keys documents are expected to carry in
            their ``.metadata.json`` sidecars. All are filterable.
    """

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=200)
    data_sources: list[DataSourceSpec] = Field(min_length=1)
    embedding_model: EmbeddingModel = TITAN_EMBED_TEXT_V2
    chunking: Chunking = SemanticChunking()
    metadata_keys: tuple[str, ...] = ()

    @field_validator("data_sources")
    @classmethod
    def _data_source_keys_unique(cls, value: list[DataSourceSpec]) -> list[DataSourceSpec]:
        keys = [data_source.key for data_source in value]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"data source keys must be unique, duplicated: {duplicates}")
        return value

    @field_validator("metadata_keys")
    @classmethod
    def _metadata_keys_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError(f"metadata_keys contains duplicates: {value}")
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError(f"at most {MAX_METADATA_KEYS} metadata_keys are allowed, got {len(value)}")
        reserved = set(value) & set(BEDROCK_NON_FILTERABLE_KEYS)
        if reserved or any(key.startswith("x-amz-bedrock-kb-") for key in value):
            raise ValueError(f"metadata_keys must not use Bedrock-reserved keys: {value}")
        return value


class KnowledgeBase(Construct):
    """A Bedrock knowledge base with its vector index, service role and data sources.

    Args:
        scope: Parent construct.
        construct_id: Construct ID.
        spec: What to build.
        name: Physical name for the knowledge base. Also used to derive the
            vector index and data source names. Lowercase alphanumerics and
            single hyphens only.
        vector_bucket: S3 Vectors bucket the index is created in.
        permissions_boundary: Optional permissions boundary for the service role.
        index_removal_policy: What happens to the vector index (and its vectors)
            when it is removed from the stack. Defaults to RETAIN, because
            rebuilding it means re-ingesting every document.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        spec: KnowledgeBaseSpec,
        name: str,
        vector_bucket: s3vectors.CfnVectorBucket,
        permissions_boundary: iam.IManagedPolicy | None = None,
        index_removal_policy: cdk.RemovalPolicy = cdk.RemovalPolicy.RETAIN,
    ) -> None:
        super().__init__(scope, construct_id)
        _validate_name(name)
        stack = cdk.Stack.of(self)
        embedding_model_arn = f"arn:aws:bedrock:{stack.region}::foundation-model/{spec.embedding_model.model_id}"

        self._index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            index_name=f"{name}{_INDEX_SUFFIX}",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            data_type="float32",
            dimension=spec.embedding_model.dimension,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=list(BEDROCK_NON_FILTERABLE_KEYS),
            ),
        )
        self._index.apply_removal_policy(index_removal_policy)

        self._role = iam.Role(
            self,
            "Role",
            description=f"Bedrock knowledge base service role for {name}",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": stack.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock:{stack.region}:{stack.account}:knowledge-base/*",
                    },
                },
            ),
            permissions_boundary=permissions_boundary,
        )
        self._grant_source_read(spec.data_sources, deploying_account=stack.account)
        self._role.add_to_policy(
            iam.PolicyStatement(
                sid="VectorIndexReadWrite",
                actions=[
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:GetIndex",
                ],
                resources=[self._index.attr_index_arn],
            )
        )
        self._role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeEmbeddingModel",
                actions=["bedrock:InvokeModel"],
                resources=[embedding_model_arn],
            )
        )
        self._grant_parsing_models(spec.data_sources, region=stack.region, account=stack.account)

        self._knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=name,
            description=spec.description,
            role_arn=self._role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn,
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
                    index_arn=self._index.attr_index_arn,
                ),
            ),
        )
        # Bedrock validates the role's permissions at creation, so its policy must exist first.
        self._knowledge_base.node.add_dependency(self._role)

        for data_source in spec.data_sources:
            bedrock.CfnDataSource(
                self,
                f"DataSource{data_source.key.replace('_', ' ').title().replace(' ', '')}",
                knowledge_base_id=self._knowledge_base.attr_knowledge_base_id,
                name=f"{name}{_DATA_SOURCE_INFIX}{data_source.key.replace('_', '-')}",
                data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                    type="S3",
                    s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                        bucket_arn=f"arn:aws:s3:::{data_source.bucket_name}",
                        bucket_owner_account_id=data_source.bucket_owner_account,
                        inclusion_prefixes=[data_source.prefix] if data_source.prefix else None,
                    ),
                ),
                vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                    chunking_configuration=_chunking_property(spec.chunking),
                    parsing_configuration=_parsing_property(data_source, region=stack.region, account=stack.account),
                ),
            )

    @property
    def knowledge_base_id(self) -> str:
        """Knowledge base ID (token until deploy)."""
        return self._knowledge_base.attr_knowledge_base_id

    @property
    def knowledge_base_arn(self) -> str:
        """Knowledge base ARN (token until deploy)."""
        return self._knowledge_base.attr_knowledge_base_arn

    @property
    def index_arn(self) -> str:
        """S3 Vectors index ARN (token until deploy)."""
        return self._index.attr_index_arn

    @property
    def role(self) -> iam.IRole:
        """Service role Bedrock assumes to ingest and query."""
        return self._role

    def _grant_source_read(self, data_sources: list[DataSourceSpec], *, deploying_account: str) -> None:
        """Grant List/Get on each source bucket, pinned to the bucket owner's account.

        Manual statements rather than ``Bucket.grant_read``: the ``aws:ResourceAccount``
        condition stops a same-named bucket in another account from being read.
        """
        for i, data_source in enumerate(data_sources):
            owner = {"StringEquals": {"aws:ResourceAccount": data_source.bucket_owner_account or deploying_account}}
            bucket_arn = f"arn:aws:s3:::{data_source.bucket_name}"
            self._role.add_to_policy(
                iam.PolicyStatement(
                    sid=f"ListSourceBucket{i}",
                    actions=["s3:ListBucket"],
                    resources=[bucket_arn],
                    conditions=owner,
                )
            )
            self._role.add_to_policy(
                iam.PolicyStatement(
                    sid=f"GetSourceObjects{i}",
                    actions=["s3:GetObject"],
                    resources=[f"{bucket_arn}/{data_source.prefix}*"],
                    conditions=owner,
                )
            )

    def _grant_parsing_models(self, data_sources: list[DataSourceSpec], *, region: str, account: str) -> None:
        """Grant invoke on each distinct parsing inference profile and its foundation model."""
        profiles = sorted({ds.parsing_model for ds in data_sources if ds.parsing_model})
        for i, profile_id in enumerate(profiles):
            base_model_id = profile_id.split(".", 1)[1]
            self._role.add_to_policy(
                iam.PolicyStatement(
                    sid=f"InvokeParsingProfile{i}",
                    actions=["bedrock:InvokeModel", "bedrock:GetInferenceProfile"],
                    resources=[_inference_profile_arn(profile_id, region=region, account=account)],
                )
            )
            self._role.add_to_policy(
                iam.PolicyStatement(
                    sid=f"InvokeParsingFoundationModel{i}",
                    actions=["bedrock:InvokeModel"],
                    # Region wildcard: a cross-region profile routes to the model in any region it spans.
                    resources=[f"arn:aws:bedrock:*::foundation-model/{base_model_id}"],
                )
            )


def _validate_name(name: str) -> None:
    if not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"name must be lowercase alphanumerics with single hyphens, got {name!r}")
    if len(name) + len(_INDEX_SUFFIX) > _MAX_INDEX_NAME_LENGTH:
        raise ValueError(f"name must be at most {_MAX_INDEX_NAME_LENGTH - len(_INDEX_SUFFIX)} characters, got {name!r}")


def _inference_profile_arn(profile_id: str, *, region: str, account: str) -> str:
    return f"arn:aws:bedrock:{region}:{account}:inference-profile/{profile_id}"


def _chunking_property(chunking: Chunking) -> bedrock.CfnDataSource.ChunkingConfigurationProperty:
    match chunking:
        case SemanticChunking():
            return bedrock.CfnDataSource.ChunkingConfigurationProperty(
                chunking_strategy="SEMANTIC",
                semantic_chunking_configuration=bedrock.CfnDataSource.SemanticChunkingConfigurationProperty(
                    max_tokens=chunking.max_tokens,
                    buffer_size=chunking.buffer_size,
                    breakpoint_percentile_threshold=chunking.breakpoint_percentile_threshold,
                ),
            )
        case FixedSizeChunking():
            return bedrock.CfnDataSource.ChunkingConfigurationProperty(
                chunking_strategy="FIXED_SIZE",
                fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                    max_tokens=chunking.max_tokens,
                    overlap_percentage=chunking.overlap_percentage,
                ),
            )
        case NoChunking():
            return bedrock.CfnDataSource.ChunkingConfigurationProperty(chunking_strategy="NONE")


def _parsing_property(
    data_source: DataSourceSpec, *, region: str, account: str
) -> bedrock.CfnDataSource.ParsingConfigurationProperty | None:
    if not data_source.parsing_model:
        return None
    return bedrock.CfnDataSource.ParsingConfigurationProperty(
        parsing_strategy="BEDROCK_FOUNDATION_MODEL",
        bedrock_foundation_model_configuration=bedrock.CfnDataSource.BedrockFoundationModelConfigurationProperty(
            model_arn=_inference_profile_arn(data_source.parsing_model, region=region, account=account),
        ),
    )
