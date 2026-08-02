"""Smoke + unit tests for dia.agent.prompts — system prompt templates and fragment helpers."""

from dia.agent.prompts.fragments.common_rules import hard_gates
from dia.agent.prompts.fragments.output_specs import dbr_output_card
from dia.agent.prompts.fragments.tools_and_sources import department_matching_rules
from dia.agent.prompts.fragments.utils import block, bullet_list, clean, join_sections
from dia.agent.prompts.templates import (
    get_ai_transformation_system_prompt,
    get_ai_transformation_system_prompt_v2,
    get_dbr_system_prompt,
    get_default_system_prompt,
    get_gats_query_system_prompt,
    get_graph_cost_aware_system_prompt,
    get_pitch_deck_system_prompt,
    get_project_investigation_system_prompt,
    get_sovereign_stack_system_prompt_v3,
    get_supplier_ecosystem_system_prompt,
    get_supplier_lockin_system_prompt,
    get_targeted_question_system_prompt,
)

# --- template factories: smoke tests (importability + non-empty output) ---
#
# This exact category of test (import + call, assert non-empty) would have
# caught the broken `from prompts.X import ...` import bug found and fixed
# earlier — every prompts/templates/*.py and prompts/fragments/*.py file used
# the wrong absolute import path.

_NO_ARG_FACTORIES = [
    get_gats_query_system_prompt,
    get_graph_cost_aware_system_prompt,
    get_pitch_deck_system_prompt,
    get_project_investigation_system_prompt,
    get_sovereign_stack_system_prompt_v3,
    get_targeted_question_system_prompt,
]

_DEPARTMENT_ARG_FACTORIES = [
    get_ai_transformation_system_prompt,
    get_ai_transformation_system_prompt_v2,
    get_dbr_system_prompt,
    get_default_system_prompt,
]

_OPTIONAL_DEPARTMENT_ARG_FACTORIES = [
    get_supplier_ecosystem_system_prompt,
    get_supplier_lockin_system_prompt,
]


def test_all_no_arg_factories_return_non_empty_strings():
    for factory in _NO_ARG_FACTORIES:
        result = factory()
        assert isinstance(result, str)
        assert len(result) > 0


def test_all_department_arg_factories_return_non_empty_strings():
    for factory in _DEPARTMENT_ARG_FACTORIES:
        result = factory("Home Office")
        assert isinstance(result, str)
        assert len(result) > 0


def test_all_optional_department_arg_factories_work_without_args():
    for factory in _OPTIONAL_DEPARTMENT_ARG_FACTORIES:
        result = factory()
        assert isinstance(result, str)
        assert len(result) > 0


def test_default_system_prompt_embeds_department_name():
    result = get_default_system_prompt("DWP")
    assert "DWP" in result


def test_dbr_system_prompt_embeds_department_name():
    result = get_dbr_system_prompt("HMRC")
    assert "HMRC" in result


def test_default_system_prompt_uses_default_department_when_not_given():
    result = get_default_system_prompt()
    assert "Home Office" in result


def test_supplier_lockin_system_prompt_works_with_empty_department():
    result = get_supplier_lockin_system_prompt()
    assert isinstance(result, str)
    assert len(result) > 0


def test_default_system_prompt_contains_expected_structural_markers():
    """Sanity check that the prompt is actually assembled from its fragments,
    not just returning some placeholder string."""
    result = get_default_system_prompt("Home Office")
    assert "<system_prompt>" in result
    assert "</system_prompt>" in result


# --- fragments/utils.py: pure string helpers ---


def test_clean_dedents_and_strips():
    text = """
        line one
        line two
    """
    assert clean(text) == "line one\nline two"


def test_block_wraps_in_named_tags():
    result = block("my_section", "some body text")
    assert result == "<my_section>\nsome body text\n</my_section>"


def test_block_dedents_body_content():
    result = block("section", "    indented text\n    more text")
    assert "<section>" in result
    assert "indented text" in result


def test_join_sections_joins_with_blank_lines():
    result = join_sections("first", "second", "third")
    assert result == "first\n\nsecond\n\nthird"


def test_join_sections_skips_none_and_empty_sections():
    result = join_sections("first", None, "", "   ", "second")
    assert result == "first\n\nsecond"


def test_bullet_list_formats_each_item_with_dash():
    result = bullet_list(["one", "two", "three"])
    assert result == "- one\n- two\n- three"


def test_bullet_list_handles_empty_iterable():
    assert bullet_list([]) == ""


# --- fragments/common_rules.py: hard_gates ---


def test_hard_gates_returns_empty_string_when_no_fields_set():
    assert hard_gates() == ""


def test_hard_gates_includes_min_words_rule():
    result = hard_gates(min_words=2000)
    assert "2,000 words" in result


def test_hard_gates_includes_min_graph_calls_rule():
    result = hard_gates(min_graph_calls=5)
    assert "Minimum 5 `default_` graph queries" in result


def test_hard_gates_includes_first_n_must_be_graph_rule():
    result = hard_gates(first_n_must_be_graph=4)
    assert "FIRST 4 tool calls MUST be" in result


def test_hard_gates_includes_min_web_calls_rule():
    result = hard_gates(min_web_calls=1)
    assert "Minimum 1 `web_search_gov` calls." in result


def test_hard_gates_includes_extra_rules():
    result = hard_gates(min_words=100, extra_rules=["Custom rule one.", "Custom rule two."])
    assert "Custom rule one." in result
    assert "Custom rule two." in result


def test_hard_gates_wraps_output_in_hard_gates_block():
    result = hard_gates(min_words=100)
    assert result.startswith("<hard_gates>")
    assert result.endswith("</hard_gates>")


# --- fragments/tools_and_sources.py: department_matching_rules ---


def test_department_matching_rules_mentions_home_office():
    result = department_matching_rules()
    assert "Home Office" in result


def test_department_matching_rules_never_uses_exact_equality():
    result = department_matching_rules()
    assert "Never use exact equality" in result


# --- fragments/output_specs.py: dbr_output_card ---


def test_dbr_output_card_embeds_uppercased_department_name():
    result = dbr_output_card("Home Office")
    assert "HOME OFFICE" in result


def test_dbr_output_card_default_department():
    result = dbr_output_card()
    assert "HOME OFFICE" in result
