"""Tests for dia.metadata.registry — source name to metadata strategy dispatch."""

from unittest.mock import patch

import pytest

from dia.metadata.registry import load_metadata


def test_gats_source_loads_historic_and_gats(monkeypatch):
    historic_records = [{"filenames": "legacy.pdf", "department": "DWP"}]
    gats_records = [{"CO_OrganisationSubmitter": "Home Office", "CO_SpendID": "CS-100", "CO_CS_Files": "new.pdf"}]

    with (
        patch("dia.metadata.registry.load_csv_from_s3", return_value=historic_records) as mock_csv,
        patch("dia.metadata.registry.load_latest_csv_from_s3", return_value=gats_records) as mock_latest,
    ):
        provider = load_metadata("gats-business-cases", source_prefix="files/")

    assert provider is not None
    assert provider.get_metadata("files/legacy.pdf").department == "DWP"
    assert provider.get_metadata("files/new.pdf").department == "Home Office"

    mock_csv.assert_called_once()
    mock_latest.assert_called_once()


def test_historic_csv_source_loads_single_csv():
    records = [{"filenames": "bid.pdf", "department": "HMRC"}]

    with patch("dia.metadata.registry.load_csv_from_s3", return_value=records) as mock_csv:
        provider = load_metadata("sr-bids-2025", source_prefix="")

    assert provider is not None
    assert provider.get_metadata("bid.pdf").department == "HMRC"
    mock_csv.assert_called_once()


def test_folder_name_source_uses_document_keys():
    keys = ["sr21-bids/Home Office/report.pdf"]

    provider = load_metadata("sr-bids-2021", source_prefix="sr21-bids/", document_keys=keys)

    assert provider is not None
    assert provider.get_metadata("sr21-bids/Home Office/report.pdf").department == "Home Office"


def test_folder_name_source_without_document_keys_raises():
    with pytest.raises(ValueError, match="document_keys is required"):
        load_metadata("sr-bids-2021", source_prefix="sr21-bids/")


def test_unknown_source_returns_none():
    provider = load_metadata("some-unregistered-source", source_prefix="")

    assert provider is None
