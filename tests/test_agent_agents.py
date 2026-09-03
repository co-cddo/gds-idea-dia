"""Tests for dia.agent.agents — make_model() and the per-prompt agent factories.

make_model() is pure branching logic (which Bedrock models need adaptive vs.
manual thinking config) with no AWS/Strands side effects at construction time.

The make_*_agent() factories are tested only for plumbing: that each one calls
the shared make_agent() helper with a non-empty prompt string, built without
raising (this is what would have caught the missing get_default_system_prompt
import). make_agent()'s internals (real MCPClient/Strands Agent construction)
are deliberately not tested here — that needs a running MCP server / AWS.
"""

from unittest.mock import patch

import pytest

from dia.agent.agents import (
    make_ai_transformation_agent,
    make_ai_transformation_agent_v2,
    make_dbr_agent,
    make_default_agent,
    make_gats_query_agent,
    make_graph_cost_aware_agent,
    make_model,
    make_pitch_deck_agent,
    make_project_investigation_agent,
    make_sovereign_stack_agent,
    make_supplier_ecosystem_agent,
    make_supplier_lockin_agent,
    make_targeted_question_agent,
)


def test_manual_thinking_model_gets_enabled_type_and_budget_tokens():
    model = make_model(model_id="eu.anthropic.claude-sonnet-4-6", thinking_budget_tokens=4096)
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"] == {"type": "enabled", "budget_tokens": 4096}


def test_manual_thinking_model_includes_temperature():
    model = make_model(model_id="eu.anthropic.claude-sonnet-4-6", temperature=0.5)
    config = model.get_config()

    assert config["additional_request_fields"]["temperature"] == 0.5


def test_adaptive_thinking_model_gets_adaptive_type_and_effort():
    model = make_model(model_id="global.anthropic.claude-sonnet-5", effort="high")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["type"] == "adaptive"
    assert config["additional_request_fields"]["output_config"] == {"effort": "high"}


def test_adaptive_thinking_model_omits_temperature():
    model = make_model(model_id="global.anthropic.claude-sonnet-5")
    config = model.get_config()

    assert "temperature" not in config["additional_request_fields"]


def test_adaptive_thinking_model_sets_display():
    model = make_model(model_id="global.anthropic.claude-sonnet-5", thinking_display="summarized")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["display"] == "summarized"


def test_claude_opus_5_is_treated_as_adaptive():
    model = make_model(model_id="global.anthropic.claude-opus-5")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["type"] == "adaptive"


def test_claude_opus_4_7_is_treated_as_adaptive():
    model = make_model(model_id="eu.anthropic.claude-opus-4-7")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["type"] == "adaptive"


def test_regional_prefix_does_not_prevent_adaptive_detection():
    """Matching is on the model-name portion, so a regional/inference-profile
    prefix (e.g. 'eu.anthropic.') shouldn't stop adaptive models being detected."""
    model = make_model(model_id="eu.anthropic.claude-sonnet-5-20250101-v1:0")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["type"] == "adaptive"


def test_older_claude_4_x_model_is_not_treated_as_adaptive():
    model = make_model(model_id="anthropic.claude-sonnet-4-5-20250929-v1:0")
    config = model.get_config()

    assert config["additional_request_fields"]["thinking"]["type"] == "enabled"


def test_max_tokens_passed_through():
    model = make_model(model_id="eu.anthropic.claude-sonnet-4-6", max_tokens=5000)
    config = model.get_config()

    assert config["max_tokens"] == 5000


def test_uses_settings_model_id_by_default():
    from dia.agent.config import settings

    model = make_model()
    config = model.get_config()

    assert config["model_id"] == settings.model_id


# --- make_*_agent() factories (plumbing only) ---

_FACTORIES_WITH_DEPARTMENT = [
    make_default_agent,
    make_dbr_agent,
    make_supplier_lockin_agent,
    make_supplier_ecosystem_agent,
    make_ai_transformation_agent,
    make_ai_transformation_agent_v2,
]

_FACTORIES_WITHOUT_DEPARTMENT = [
    make_gats_query_agent,
    make_project_investigation_agent,
    make_targeted_question_agent,
    make_sovereign_stack_agent,
    make_graph_cost_aware_agent,
    make_pitch_deck_agent,
]


@pytest.mark.parametrize("factory", _FACTORIES_WITH_DEPARTMENT)
def test_department_factory_calls_make_agent_with_nonempty_prompt(factory):
    with patch("dia.agent.agents.make_agent") as mock_make_agent:
        factory("Home Office")

        mock_make_agent.assert_called_once()
        prompt = mock_make_agent.call_args[0][0]
        assert isinstance(prompt, str)
        assert prompt != ""


@pytest.mark.parametrize("factory", _FACTORIES_WITHOUT_DEPARTMENT)
def test_no_department_factory_calls_make_agent_with_nonempty_prompt(factory):
    with patch("dia.agent.agents.make_agent") as mock_make_agent:
        factory()

        mock_make_agent.assert_called_once()
        prompt = mock_make_agent.call_args[0][0]
        assert isinstance(prompt, str)
        assert prompt != ""
