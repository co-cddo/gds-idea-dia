"""Tests for dia.agent.agents.make_model — Bedrock thinking-config branching logic.

Only make_model() is tested here: it's pure branching logic (which Bedrock
models need adaptive vs. manual thinking config) with no AWS/Strands side
effects at construction time, and is likely to survive an eventual A2A
rework of the wiring functions (_make_mcp_client/make_agent/make_default_agent/
make_all_agents), which are deliberately not tested here.
"""

from dia.agent.agents import make_model


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
