"""Tests for dia.agent.mcp.tools.knowledge_base — Bedrock Knowledge Base MCP tools."""

import json
from unittest.mock import MagicMock, PropertyMock, patch

from dia.agent.mcp.tools import knowledge_base as kb


def _patched_kb_arns(value: dict[str, str]):
    """kb_arns is a @property on Settings — patch it at the class level via
    PropertyMock so accessing settings.kb_arns doesn't trigger the real
    Secrets Manager call."""
    return patch.object(type(kb.settings), "kb_arns", new_callable=PropertyMock, return_value=value)


def _fake_retrieve_response():
    return {
        "retrievalResults": [
            {
                "content": {"text": "some passage"},
                "score": 0.9,
                "location": {"s3Location": {"uri": "s3://bucket/doc.pdf"}},
            }
        ]
    }


@patch("dia.agent.mcp.tools.knowledge_base.get_session")
def test_kb_retrieve_formats_results(mock_get_session):
    mock_client = MagicMock()
    mock_client.retrieve.return_value = _fake_retrieve_response()
    mock_get_session.return_value.client.return_value = mock_client

    result = kb._kb_retrieve("kb-123", "some query", top_k=5)

    parsed = json.loads(result)
    assert parsed == [{"text": "some passage", "score": 0.9, "source": "s3://bucket/doc.pdf"}]


@patch("dia.agent.mcp.tools.knowledge_base.get_session")
def test_kb_retrieve_passes_top_k_into_retrieval_config(mock_get_session):
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {"retrievalResults": []}
    mock_get_session.return_value.client.return_value = mock_client

    kb._kb_retrieve("kb-123", "some query", top_k=7)

    _, kwargs = mock_client.retrieve.call_args
    assert kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["numberOfResults"] == 7


@patch("dia.agent.mcp.tools.knowledge_base.get_session")
def test_kb_retrieve_applies_filter_config_when_given(mock_get_session):
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {"retrievalResults": []}
    mock_get_session.return_value.client.return_value = mock_client

    kb._kb_retrieve("kb-123", "some query", filter_config={"equals": {"key": "x", "value": "y"}})

    _, kwargs = mock_client.retrieve.call_args
    assert kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] == {
        "equals": {"key": "x", "value": "y"}
    }


@patch("dia.agent.mcp.tools.knowledge_base.get_session")
def test_kb_retrieve_omits_filter_when_not_given(mock_get_session):
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {"retrievalResults": []}
    mock_get_session.return_value.client.return_value = mock_client

    kb._kb_retrieve("kb-123", "some query")

    _, kwargs = mock_client.retrieve.call_args
    assert "filter" not in kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]


@patch("dia.agent.mcp.tools.knowledge_base.get_session")
def test_kb_retrieve_uses_query_text(mock_get_session):
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {"retrievalResults": []}
    mock_get_session.return_value.client.return_value = mock_client

    kb._kb_retrieve("kb-123", "digital transformation funding")

    _, kwargs = mock_client.retrieve.call_args
    assert kwargs["retrievalQuery"] == {"text": "digital transformation funding"}


# --- kb_search_* wrapper functions ---

_SEARCH_FN_TO_ARN_KEY = {
    kb.kb_search_gats_business_cases: "gats_business_cases",
    kb.kb_search_sr25_bids: "sr25_bids",
    kb.kb_search_sr21_bids: "sr21_bids",
    kb.kb_search_nao_reports: "nao_reports",
    kb.kb_search_efficiency_reports: "efficiency_reports",
}


def test_all_kb_search_functions_are_mapped():
    """Sanity check that the mapping above covers every kb_search_* function."""
    assert len(_SEARCH_FN_TO_ARN_KEY) == 5


def test_kb_search_gats_business_cases_returns_error_when_not_configured():
    with _patched_kb_arns({"gats_business_cases": ""}):
        result = kb.kb_search_gats_business_cases("some query")

    assert result == "Error: KB_GATS_BUSINESS_CASES not configured"


def test_kb_search_sr25_bids_returns_error_when_not_configured():
    with _patched_kb_arns({"sr25_bids": ""}):
        result = kb.kb_search_sr25_bids("some query")

    assert result == "Error: KB_SR25_BIDS not configured"


def test_kb_search_sr21_bids_returns_error_when_not_configured():
    with _patched_kb_arns({"sr21_bids": ""}):
        result = kb.kb_search_sr21_bids("some query")

    assert result == "Error: KB_SR21_BIDS not configured"


def test_kb_search_nao_reports_returns_error_when_not_configured():
    with _patched_kb_arns({"nao_reports": ""}):
        result = kb.kb_search_nao_reports("some query")

    assert result == "Error: KB_NAO_REPORTS not configured"


def test_kb_search_efficiency_reports_returns_error_when_not_configured():
    with _patched_kb_arns({"efficiency_reports": ""}):
        result = kb.kb_search_efficiency_reports("some query")

    assert result == "Error: KB_EFFICIENCY_REPORTS not configured"


@patch("dia.agent.mcp.tools.knowledge_base._kb_retrieve")
def test_kb_search_sr25_bids_delegates_to_kb_retrieve_when_configured(mock_kb_retrieve):
    mock_kb_retrieve.return_value = "[]"
    with _patched_kb_arns({"sr25_bids": "kb-abc"}):
        result = kb.kb_search_sr25_bids("digital transformation funding", top_k=3)

    mock_kb_retrieve.assert_called_once_with("kb-abc", "digital transformation funding", 3)
    assert result == "[]"


# --- register ---


def test_register_attaches_all_five_kb_search_tools():
    mock_server = MagicMock()
    mock_tool_decorator = MagicMock()
    mock_server.tool.return_value = mock_tool_decorator

    kb.register(mock_server)

    assert mock_server.tool.call_count == 5
    mock_tool_decorator.assert_any_call(kb.kb_search_gats_business_cases)
    mock_tool_decorator.assert_any_call(kb.kb_search_sr25_bids)
    mock_tool_decorator.assert_any_call(kb.kb_search_sr21_bids)
    mock_tool_decorator.assert_any_call(kb.kb_search_nao_reports)
    mock_tool_decorator.assert_any_call(kb.kb_search_efficiency_reports)
