"""MCP tool: Bedrock Knowledge Base search."""

import json
from typing import Any

from dia.agent.config import settings
from dia.clients.session import get_session


def _kb_retrieve(kb_id: str, query: str, top_k: int = 10, filter_config: dict | None = None) -> str:
    """Internal helper to retrieve from a specific knowledge base."""
    client = get_session().client("bedrock-agent-runtime", region_name=settings.aws_region)
    retrieval_config: dict[str, Any] = {"vectorSearchConfiguration": {"numberOfResults": top_k}}
    if filter_config:
        retrieval_config["vectorSearchConfiguration"]["filter"] = filter_config
    response = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration=retrieval_config,
    )

    results = []
    for r in response["retrievalResults"]:
        results.append(
            {
                "text": r["content"]["text"],
                "score": r["score"],
                "source": r["location"]["s3Location"]["uri"],
            }
        )
    return json.dumps(results, indent=2)


def kb_search_gats_business_cases(query: str, top_k: int = 10) -> str:
    """
    Search the GATS Business Cases knowledge base.
    Contains OBCs, FBCs, and programme cases submitted through spend controls.

    Use for: finding specific business cases, understanding project rationale,
    benefits cases, delivery plans, and risk assessments.

    Args:
        query: Natural language search (e.g. 'cloud migration benefits', 'identity verification risks')
        top_k: Number of passages to return (default 10)
    """
    kb_id = settings.kb_arns["gats_business_cases"]
    if not kb_id:
        return "Error: KB_GATS_BUSINESS_CASES not configured"
    return _kb_retrieve(kb_id, query, top_k)


def kb_search_sr25_bids(query: str, top_k: int = 10) -> str:
    """
    Search the SR25 Spending Review Bids knowledge base.
    Contains 2025 spending review submissions from government departments.

    Use for: departmental funding requests, RDEL/CDEL breakdowns, policy priorities,
    workforce plans, and transformation programmes for the current spending period.

    Args:
        query: Natural language search (e.g. 'digital transformation funding', 'AI investment')
        top_k: Number of passages to return (default 10)
    """
    kb_id = settings.kb_arns["sr25_bids"]
    if not kb_id:
        return "Error: KB_SR25_BIDS not configured"
    return _kb_retrieve(kb_id, query, top_k)


def kb_search_sr21_bids(query: str, top_k: int = 10) -> str:
    """
    Search the SR21 Spending Review Bids knowledge base.
    Contains 2021 spending review submissions from government departments.

    Use for: historical spending commitments, comparing SR21 vs SR25 priorities,
    tracking delivery against previous funding settlements.

    Args:
        query: Natural language search (e.g. 'legacy IT replacement', 'data platform investment')
        top_k: Number of passages to return (default 10)
    """
    kb_id = settings.kb_arns["sr21_bids"]
    if not kb_id:
        return "Error: KB_SR21_BIDS not configured"
    return _kb_retrieve(kb_id, query, top_k)


def kb_search_nao_reports(query: str, top_k: int = 10) -> str:
    """
    Search the NAO Reports knowledge base.
    Contains National Audit Office reports, PAC findings, and value-for-money assessments.

    Use for: audit findings, programme failures, lessons learned, accountability
    concerns, and value-for-money judgements on government programmes.

    Args:
        query: Natural language search (e.g. 'programme delays', 'cost overruns digital')
        top_k: Number of passages to return (default 10)
    """
    kb_id = settings.kb_arns["nao_reports"]
    if not kb_id:
        return "Error: KB_NAO_REPORTS not configured"
    return _kb_retrieve(kb_id, query, top_k)


def kb_search_efficiency_reports(query: str, top_k: int = 10) -> str:
    """
    Search the Interim Efficiencies Reports knowledge base.
    Contains per-department interim efficiencies reports produced as a follow-up
    to the SR25 spending review bids.

    Use for: where a department plans to focus its efficiency savings, the size and
    profile of those savings, and its intended priorities and plans for the upcoming
    SR27 spending review bids.

    Args:
        query: Natural language search (e.g. 'workforce efficiency savings', 'SR27 investment plans')
        top_k: Number of passages to return (default 10)
    """
    kb_id = settings.kb_arns["efficiency_reports"]
    if not kb_id:
        return "Error: KB_EFFICIENCY_REPORTS not configured"
    return _kb_retrieve(kb_id, query, top_k)


def register(mcp_server) -> None:
    """Register all knowledge-base search tools onto an already-built MCP server."""
    mcp_server.tool()(kb_search_gats_business_cases)
    mcp_server.tool()(kb_search_sr25_bids)
    mcp_server.tool()(kb_search_sr21_bids)
    mcp_server.tool()(kb_search_nao_reports)
    mcp_server.tool()(kb_search_efficiency_reports)
