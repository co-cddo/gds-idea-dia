"""Tests for dia.agent.mcp.tools.web_search — Tavily GOV.UK web search MCP tool."""

import json
from unittest.mock import MagicMock, PropertyMock, patch

from dia.agent.mcp.tools import web_search


def _patched_tavily_api_key(value: str):
    """tavily_api_key is a @property on Settings — patch it at the class level
    via PropertyMock so accessing it doesn't trigger a real Secrets Manager call."""
    return patch.object(type(web_search.settings), "tavily_api_key", new_callable=PropertyMock, return_value=value)


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_returns_results_as_json(mock_tavily_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": [{"title": "Some result", "url": "https://gov.uk/x"}]}
    mock_tavily_client_cls.return_value = mock_client

    with _patched_tavily_api_key("tvly-abc123"):
        result = web_search.web_search_gov("digital strategy")

    parsed = json.loads(result)
    assert parsed == [{"title": "Some result", "url": "https://gov.uk/x"}]


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_scopes_query_to_gov_uk_publications(mock_tavily_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    mock_tavily_client_cls.return_value = mock_client

    with _patched_tavily_api_key("tvly-abc123"):
        web_search.web_search_gov("Home Office digital strategy")

    _, kwargs = mock_client.search.call_args
    assert kwargs["query"] == "Home Office digital strategy site:gov.uk/government/publications"
    assert kwargs["include_domains"] == ["www.gov.uk"]


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_passes_max_results(mock_tavily_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    mock_tavily_client_cls.return_value = mock_client

    with _patched_tavily_api_key("tvly-abc123"):
        web_search.web_search_gov("query", max_results=3)

    _, kwargs = mock_client.search.call_args
    assert kwargs["max_results"] == 3


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_uses_resolved_api_key(mock_tavily_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {"results": []}
    mock_tavily_client_cls.return_value = mock_client

    with _patched_tavily_api_key("tvly-real-key"):
        web_search.web_search_gov("query")

    mock_tavily_client_cls.assert_called_once_with(api_key="tvly-real-key")


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_returns_error_string_on_exception(mock_tavily_client_cls):
    mock_tavily_client_cls.side_effect = Exception("bad api key")

    with _patched_tavily_api_key("tvly-bad-key"):
        result = web_search.web_search_gov("query")

    assert result == "Search error: bad api key"


@patch("dia.agent.mcp.tools.web_search.TavilyClient")
def test_web_search_gov_defaults_results_key_to_empty_list(mock_tavily_client_cls):
    mock_client = MagicMock()
    mock_client.search.return_value = {}  # no "results" key at all
    mock_tavily_client_cls.return_value = mock_client

    with _patched_tavily_api_key("tvly-abc123"):
        result = web_search.web_search_gov("query")

    assert json.loads(result) == []


# --- register ---


def test_register_attaches_web_search_gov_to_server():
    mock_server = MagicMock()
    mock_tool_decorator = MagicMock()
    mock_server.tool.return_value = mock_tool_decorator

    web_search.register(mock_server)

    mock_server.tool.assert_called_once()
    mock_tool_decorator.assert_called_once_with(web_search.web_search_gov)
