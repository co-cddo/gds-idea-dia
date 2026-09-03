"""Tests for dia.agent.config — Settings secret resolution."""

import json
from unittest.mock import patch

from dia.agent.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


# --- _resolve_secret / caching ---


@patch("dia.agent.config.get_secret")
def test_resolve_secret_fetches_value(mock_get_secret):
    mock_get_secret.return_value = "the-value"
    settings = _settings()

    value = settings._resolve_secret("dia-some-secret-dev")

    assert value == "the-value"
    mock_get_secret.assert_called_once_with("dia-some-secret-dev", region=settings.aws_region)


@patch("dia.agent.config.get_secret")
def test_resolve_secret_is_cached_after_first_call(mock_get_secret):
    mock_get_secret.return_value = "the-value"
    settings = _settings()

    settings._resolve_secret("dia-some-secret-dev")
    settings._resolve_secret("dia-some-secret-dev")
    settings._resolve_secret("dia-some-secret-dev")

    mock_get_secret.assert_called_once()


@patch("dia.agent.config.get_secret")
def test_resolve_secret_caches_independently_per_secret_name(mock_get_secret):
    mock_get_secret.side_effect = lambda name, region: f"value-for-{name}"
    settings = _settings()

    a = settings._resolve_secret("secret-a")
    b = settings._resolve_secret("secret-b")

    assert a == "value-for-secret-a"
    assert b == "value-for-secret-b"
    assert mock_get_secret.call_count == 2


@patch("dia.agent.config.get_secret")
def test_resolve_secret_cache_is_per_instance(mock_get_secret):
    """Two separate Settings instances shouldn't share cache state."""
    mock_get_secret.return_value = "value"
    settings_a = _settings()
    settings_b = _settings()

    settings_a._resolve_secret("shared-secret-name")

    assert "shared-secret-name" not in settings_b._secret_cache


# --- kb_arns ---


@patch("dia.agent.config.get_secret")
def test_kb_arns_parses_json_and_strips_kb_prefix(mock_get_secret):
    mock_get_secret.return_value = json.dumps(
        {
            "kb_gats_business_cases": "arn:aws:bedrock:kb-1",
            "kb_sr25_bids": "arn:aws:bedrock:kb-2",
        }
    )
    settings = _settings(kb_arns_secret_name="dia-kb-arns-dev")

    result = settings.kb_arns

    assert result == {
        "gats_business_cases": "arn:aws:bedrock:kb-1",
        "sr25_bids": "arn:aws:bedrock:kb-2",
    }


@patch("dia.agent.config.get_secret")
def test_kb_arns_only_fetches_secret_once_across_multiple_accesses(mock_get_secret):
    mock_get_secret.return_value = json.dumps({"kb_sr25_bids": "arn"})
    settings = _settings(kb_arns_secret_name="dia-kb-arns-dev")

    settings.kb_arns
    settings.kb_arns

    mock_get_secret.assert_called_once()


@patch("dia.agent.config.get_secret")
def test_kb_arns_handles_empty_json_object(mock_get_secret):
    mock_get_secret.return_value = "{}"
    settings = _settings(kb_arns_secret_name="dia-kb-arns-dev")

    assert settings.kb_arns == {}


# --- tavily_api_key ---


@patch("dia.agent.config.get_secret")
def test_tavily_api_key_returns_raw_secret_value(mock_get_secret):
    mock_get_secret.return_value = "tvly-abc123"
    settings = _settings(tavily_secret_name="dia-tavily-dev")

    assert settings.tavily_api_key == "tvly-abc123"


@patch("dia.agent.config.get_secret")
def test_tavily_api_key_uses_shared_resolve_secret_cache(mock_get_secret):
    mock_get_secret.return_value = "tvly-abc123"
    settings = _settings(tavily_secret_name="dia-tavily-dev")

    settings.tavily_api_key
    settings.tavily_api_key

    mock_get_secret.assert_called_once_with("dia-tavily-dev", region=settings.aws_region)


# --- neptune_endpoint / aoss_endpoint ---


@patch("dia.agent.config.get_secret")
def test_neptune_endpoint_returns_raw_secret_value(mock_get_secret):
    mock_get_secret.return_value = "dia-neptune-dev.cluster-xxx.eu-west-2.neptune.amazonaws.com"
    settings = _settings(neptune_endpoint_secret_name="dia-neptune-endpoint-dev")

    assert settings.neptune_endpoint == "dia-neptune-dev.cluster-xxx.eu-west-2.neptune.amazonaws.com"


@patch("dia.agent.config.get_secret")
def test_aoss_endpoint_returns_raw_secret_value(mock_get_secret):
    mock_get_secret.return_value = "abc123.eu-west-2.aoss.amazonaws.com"
    settings = _settings(aoss_endpoint_secret_name="dia-aoss-endpoint-dev")

    assert settings.aoss_endpoint == "abc123.eu-west-2.aoss.amazonaws.com"


# --- defaults (no AWS calls needed) ---


def test_settings_field_defaults():
    settings = Settings()

    assert settings.aws_region == "eu-west-2"
    assert settings.mcp_port == 8000
    assert settings.tavily_secret_name == "dia-tavily-dev"
    assert settings.kb_arns_secret_name == "dia-kb-arns-dev"
    assert settings.neptune_endpoint_secret_name == "dia-neptune-endpoint-dev"
    assert settings.aoss_endpoint_secret_name == "dia-aoss-endpoint-dev"


def test_mcp_url_computed_from_port():
    settings = Settings(mcp_port=9000)

    assert settings.mcp_url == "http://127.0.0.1:9000/mcp/"
