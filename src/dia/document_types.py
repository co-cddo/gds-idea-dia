"""Document type definitions and per-type processing configuration.

This module is the single source of truth for document types and their
associated processing configuration (entity classifications, chunking strategy).

Adding a new document type:
    1. Add an enum value to DocumentType
    2. Add an entry to _CONFIGS with id_field and optionally chunking

Adding a new source of an existing type:
    See src/dia/sources/known.py — just one DataSource entry.
"""

from enum import StrEnum

from pydantic import BaseModel

from dia.config import ChunkingConfig


class DocumentTypeConfig(BaseModel, frozen=True):
    """Per-document-type processing configuration.

    Defines the entity classification ID field and chunking strategy
    for a document type. Referenced by DocumentType properties.
    """

    id_field: str
    chunking: ChunkingConfig = ChunkingConfig()


# ---------------------------------------------------------------------------
# Base entity classifications (shared across all document types)
# ---------------------------------------------------------------------------

BASE_ENTITY_CLASSIFICATIONS: list[str] = [
    # Core identifiers
    "Programme Name",
    "Project Name",
    "Portfolio",
    "Tier",
    # Organisations & people
    "Supplier",
    "Government Departments",
    "Arm's Length Body",
    "Committee",
    "Organisational Unit",
    "Team",
    "Person",
    "Role",
    "Stakeholder",
    "Government Function",
    # Legal & governance
    "Service",
    "Legislation",
    "Regulation",
    "Contract",
    "Framework",
    "Policy",
    "Standard",
    "Obligation",
    "Spending Control",
    "Assurance Review",
    # Commercial & procurement
    "Commercial Model",
    "Procurement Route",
    "Lot",
    "SLA",
    "Penalty",
    "Critical Success Factor",
    # Financial
    "Cost Category",
    "Funding Source",
    "Financial Metric",
    "Accounting Standard",
    "Tax Regime",
    "Budget Line",
    "Headcount",
    "Outturn",
    "Contingency",
    "Write-off",
    # Digital & technology
    "Thematic Topic of Digital",
    "Technological Application",
    "System",
    "Platform",
    "Data Asset",
    "API",
    "Integration",
    "Architecture Pattern",
    "Design Pattern",
    "Security Classification",
    "Accessibility Standard",
    # Strategy & delivery
    "Methodology",
    "Benefit",
    "Risk",
    "Option",
    "Strategic Objective",
    "Outcome",
    "KPI",
    "Milestone",
    "Deliverable",
    "Dependency",
    "Capability",
    "Priority",
    "Manifesto Commitment",
    "Assumption",
    "Constraint",
    # Accountability & audit
    "Finding",
    "Recommendation",
    "Incident",
    "Lesson Learned",
    "User Need",
    # Documents & process
    "Document",
    "Process",
    "Approval Gate",
    # Context
    "Location",
    "Sector",
    "Event",
]


class DocumentType(StrEnum):
    """Document types supported by the extraction pipeline.

    Each value carries per-type processing configuration via properties:
        doc_type.config                 → DocumentTypeConfig
        doc_type.entity_classifications → full list including ID field
        doc_type.chunking               → ChunkingConfig for this type
    """

    BUSINESS_CASE = "business_case"
    SR_BIDS = "sr_bids"
    CONTRACT_FINDER = "contract_finder"

    @property
    def config(self) -> DocumentTypeConfig:
        """Per-type processing configuration."""
        return _CONFIGS[self]

    @property
    def entity_classifications(self) -> list[str]:
        """Full entity classification list including the type-specific ID field."""
        return [*BASE_ENTITY_CLASSIFICATIONS, self.config.id_field]

    @property
    def chunking(self) -> ChunkingConfig:
        """Chunking strategy for this document type."""
        return self.config.chunking


# ---------------------------------------------------------------------------
# Per-type configuration (referenced by DocumentType properties above)
# ---------------------------------------------------------------------------

_CONFIGS: dict[DocumentType, DocumentTypeConfig] = {
    DocumentType.BUSINESS_CASE: DocumentTypeConfig(id_field="Spend ID"),
    DocumentType.SR_BIDS: DocumentTypeConfig(id_field="Spend ID"),
    DocumentType.CONTRACT_FINDER: DocumentTypeConfig(
        id_field="Contract ID",
        chunking=ChunkingConfig(use_semantic_splitting=False),
    ),
}

# Validate completeness at import time — if you add a DocumentType but forget
# the config entry, this module will refuse to import.
_missing = set(DocumentType) - set(_CONFIGS.keys())
if _missing:
    raise RuntimeError(f"Missing DocumentTypeConfig for: {_missing}")
