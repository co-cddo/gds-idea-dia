"""The Bedrock knowledge bases this project deploys.

Each entry is a `KnowledgeBaseSpec` for the reusable template in
`stacks/constructs/knowledge_base.py`. Adding a knowledge base means adding one
entry to `knowledge_bases()`, and its document type to `DOCUMENT_TYPES`.

Source buckets owned by other projects are named literally. Buckets this repo
creates are named through `config.names(Bucket.X)`. Each source states which
environment's account owns its bucket, and the data source is marked
cross-account whenever that isn't the account being deployed to.

Usage:
    config = AppConfig(environment=DeploymentEnvironment.DEVELOPMENT)
    for spec in knowledge_bases(config):
        ...
"""

from __future__ import annotations

from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig
from dia.document_types import DocumentType
from dia.naming import Bucket
from stacks.constructs.knowledge_base import DataSourceSpec, KnowledgeBaseSpec

HAIKU_4_5 = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

# Keys every document may carry in its .metadata.json sidecar.
COMMON_METADATA_KEYS: tuple[str, ...] = ("department_name", "alb", "document_type", "report_type", "year")

# The `document_type` value written to each knowledge base's sidecars.
DOCUMENT_TYPES: dict[str, DocumentType] = {
    "gats_business_cases": DocumentType.BUSINESS_CASE,
    "sr25_bids": DocumentType.SR_BIDS_2025,
    "sr21_bids": DocumentType.SR_BIDS_2021,
    "nao_reports": DocumentType.NAO_REPORT,
    "efficiency_reports": DocumentType.EFFICIENCY_REPORT,
    "other_reports": DocumentType.TECHNOLOGY_REPORT,
    "dbr_readouts_letter": DocumentType.DBR_READOUT,
    "dbr_reports": DocumentType.DBR_REPORT,
}

_DIA_DOCUMENTS_BUCKET = "gds-idea-digital-intelligence-agent-documents"


def knowledge_bases(config: AppConfig) -> list[KnowledgeBaseSpec]:
    """Knowledge bases to deploy in the given environment.

    Args:
        config: The deployment's configuration, used for bucket names and to
            decide which sources are cross-account.

    Returns:
        One spec per knowledge base.
    """

    def source(
        bucket: str,
        *,
        owner: DeploymentEnvironment,
        prefix: str = "",
        parsing_model: str | None = None,
    ) -> DataSourceSpec:
        return DataSourceSpec(
            bucket_name=bucket,
            prefix=prefix,
            bucket_owner_account=None if owner == config.environment else owner.value,
            parsing_model=parsing_model,
        )

    dev = DeploymentEnvironment.DEVELOPMENT
    prod = DeploymentEnvironment.PRODUCTION
    dbr_bucket = config.names(Bucket.DBR_REPORTS)

    return [
        KnowledgeBaseSpec(
            key="gats_business_cases",
            description="GATS business cases: OBCs, FBCs and programme cases submitted through spend controls",
            data_sources=[source("c-af-get-approval-spend-service-business-cases", owner=prod, prefix="files/")],
            metadata_keys=(*COMMON_METADATA_KEYS, "spend_id", "project_name", "assurance_date", "file_reference"),
        ),
        KnowledgeBaseSpec(
            key="sr25_bids",
            description="SR25 spending review bids and submissions",
            data_sources=[source("gds-idea-sr-query-documentstore-dev", owner=dev)],
            metadata_keys=(*COMMON_METADATA_KEYS, "spend_id", "project_name", "file_reference"),
        ),
        KnowledgeBaseSpec(
            key="sr21_bids",
            description="SR21 spending review bids and submissions",
            data_sources=[source("gds-idea-spending-review-21-bids", owner=dev)],
            metadata_keys=(*COMMON_METADATA_KEYS, "project_name"),
        ),
        KnowledgeBaseSpec(
            key="nao_reports",
            description="NAO reports, PAC findings and value-for-money assessments",
            data_sources=[source("gds-idea-assurance-nao", owner=dev, prefix="files/", parsing_model=HAIKU_4_5)],
            metadata_keys=COMMON_METADATA_KEYS,
        ),
        KnowledgeBaseSpec(
            key="efficiency_reports",
            description="Interim efficiency reports 2026, based on SR25 spending bids",
            data_sources=[
                source(
                    _DIA_DOCUMENTS_BUCKET,
                    owner=dev,
                    prefix="interim-efficiency-report-26/",
                    parsing_model=HAIKU_4_5,
                )
            ],
            metadata_keys=COMMON_METADATA_KEYS,
        ),
        KnowledgeBaseSpec(
            key="other_reports",
            description="Technology and other reports and presentations",
            data_sources=[source(_DIA_DOCUMENTS_BUCKET, owner=dev, prefix="technology/", parsing_model=HAIKU_4_5)],
            metadata_keys=COMMON_METADATA_KEYS,
        ),
        KnowledgeBaseSpec(
            key="dbr_readouts_letter",
            description="Letters sent after Digital Business Review sessions, used to brief the next DBR",
            data_sources=[source(dbr_bucket, owner=config.environment, prefix="readouts/")],
            metadata_keys=(*COMMON_METADATA_KEYS, "readout_date", "is_latest"),
        ),
        KnowledgeBaseSpec(
            key="dbr_reports",
            description="DIA-generated Digital Business Review reports",
            data_sources=[source(dbr_bucket, owner=config.environment, prefix="reports/")],
            metadata_keys=(*COMMON_METADATA_KEYS, "report_date", "is_latest"),
        ),
    ]
