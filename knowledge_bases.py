"""The Bedrock knowledge bases this project deploys.

To add a knowledge base, add one entry to `KNOWLEDGE_BASES` below. Everything
about it lives in that entry. Set `deployed=True` to have the stack create it.

    "my_reports": KnowledgeBaseEntry(
        description="What it holds",
        document_type=DocumentType.TECHNOLOGY_REPORT,
        data_sources=[Source(bucket="some-bucket", owner=DeploymentEnvironment.DEVELOPMENT, prefix="files/")],
        extra_metadata_keys=("spend_id",),
        deployed=True,
    ),

Each source names the bucket and the environment whose account owns it. For a
bucket owned by another project, give its literal name and `owner`. For a bucket
this repo creates, give the `Bucket` enum member and leave `owner` out: it is
named through `config.names(...)` and lives in the account being deployed to.
A source is cross-account whenever its owner isn't the account being deployed
to, so no account IDs are written here.

A data source is named after its `key`, not its position. A knowledge base with
one source needs no key (it uses the knowledge base's key). With several, give
each source a key and keep it once deployed: renaming one replaces the data
source.

The models are in `stacks/knowledge_base_entries.py`, which also turns this
table into the specs the stack builds.
"""

from __future__ import annotations

from gds_idea_cdk_constructs import DeploymentEnvironment

from dia.document_types import DocumentType
from dia.naming import Bucket
from stacks.knowledge_base_entries import KnowledgeBaseEntry, Source

HAIKU_4_5 = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

_DIA_DOCUMENTS_BUCKET = "gds-idea-digital-intelligence-agent-documents"

KNOWLEDGE_BASES: dict[str, KnowledgeBaseEntry] = {
    "gats_business_cases": KnowledgeBaseEntry(
        description="GATS business cases: OBCs, FBCs and programme cases submitted through spend controls",
        document_type=DocumentType.BUSINESS_CASE,
        data_sources=[
            Source(
                bucket="c-af-get-approval-spend-service-business-cases",
                owner=DeploymentEnvironment.PRODUCTION,
                prefix="files/",
            )
        ],
        extra_metadata_keys=("spend_id", "project_name", "assurance_date", "file_reference"),
    ),
    "sr25_bids": KnowledgeBaseEntry(
        description="SR25 spending review bids and submissions",
        document_type=DocumentType.SR_BIDS_2025,
        data_sources=[Source(bucket="gds-idea-sr-query-documentstore-dev", owner=DeploymentEnvironment.DEVELOPMENT)],
        extra_metadata_keys=("spend_id", "project_name", "file_reference"),
    ),
    "sr21_bids": KnowledgeBaseEntry(
        description="SR21 spending review bids and submissions",
        document_type=DocumentType.SR_BIDS_2021,
        data_sources=[Source(bucket="gds-idea-spending-review-21-bids", owner=DeploymentEnvironment.DEVELOPMENT)],
        extra_metadata_keys=("project_name",),
    ),
    "nao_reports": KnowledgeBaseEntry(
        description="NAO reports, PAC findings and value-for-money assessments",
        document_type=DocumentType.NAO_REPORT,
        data_sources=[
            Source(
                bucket="gds-idea-assurance-nao",
                owner=DeploymentEnvironment.DEVELOPMENT,
                prefix="files/",
                parsing_model=HAIKU_4_5,
            )
        ],
    ),
    "efficiency_reports": KnowledgeBaseEntry(
        description="Interim efficiency reports 2026, based on SR25 spending bids",
        document_type=DocumentType.EFFICIENCY_REPORT,
        data_sources=[
            Source(
                bucket=_DIA_DOCUMENTS_BUCKET,
                owner=DeploymentEnvironment.DEVELOPMENT,
                prefix="interim-efficiency-report-26/",
                parsing_model=HAIKU_4_5,
            )
        ],
    ),
    "other_reports": KnowledgeBaseEntry(
        description="Technology and other reports and presentations",
        document_type=DocumentType.TECHNOLOGY_REPORT,
        data_sources=[
            Source(
                bucket=_DIA_DOCUMENTS_BUCKET,
                owner=DeploymentEnvironment.DEVELOPMENT,
                prefix="technology/",
                parsing_model=HAIKU_4_5,
            )
        ],
    ),
    "dbr_readouts_letter": KnowledgeBaseEntry(
        description="Letters sent after Digital Business Review sessions, used to brief the next DBR",
        document_type=DocumentType.DBR_READOUT,
        data_sources=[Source(bucket=Bucket.DBR_REPORTS, prefix="readouts/")],
        extra_metadata_keys=("readout_date", "is_latest"),
        deployed=True,
    ),
    "dbr_reports": KnowledgeBaseEntry(
        description="DIA-generated Digital Business Review reports",
        document_type=DocumentType.DBR_REPORT,
        data_sources=[Source(bucket=Bucket.DBR_REPORTS, prefix="reports/")],
        extra_metadata_keys=("report_date", "is_latest"),
        deployed=True,
    ),
}

# The `document_type` value written to each knowledge base's sidecars.
DOCUMENT_TYPES: dict[str, DocumentType] = {key: entry.document_type for key, entry in KNOWLEDGE_BASES.items()}
