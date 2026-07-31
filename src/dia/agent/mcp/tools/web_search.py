"""MCP tool: gov.uk web search."""

import json

from tavily import TavilyClient

from dia.agent.config import settings


def web_search_gov(query: str, max_results: int = 5) -> str:
    """
    Search GOV.UK publications for relevant government documents.
    Scoped to gov.uk/government/publications — finds published strategies, policy papers,
    guidance documents, annual reports, and official statistics.

    Use for:
    - Finding published strategies or policy papers related to programmes found in the graph
    - Verifying programme status with official publications
    - Cross-referencing internal data with publicly available departmental reports
    - Finding IPA annual reports, digital strategies, and transformation plans

    Args:
        query: Search query (e.g. 'Home Office digital strategy', 'IPA annual report 2024')
        max_results: Number of results (default 5)
    """
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        results = client.search(
            query=f"{query} site:gov.uk/government/publications",
            search_depth="advanced",
            include_domains=["www.gov.uk"],
            max_results=max_results,
        )
        return json.dumps(results.get("results", []), indent=2)
    except Exception as e:
        return f"Search error: {e}"
