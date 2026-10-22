"""Tests for the knowledge base declarations in knowledge_bases.py."""

import re
from pathlib import Path

import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment

from config import AppConfig
from dia.document_types import DocumentType
from dia.naming import Bucket
from knowledge_bases import DOCUMENT_TYPES, KNOWLEDGE_BASES
from stacks.knowledge_base_entries import (
    COMMON_METADATA_KEYS,
    KnowledgeBaseEntry,
    Source,
    deployed_knowledge_bases,
    knowledge_bases,
)

DEV = DeploymentEnvironment.DEVELOPMENT
PROD = DeploymentEnvironment.PRODUCTION
ENVIRONMENTS = [DEV, PROD]

EXPECTED_KEYS = {
    "gats_business_cases",
    "sr25_bids",
    "sr21_bids",
    "nao_reports",
    "efficiency_reports",
    "other_reports",
    "dbr_readouts_letter",
    "dbr_reports",
}

DEV_ACCOUNT_SOURCES = {"sr25_bids", "sr21_bids", "nao_reports", "efficiency_reports", "other_reports"}


def _by_key(environment: DeploymentEnvironment) -> dict:
    return {spec.key: spec for spec in knowledge_bases(AppConfig(environment=environment), KNOWLEDGE_BASES)}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_declares_every_knowledge_base_once(environment):
    specs = knowledge_bases(AppConfig(environment=environment), KNOWLEDGE_BASES)
    keys = [spec.key for spec in specs]
    assert len(keys) == len(set(keys))
    assert set(keys) == EXPECTED_KEYS


def test_every_knowledge_base_has_a_document_type():
    assert set(DOCUMENT_TYPES) == EXPECTED_KEYS
    assert all(isinstance(value, DocumentType) for value in DOCUMENT_TYPES.values())


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_every_knowledge_base_carries_the_common_metadata_keys(environment):
    for spec in knowledge_bases(AppConfig(environment=environment), KNOWLEDGE_BASES):
        assert set(COMMON_METADATA_KEYS) <= set(spec.metadata_keys), spec.key


def test_metadata_uses_department_name():
    for spec in knowledge_bases(AppConfig(environment=DEV), KNOWLEDGE_BASES):
        assert "department" not in spec.metadata_keys, spec.key


@pytest.mark.parametrize("key", ["dbr_readouts_letter", "dbr_reports"])
def test_dbr_knowledge_bases_mark_the_latest_document(key):
    assert "is_latest" in _by_key(DEV)[key].metadata_keys


# --- bucket ownership ---


def test_gats_is_cross_account_in_dev_only():
    (dev_source,) = _by_key(DEV)["gats_business_cases"].data_sources
    (prod_source,) = _by_key(PROD)["gats_business_cases"].data_sources
    assert dev_source.bucket_owner_account == PROD.value
    assert prod_source.bucket_owner_account is None


@pytest.mark.parametrize("key", sorted(DEV_ACCOUNT_SOURCES))
def test_dev_account_buckets_are_cross_account_in_prod_only(key):
    (dev_source,) = _by_key(DEV)[key].data_sources
    (prod_source,) = _by_key(PROD)[key].data_sources
    assert dev_source.bucket_owner_account is None
    assert prod_source.bucket_owner_account == DEV.value


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize("key,prefix", [("dbr_readouts_letter", "readouts/"), ("dbr_reports", "reports/")])
def test_dbr_knowledge_bases_read_this_environments_dbr_bucket(environment, key, prefix):
    (source,) = _by_key(environment)[key].data_sources
    assert source.bucket_name == f"gds-idea-dia-dbr-reports-{environment.short_name}"
    assert source.prefix == prefix
    assert source.bucket_owner_account is None


# --- parsing ---


@pytest.mark.parametrize("key", ["nao_reports", "efficiency_reports", "other_reports"])
def test_report_knowledge_bases_parse_with_a_foundation_model(key):
    (source,) = _by_key(DEV)[key].data_sources
    assert source.parsing_model is not None


@pytest.mark.parametrize("key", ["sr25_bids", "sr21_bids", "dbr_readouts_letter", "dbr_reports"])
def test_text_knowledge_bases_use_default_parsing(key):
    (source,) = _by_key(DEV)[key].data_sources
    assert source.parsing_model is None


# --- source validation ---


def test_a_literal_bucket_must_say_who_owns_it():
    with pytest.raises(ValueError, match="owner"):
        Source(bucket="some-bucket")


def test_a_bucket_this_repo_creates_must_not_name_an_owner():
    with pytest.raises(ValueError, match="owner"):
        Source(bucket=Bucket.DBR_REPORTS, owner=DEV)


# --- data source keys ---


def _entry(*sources: Source) -> KnowledgeBaseEntry:
    return KnowledgeBaseEntry(
        description="Test", document_type=DocumentType.TECHNOLOGY_REPORT, data_sources=list(sources)
    )


def test_a_single_source_is_keyed_by_its_knowledge_base():
    for spec in knowledge_bases(AppConfig(environment=DEV), KNOWLEDGE_BASES):
        (source,) = spec.data_sources
        assert source.key == spec.key


def test_several_sources_use_their_own_keys():
    entry = _entry(
        Source(key="first", bucket="bucket-a", owner=DEV),
        Source(key="second", bucket="bucket-b", owner=DEV),
    )
    (spec,) = knowledge_bases(AppConfig(environment=DEV), {"reports": entry})
    assert [source.key for source in spec.data_sources] == ["first", "second"]


def test_several_sources_without_keys_are_rejected():
    with pytest.raises(ValueError, match="key"):
        _entry(Source(key="first", bucket="bucket-a", owner=DEV), Source(bucket="bucket-b", owner=DEV))


# --- open-source safety ---


def test_declarations_contain_no_account_ids():
    source = Path(__file__).resolve().parent.parent.joinpath("knowledge_bases.py").read_text()
    assert not re.search(r"\b\d{12}\b", source)


# --- what gets deployed ---


def test_deployed_entries_are_the_two_dbr_ones():
    assert {key for key, entry in KNOWLEDGE_BASES.items() if entry.deployed} == {"dbr_readouts_letter", "dbr_reports"}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_only_the_dbr_knowledge_bases_are_deployed(environment):
    keys = {spec.key for spec in deployed_knowledge_bases(AppConfig(environment=environment), KNOWLEDGE_BASES)}
    assert keys == {"dbr_readouts_letter", "dbr_reports"}
