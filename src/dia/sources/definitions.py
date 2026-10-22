"""The datasets this project reads, declared once for every pipeline.

To add a dataset, add one entry to `SOURCES`. Everything about it lives in that
entry: where its documents are, their document type, and which pipelines use it.

    "my_reports": SourceDefinition(
        description="What it holds",
        document_type=DocumentType.TECHNOLOGY_REPORT,
        location=Location(bucket=Bucket.REPORTS, prefix="my-reports/"),
        knowledge_base=KnowledgeBaseSettings(),
    ),

Keys are snake_case. Knowledge base names are derived from them.

A location is one of our own buckets (a `Bucket` member: it exists in dev and prod,
and we can write to it), or an `ExternalBucket` with every name written out. See
`dia.sources.models`.
"""

from __future__ import annotations

from dia.document_types import DocumentType
from dia.naming import Bucket
from dia.sources.models import (
    ExternalBucket,
    KnowledgeBaseSettings,
    Location,
    SourceDefinition,
)

HAIKU_4_5 = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

SOURCES: dict[str, SourceDefinition] = {
    "gats_business_cases": SourceDefinition(
        description="GATS business cases: OBCs, FBCs and programme cases submitted through spend controls",
        document_type=DocumentType.BUSINESS_CASE,
        # Owned by another team, in the production account. Dev reads it through the cross-account role.
        location=Location(
            bucket=ExternalBucket(
                prod="c-af-get-approval-spend-service-business-cases",
                dev_via_cross_account=True,
            ),
            prefix="files/",
        ),
        extra_metadata_keys=("spend_id", "project_name", "assurance_date", "file_reference"),
        graph=True,
        knowledge_base=KnowledgeBaseSettings(),
    ),
    "sr25_bids": SourceDefinition(
        description="SR25 spending review bids and submissions",
        document_type=DocumentType.SR_BIDS_2025,
        location=Location(bucket=Bucket.SR25_BIDS),
        extra_metadata_keys=("spend_id", "project_name", "file_reference"),
        knowledge_base=KnowledgeBaseSettings(),
    ),
    "sr21_bids": SourceDefinition(
        description="SR21 spending review bids and submissions",
        document_type=DocumentType.SR_BIDS_2021,
        location=Location(bucket=Bucket.SR21_BIDS),
        extra_metadata_keys=("project_name",),
        knowledge_base=KnowledgeBaseSettings(),
    ),
    "nao_reports": SourceDefinition(
        description="NAO reports, PAC findings and value-for-money assessments",
        document_type=DocumentType.NAO_REPORT,
        location=Location(bucket=Bucket.NAO_REPORTS, prefix="files/"),
        knowledge_base=KnowledgeBaseSettings(parsing_model=HAIKU_4_5),
    ),
    "efficiency_reports": SourceDefinition(
        description="Interim efficiency reports 2026, based on SR25 spending bids",
        document_type=DocumentType.EFFICIENCY_REPORT,
        location=Location(bucket=Bucket.REPORTS, prefix="interim-efficiency-report-26/"),
        knowledge_base=KnowledgeBaseSettings(parsing_model=HAIKU_4_5),
    ),
    "other_reports": SourceDefinition(
        description="Technology and other reports and presentations",
        document_type=DocumentType.TECHNOLOGY_REPORT,
        location=Location(bucket=Bucket.REPORTS, prefix="technology/"),
        knowledge_base=KnowledgeBaseSettings(parsing_model=HAIKU_4_5),
    ),
    "dbr_readouts_letter": SourceDefinition(
        description="Letters sent after Digital Business Review sessions, used to brief the next DBR",
        document_type=DocumentType.DBR_READOUT,
        location=Location(bucket=Bucket.DBR_REPORTS, prefix="readouts/"),
        extra_metadata_keys=("readout_date", "is_latest"),
        knowledge_base=KnowledgeBaseSettings(deployed=True),
    ),
    "dbr_reports": SourceDefinition(
        description="DIA-generated Digital Business Review reports",
        document_type=DocumentType.DBR_REPORT,
        location=Location(bucket=Bucket.DBR_REPORTS, prefix="reports/"),
        extra_metadata_keys=("report_date", "is_latest"),
        knowledge_base=KnowledgeBaseSettings(deployed=True),
    ),
}


def graph_sources() -> dict[str, SourceDefinition]:
    """The sources that go through our extraction into the graph."""
    return {key: source for key, source in SOURCES.items() if source.graph}
