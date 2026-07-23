"""Known data sources for the DIA pipeline."""

from dia.document_types import DocumentType
from dia.types import DataSource

KNOWN_SOURCES: dict[str, DataSource] = {
    "gats-business-cases": DataSource(
        name="gats-business-cases",
        document_type=DocumentType.BUSINESS_CASE,
        bucket="c-af-get-approval-spend-service-business-cases",
        prefix="files/",
        cross_account=True,
    ),
    "sr-bids-2025": DataSource(
        name="sr-bids-2025",
        document_type=DocumentType.SR_BIDS,
        bucket="gds-idea-sr-query-documentstore-dev",
        prefix="",
    ),
}


def get_source(name: str) -> DataSource:
    """Get a known data source by name.

    Raises:
        KeyError: If the source name is not found.
    """
    return KNOWN_SOURCES[name]
