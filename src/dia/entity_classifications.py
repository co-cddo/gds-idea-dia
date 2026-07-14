"""Entity classifications for knowledge graph extraction.

This module is the single source of truth for the entity classification
list used across all document types.
"""

from dia.types import DocumentType

# ---------------------------------------------------------------------------
# Base classifications (shared across all document types)
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

# ---------------------------------------------------------------------------
# Document-type-specific ID fields
# ---------------------------------------------------------------------------

DOCUMENT_TYPE_ID_FIELDS: dict[DocumentType, str] = {
    DocumentType.BUSINESS_CASE: "Spend ID",
    DocumentType.SR_BIDS: "Spend ID",
    DocumentType.CONTRACT_FINDER: "Contract ID",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_entity_classifications(document_type: DocumentType) -> list[str]:
    """Return the full entity classifications list for a document type.

    Appends the appropriate ID field (Spend ID or Contract ID)
    based on the document type.

    Args:
        document_type: The type of document being processed.

    Returns:
        Complete list of entity classifications including the ID field.

    Raises:
        KeyError: If document_type is not a valid DocumentType.
    """
    return BASE_ENTITY_CLASSIFICATIONS + [DOCUMENT_TYPE_ID_FIELDS[document_type]]
