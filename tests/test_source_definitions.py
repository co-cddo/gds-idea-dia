"""Tests for dia.sources.models and dia.sources.definitions — source declarations."""

import json

import pytest
from gds_idea_cdk_constructs import DeploymentEnvironment
from pydantic import ValidationError

from dia.document_types import DocumentType
from dia.naming import Bucket
from dia.sources.definitions import SOURCES, graph_sources
from dia.sources.models import (
    COMMON_METADATA_KEYS,
    ExternalBucket,
    KnowledgeBaseSettings,
    Location,
    ResolvedLocation,
    SourceDefinition,
    resolve,
)

DEV = DeploymentEnvironment.DEVELOPMENT
PROD = DeploymentEnvironment.PRODUCTION

# --- ExternalBucket ---


def test_an_external_bucket_with_its_own_dev_bucket_is_valid():
    bucket = ExternalBucket(prod="some-prod-bucket", dev="some-dev-bucket")

    assert bucket.dev == "some-dev-bucket"
    assert bucket.dev_via_cross_account is False


def test_an_external_bucket_read_through_the_cross_account_role_is_valid():
    bucket = ExternalBucket(prod="some-prod-bucket", dev_via_cross_account=True)

    assert bucket.dev is None


def test_an_external_bucket_must_say_how_dev_reads_it():
    with pytest.raises(ValidationError, match="exactly one of dev"):
        ExternalBucket(prod="some-prod-bucket")


def test_an_external_bucket_cannot_have_both_a_dev_bucket_and_the_cross_account_flag():
    with pytest.raises(ValidationError, match="exactly one of dev"):
        ExternalBucket(prod="some-prod-bucket", dev="some-dev-bucket", dev_via_cross_account=True)


# --- resolve ---


def test_one_of_our_buckets_is_named_by_phase_and_is_never_cross_account():
    location = Location(bucket=Bucket.DBR_REPORTS, prefix="readouts/")

    assert resolve(location, DEV) == ResolvedLocation("gds-idea-dia-dbr-reports-dev", "readouts/", False, True)
    assert resolve(location, PROD) == ResolvedLocation("gds-idea-dia-dbr-reports-prod", "readouts/", False, True)


def test_an_external_bucket_is_read_directly_in_prod():
    location = Location(bucket=ExternalBucket(prod="the-prod-bucket", dev="the-dev-bucket"), prefix="files/")

    assert resolve(location, PROD) == ResolvedLocation("the-prod-bucket", "files/", False, False)


def test_an_external_bucket_with_a_dev_bucket_is_read_from_it_in_dev():
    location = Location(bucket=ExternalBucket(prod="the-prod-bucket", dev="the-dev-bucket"))

    assert resolve(location, DEV) == ResolvedLocation("the-dev-bucket", "", False, False)


def test_an_external_bucket_flagged_cross_account_is_read_from_prod_through_the_role_in_dev():
    location = Location(bucket=ExternalBucket(prod="the-prod-bucket", dev_via_cross_account=True), prefix="files/")

    assert resolve(location, DEV) == ResolvedLocation("the-prod-bucket", "files/", True, False)


def test_a_bucket_name_is_never_derived_for_an_external_bucket():
    location = Location(bucket=ExternalBucket(prod="the-prod-bucket", dev_via_cross_account=True))

    for environment in (DEV, PROD):
        assert resolve(location, environment).bucket == "the-prod-bucket"


# --- SourceDefinition ---


def _source(**overrides) -> SourceDefinition:
    values = {
        "description": "A test source",
        "document_type": DocumentType.BUSINESS_CASE,
        "location": Location(bucket=Bucket.REPORTS),
        "graph": True,
    }
    return SourceDefinition(**{**values, **overrides})


def test_a_source_can_feed_only_the_graph():
    assert _source(graph=True).knowledge_base is None


def test_a_source_can_feed_only_a_knowledge_base():
    source = _source(graph=False, knowledge_base=KnowledgeBaseSettings())

    assert source.graph is False


def test_a_source_can_feed_both():
    source = _source(graph=True, knowledge_base=KnowledgeBaseSettings())

    assert source.graph and source.knowledge_base is not None


def test_a_source_must_feed_a_pipeline():
    with pytest.raises(ValidationError, match="graph, a knowledge base, or both"):
        _source(graph=False, knowledge_base=None)


def test_a_source_carries_the_common_metadata_keys_plus_its_own():
    source = _source(extra_metadata_keys=("spend_id",))

    assert source.metadata_keys == (*COMMON_METADATA_KEYS, "spend_id")


# --- the table ---


def test_the_keys_are_snake_case():
    for key in SOURCES:
        assert key == key.lower()
        assert "-" not in key


def test_every_source_feeds_a_pipeline():
    for key, source in SOURCES.items():
        assert source.graph or source.knowledge_base is not None, key


def test_every_source_resolves_in_both_phases():
    for key, source in SOURCES.items():
        for environment in (DEV, PROD):
            assert resolve(source.location, environment).bucket, f"{key} in {environment.short_name}"


def test_the_graph_sources_are_gats_business_cases_for_now():
    assert list(graph_sources()) == ["gats_business_cases"]


def test_gats_is_read_through_the_cross_account_role_in_dev_and_directly_in_prod():
    gats = SOURCES["gats_business_cases"].location

    assert resolve(gats, DEV).cross_account is True
    assert resolve(gats, PROD).cross_account is False
    assert resolve(gats, DEV).bucket == resolve(gats, PROD).bucket


def test_only_the_dbr_knowledge_bases_are_deployed():
    deployed = sorted(key for key, s in SOURCES.items() if s.knowledge_base and s.knowledge_base.deployed)

    assert deployed == ["dbr_readouts_letter", "dbr_reports"]


def test_every_source_except_gats_is_in_a_bucket_we_own():
    external = [key for key, s in SOURCES.items() if isinstance(s.location.bucket, ExternalBucket)]

    assert external == ["gats_business_cases"]


def test_the_two_dbr_sources_share_a_bucket_with_different_prefixes():
    readouts, reports = SOURCES["dbr_readouts_letter"].location, SOURCES["dbr_reports"].location

    assert readouts.bucket == reports.bucket == Bucket.DBR_REPORTS
    assert readouts.prefix != reports.prefix


def test_the_declarations_contain_no_account_ids():
    text = json.dumps({key: s.model_dump(mode="json") for key, s in SOURCES.items()})

    assert DEV.value not in text
    assert PROD.value not in text


def test_document_types_match_the_agents_filters():
    assert SOURCES["sr25_bids"].document_type == DocumentType.SR_BIDS_2025
    assert SOURCES["sr21_bids"].document_type == DocumentType.SR_BIDS_2021
