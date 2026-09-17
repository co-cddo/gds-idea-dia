"""Tests for dia.agent.mcp.retrieval_modes — mode/entity_name -> filter/throttle translation."""

import pytest
from graphrag_toolkit.lexical_graph.metadata import FilterConfig
from graphrag_toolkit.lexical_graph.retrieval.retrievers import ChunkBasedSearch
from llama_index.core.vector_stores.types import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)

from dia.agent.mcp.retrieval_modes import (
    _ALL_RETRIEVERS,
    _SUPER_THROTTLE_KWARGS,
    _THROTTLE_KWARGS,
    _make_filter_eq_and,
    update_tool_params,
)

# --- _make_filter_eq_and ---


def test_make_filter_eq_and_uses_text_match_for_document_type():
    fc = _make_filter_eq_and(("document_type", "business_case"))
    expected = FilterConfig(
        MetadataFilters(
            filters=[MetadataFilter(key="document_type", value="business_case", operator=FilterOperator.TEXT_MATCH)],
            condition=FilterCondition.AND,
        )
    )
    assert fc == expected


def test_make_filter_eq_and_uses_text_match_for_contract_name():
    fc = _make_filter_eq_and(("contract_name", "Some Project"))
    assert fc.source_filters.filters[0].operator == FilterOperator.TEXT_MATCH


def test_make_filter_eq_and_uses_eq_for_other_keys():
    fc = _make_filter_eq_and(("department", "DWP"), ("alb", "Some ALB"))
    assert fc.source_filters.filters[0].operator == FilterOperator.EQ
    assert fc.source_filters.filters[1].operator == FilterOperator.EQ


def test_make_filter_eq_and_condition_is_and():
    fc = _make_filter_eq_and(("department", "DWP"))
    assert fc.source_filters.condition == FilterCondition.AND


def test_make_filter_eq_and_preserves_pair_order():
    fc = _make_filter_eq_and(("document_type", "business_case"), ("department", "DWP"))
    keys = [f.key for f in fc.source_filters.filters]
    assert keys == ["document_type", "department"]


# --- update_tool_params: basic contract ---


def test_update_tool_params_returns_none():
    kwargs = {}
    result = update_tool_params({"mode": "default"}, kwargs)
    assert result is None


def test_update_tool_params_always_sets_retrievers_to_all():
    kwargs = {}
    update_tool_params({"mode": "default"}, kwargs)
    assert kwargs["retrievers"] == _ALL_RETRIEVERS


def test_update_tool_params_missing_mode_key_defaults_to_default():
    kwargs = {}
    update_tool_params({}, kwargs)
    assert kwargs["intermediate_limit"] == 24
    assert "filter_config" not in kwargs


def test_update_tool_params_missing_entity_name_key_defaults_to_empty():
    kwargs = {}
    # business_case_all doesn't need entity_name, so this should not raise
    update_tool_params({"mode": "business_case_all"}, kwargs)
    assert "filter_config" in kwargs


def test_update_tool_params_mode_is_case_insensitive_and_stripped():
    kwargs = {}
    update_tool_params({"mode": "  Business_Case_All  "}, kwargs)
    assert "filter_config" in kwargs


def test_update_tool_params_entity_name_is_stripped():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_business_case_department", "entity_name": "  DWP  "}, kwargs)
    assert kwargs["filter_config"].source_filters.filters[1].value == "DWP"


# --- default mode ---


def test_default_mode_sets_intermediate_limit():
    kwargs = {}
    update_tool_params({"mode": "default"}, kwargs)
    assert kwargs["intermediate_limit"] == 24


def test_default_mode_sets_no_filter_config():
    kwargs = {}
    update_tool_params({"mode": "default"}, kwargs)
    assert "filter_config" not in kwargs


# --- modes requiring entity_name: raise when missing ---

_ENTITY_REQUIRED_MODES = [
    "metadata_filtered_business_case_department",
    "metadata_filtered_business_case_alb",
    "metadata_filtered_sr_bids_department",
    "metadata_filtered_sr_bids_alb",
    "metadata_filtered_contract_finder_department",
    "search_by_project",
    "department_all_sources",
]


@pytest.mark.parametrize("mode", _ENTITY_REQUIRED_MODES)
def test_modes_requiring_entity_name_raise_when_missing(mode):
    with pytest.raises(ValueError, match="entity_name required"):
        update_tool_params({"mode": mode}, {})


@pytest.mark.parametrize("mode", _ENTITY_REQUIRED_MODES)
def test_modes_requiring_entity_name_raise_when_blank(mode):
    with pytest.raises(ValueError, match="entity_name required"):
        update_tool_params({"mode": mode, "entity_name": "   "}, {})


def test_retrievers_key_is_set_before_the_raise():
    """query_engine_kwargs["retrievers"] is set unconditionally before the mode
    branch runs, so it's already mutated into the dict even if a ValueError is
    raised afterward for a missing entity_name."""
    kwargs = {}
    with pytest.raises(ValueError):
        update_tool_params({"mode": "search_by_project"}, kwargs)
    assert kwargs["retrievers"] == _ALL_RETRIEVERS


# --- modes requiring entity_name: filter_config built correctly ---


def test_metadata_filtered_business_case_department():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_business_case_department", "entity_name": "DWP"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "business_case"), ("department", "DWP"))
    assert kwargs["filter_config"] == expected


def test_metadata_filtered_business_case_alb():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_business_case_alb", "entity_name": "Some ALB"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "business_case"), ("alb", "Some ALB"))
    assert kwargs["filter_config"] == expected


def test_metadata_filtered_sr_bids_department():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_sr_bids_department", "entity_name": "DWP"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "sr_bids_2025"), ("department_name", "DWP"))
    assert kwargs["filter_config"] == expected


def test_metadata_filtered_sr_bids_alb():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_sr_bids_alb", "entity_name": "Some ALB"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "sr_bids_2025"), ("alb", "Some ALB"))
    assert kwargs["filter_config"] == expected


def test_metadata_filtered_contract_finder_department():
    kwargs = {}
    update_tool_params({"mode": "metadata_filtered_contract_finder_department", "entity_name": "DWP"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "contract_finder"), ("department_name", "DWP"))
    assert kwargs["filter_config"] == expected


def test_search_by_project():
    kwargs = {}
    update_tool_params({"mode": "search_by_project", "entity_name": "Some Project"}, kwargs)
    expected = _make_filter_eq_and(("document_type", "contract_finder"), ("contract_name", "Some Project"))
    assert kwargs["filter_config"] == expected


def test_department_all_sources_uses_or_condition():
    kwargs = {}
    update_tool_params({"mode": "department_all_sources", "entity_name": "DWP"}, kwargs)
    filter_config = kwargs["filter_config"]
    assert filter_config.source_filters.condition == FilterCondition.OR
    keys = {f.key for f in filter_config.source_filters.filters}
    assert keys == {"department", "department_name"}
    for f in filter_config.source_filters.filters:
        assert f.value == "DWP"
        assert f.operator == FilterOperator.EQ


# --- unfiltered "_all" modes ---


def test_business_case_all_sets_single_text_match_filter():
    kwargs = {}
    update_tool_params({"mode": "business_case_all"}, kwargs)
    fc = kwargs["filter_config"]
    single_filter = fc.source_filters.filters[0]
    assert single_filter.key == "document_type"
    assert single_filter.value == "business_case"
    assert single_filter.operator == FilterOperator.TEXT_MATCH


def test_sr_bids_all_sets_single_text_match_filter():
    kwargs = {}
    update_tool_params({"mode": "sr_bids_all"}, kwargs)
    fc = kwargs["filter_config"]
    assert fc.source_filters.filters[0].value == "sr_bids_2025"


def test_contract_finder_all_sets_single_text_match_filter():
    kwargs = {}
    update_tool_params({"mode": "contract_finder_all"}, kwargs)
    fc = kwargs["filter_config"]
    assert fc.source_filters.filters[0].value == "contract_finder"


# --- unrecognized mode: silent fallback to default (documents current behavior) ---


def test_unrecognized_mode_silently_falls_back_to_default():
    """No validation against the allowed-modes list exists today: a typo'd or
    unknown mode string is silently treated as 'default' rather than raising.
    This test documents the current behavior."""
    kwargs = {}
    update_tool_params({"mode": "totally_bogus_mode"}, kwargs)
    assert kwargs["intermediate_limit"] == 24
    assert "filter_config" not in kwargs


# --- throttle suffix parsing ---


def test_throttled_suffix_is_stripped_and_throttle_kwargs_applied():
    kwargs = {}
    update_tool_params({"mode": "default_throttled"}, kwargs)
    assert kwargs["intermediate_limit"] == _THROTTLE_KWARGS["intermediate_limit"]
    assert kwargs["num_workers"] == _THROTTLE_KWARGS["num_workers"]
    assert kwargs["vss_top_k"] == _THROTTLE_KWARGS["vss_top_k"]
    assert kwargs["ec_max_contexts"] == _THROTTLE_KWARGS["ec_max_contexts"]


def test_super_throttled_suffix_is_stripped_and_super_throttle_kwargs_applied():
    kwargs = {}
    update_tool_params({"mode": "default_super_throttled"}, kwargs)
    assert kwargs["retrievers"] == _SUPER_THROTTLE_KWARGS["retrievers"]
    assert kwargs["vss_top_k"] == _SUPER_THROTTLE_KWARGS["vss_top_k"]


def test_super_throttled_overwrites_retrievers_to_vector_only():
    """retrievers is first set to all three retrievers unconditionally, then
    overwritten to ChunkBasedSearch-only for _super_throttled — verify the
    final state reflects the override, not the initial value."""
    kwargs = {}
    update_tool_params({"mode": "default_super_throttled"}, kwargs)
    assert kwargs["retrievers"] == [ChunkBasedSearch]


def test_super_throttled_takes_precedence_over_throttled_suffix_match():
    """A mode ending in '_super_throttled' must not also be matched by the
    '_throttled' suffix check."""
    kwargs = {}
    update_tool_params({"mode": "default_super_throttled"}, kwargs)
    # only super-throttle kwargs applied, not the plain throttle kwargs
    assert kwargs["vss_top_k"] == _SUPER_THROTTLE_KWARGS["vss_top_k"]
    assert "num_workers" not in kwargs


def test_no_suffix_applies_neither_throttle_kwargs():
    kwargs = {}
    update_tool_params({"mode": "default"}, kwargs)
    assert "num_workers" not in kwargs
    assert kwargs["retrievers"] == _ALL_RETRIEVERS


# --- metadata-filtered mode combined with throttle suffix ---


def test_metadata_filtered_mode_with_throttled_suffix_keeps_both_filter_and_throttle():
    kwargs = {}
    update_tool_params(
        {"mode": "metadata_filtered_business_case_department_throttled", "entity_name": "DWP"},
        kwargs,
    )
    expected_filter = _make_filter_eq_and(("document_type", "business_case"), ("department", "DWP"))
    assert kwargs["filter_config"] == expected_filter
    assert kwargs["intermediate_limit"] == _THROTTLE_KWARGS["intermediate_limit"]


def test_metadata_filtered_mode_with_super_throttled_suffix_overwrites_retrievers():
    kwargs = {}
    update_tool_params(
        {"mode": "metadata_filtered_business_case_department_super_throttled", "entity_name": "DWP"},
        kwargs,
    )
    expected_filter = _make_filter_eq_and(("document_type", "business_case"), ("department", "DWP"))
    assert kwargs["filter_config"] == expected_filter
    # even though a metadata-filtered mode was requested, super_throttled still
    # downgrades to vector-only retrieval
    assert kwargs["retrievers"] == [ChunkBasedSearch]


@pytest.mark.parametrize("mode", _ENTITY_REQUIRED_MODES)
def test_entity_required_modes_still_raise_with_throttled_suffix_if_entity_missing(mode):
    with pytest.raises(ValueError, match="entity_name required"):
        update_tool_params({"mode": f"{mode}_throttled"}, {})
