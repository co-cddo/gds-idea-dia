"""Wires known sources to their metadata-loading strategy.

Each source's documents come with metadata from a different place —
GATS exports, a dedicated historic CSV, or the S3 folder structure itself.
This module is the one place that knows which strategy applies to which
source, and what bucket/key info to use.

Adding a new source with metadata support: add an entry to whichever of
_GATS_SOURCES / _HISTORIC_CSV_SOURCES / _FOLDER_NAME_SOURCES matches its
strategy.
"""

from dia.metadata.builders import build_folder_name_lookup, build_gats_lookup, build_historic_csv_lookup
from dia.metadata.csv_loader import load_csv_from_s3, load_latest_csv_from_s3
from dia.metadata.provider import MetadataProvider

_METADATA_BUCKET = "c-af-get-approval-spend-service-business-cases-dev"

_HISTORIC_CSV_SOURCES = {
    "sr-bids-2025": "department_files/historic_sr_bids_metadata.csv",
}

_GATS_SOURCES = {
    "gats-business-cases": {
        "historic_key": "department_files/historic_cases_metadata.csv",
        "gats_prefix": "spend-controls-raw-data/",
    },
}

_FOLDER_NAME_SOURCES = {
    "sr-bids-2021",
}


def load_metadata(
    source_name: str,
    source_prefix: str,
    s3_client=None,
    document_keys: list[str] | None = None,
) -> MetadataProvider | None:
    """Load the metadata provider for a known source, if it has one.

    Args:
        source_name: The source name (key in KNOWN_SOURCES).
        source_prefix: The source's key prefix, used to build full document keys.
        s3_client: Optional injected S3 client (for testing).
        document_keys: Full document keys from source.list_documents().
            Only required for folder_name-strategy sources.

    Returns:
        A MetadataProvider, or None if the source has no metadata configured.
        Callers should treat None as "no enrichment / no department filtering
        available for this source".
    """
    if source_name in _GATS_SOURCES:
        config = _GATS_SOURCES[source_name]
        historic = load_csv_from_s3(_METADATA_BUCKET, config["historic_key"], s3_client)
        gats = load_latest_csv_from_s3(_METADATA_BUCKET, config["gats_prefix"], s3_client)
        return MetadataProvider(build_gats_lookup(historic, gats, source_prefix))

    if source_name in _HISTORIC_CSV_SOURCES:
        historic_key = _HISTORIC_CSV_SOURCES[source_name]
        records = load_csv_from_s3(_METADATA_BUCKET, historic_key, s3_client)
        return MetadataProvider(build_historic_csv_lookup(records, source_prefix))

    if source_name in _FOLDER_NAME_SOURCES:
        if document_keys is None:
            msg = f"Source {source_name!r} uses folder_name metadata — document_keys is required"
            raise ValueError(msg)
        return MetadataProvider(build_folder_name_lookup(document_keys, source_prefix))

    return None
