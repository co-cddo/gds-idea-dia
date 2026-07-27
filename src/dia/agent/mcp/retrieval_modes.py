"""Retrieval mode parsing for the default_ MCP tool.

Translates the (mode, entity_name) tool arguments the agent passes at call
time into concrete FilterConfig + retriever/throttle kwargs for the
underlying graphrag-toolkit query engine.

Throttle tiers, applied via a mode suffix:
  default            -> full traversal (intermediate_limit=50)
  *_throttled         -> reduced traversal (retry after first timeout)
  *_super_throttled    -> vector-only, no graph traversal (retry after second timeout)
"""

import logging
from typing import Any

from fastmcp.tools.tool_transform import ArgTransform
from graphrag_toolkit.lexical_graph.metadata import FilterConfig
from graphrag_toolkit.lexical_graph.protocols import ToolParameters
from graphrag_toolkit.lexical_graph.retrieval.retrievers import (
    ChunkBasedSearch,
    EntityBasedSearch,
    EntityContextSearch,
)
from llama_index.core.vector_stores.types import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)

logger = logging.getLogger(__name__)

_ALL_RETRIEVERS = [ChunkBasedSearch, EntityBasedSearch, EntityContextSearch]

_THROTTLE_KWARGS = {
    "intermediate_limit": 8,
    "num_workers": 1,
    "vss_top_k": 3,
    "ec_max_contexts": 1,
}

_SUPER_THROTTLE_KWARGS = {
    "retrievers": [ChunkBasedSearch],
    "vss_top_k": 5,
}


def _make_filter_eq_and(*pairs: tuple[str, str]) -> FilterConfig:
    return FilterConfig(
        MetadataFilters(
            filters=[
                MetadataFilter(
                    key=key,
                    value=value,
                    operator=(
                        FilterOperator.TEXT_MATCH if key in {"document_type", "contract_name"} else FilterOperator.EQ
                    ),
                )
                for key, value in pairs
            ],
            condition=FilterCondition.AND,
        )
    )


def update_tool_params(tool_params: dict[str, Any], query_engine_kwargs: dict[str, Any]) -> None:
    """Translate (mode, entity_name) into FilterConfig + retriever / throttle kwargs."""
    raw_mode = (tool_params.get("mode") or "default").lower().strip()
    entity_name = (tool_params.get("entity_name") or "").strip()

    super_throttle = raw_mode.endswith("_super_throttled")
    if super_throttle:
        mode = raw_mode.removesuffix("_super_throttled")
        throttle = False
    else:
        throttle = raw_mode.endswith("_throttled")
        mode = raw_mode.removesuffix("_throttled") if throttle else raw_mode

    logger.info(
        "Mode: %s | Entity: %s | SuperThrottle: %s | Throttle: %s",
        mode,
        entity_name,
        super_throttle,
        throttle,
    )

    query_engine_kwargs["retrievers"] = _ALL_RETRIEVERS

    if mode == "metadata_filtered_business_case_department":
        if not entity_name:
            raise ValueError("entity_name required for mode='metadata_filtered_business_case_department'")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "business_case"),
            ("department", entity_name),
        )
    elif mode == "metadata_filtered_business_case_alb":
        if not entity_name:
            raise ValueError("entity_name required for mode='metadata_filtered_business_case_alb'")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "business_case"),
            ("alb", entity_name),
        )
    elif mode == "metadata_filtered_sr_bids_department":
        if not entity_name:
            raise ValueError("entity_name required for mode='metadata_filtered_sr_bids_department'")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "sr_bids_2025"),
            ("department_name", entity_name),
        )
    elif mode == "metadata_filtered_sr_bids_alb":
        if not entity_name:
            raise ValueError("entity_name required for mode='metadata_filtered_sr_bids_alb'")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "sr_bids_2025"),
            ("alb", entity_name),
        )
    elif mode == "metadata_filtered_contract_finder_department":
        if not entity_name:
            raise ValueError("entity_name required for mode='metadata_filtered_contract_finder_department'")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "contract_finder"),
            ("department_name", entity_name),
        )
    elif mode == "search_by_project":
        if not entity_name:
            raise ValueError("entity_name required for mode='search_by_project' (provide the project/contract name)")
        query_engine_kwargs["filter_config"] = _make_filter_eq_and(
            ("document_type", "contract_finder"),
            ("contract_name", entity_name),
        )
    elif mode == "department_all_sources":
        if not entity_name:
            raise ValueError("entity_name required for mode='department_all_sources' (provide the department name)")
        query_engine_kwargs["filter_config"] = FilterConfig(
            MetadataFilters(
                filters=[
                    MetadataFilter(
                        key="department",
                        value=entity_name,
                        operator=FilterOperator.EQ,
                    ),
                    MetadataFilter(
                        key="department_name",
                        value=entity_name,
                        operator=FilterOperator.EQ,
                    ),
                ],
                condition=FilterCondition.OR,
            )
        )
    elif mode == "business_case_all":
        query_engine_kwargs["filter_config"] = FilterConfig(
            MetadataFilter(
                key="document_type",
                value="business_case",
                operator=FilterOperator.TEXT_MATCH,
            )
        )
    elif mode == "sr_bids_all":
        query_engine_kwargs["filter_config"] = FilterConfig(
            MetadataFilter(
                key="document_type",
                value="sr_bids_2025",
                operator=FilterOperator.TEXT_MATCH,
            )
        )
    elif mode == "contract_finder_all":
        query_engine_kwargs["filter_config"] = FilterConfig(
            MetadataFilter(
                key="document_type",
                value="contract_finder",
                operator=FilterOperator.TEXT_MATCH,
            )
        )
    else:  # default
        # intermediate_limit caps the candidate entities fed into the graph
        # traversal. High values (50) on hub entities (degree ~4000) blow up
        # the downstream __SUBJECT__/__OBJECT__ filter and time out. 24 keeps
        # recall reasonable while cutting the worst-case cost.
        query_engine_kwargs["intermediate_limit"] = 24

    if super_throttle:
        query_engine_kwargs.update(_SUPER_THROTTLE_KWARGS)
    elif throttle:
        query_engine_kwargs.update(_THROTTLE_KWARGS)


_MODE_DESCRIPTION = (
    "Select the retrieval mode based on the document type and entity.\n\n"
    "Allowed values:\n"
    "- default: Composite search across all document types, no filter.\n"
    "- metadata_filtered_business_case_department: Business Cases for a specific department (requires entity_name).\n"
    "- metadata_filtered_business_case_alb: Business Cases for a specific ALB (requires entity_name).\n"
    "- metadata_filtered_sr_bids_department: SR Bids for a specific department (requires entity_name).\n"
    "- metadata_filtered_sr_bids_alb: SR Bids for a specific ALB (requires entity_name).\n"
    "- metadata_filtered_contract_finder_department: Contract Finder contracts for a specific department "
    "(requires entity_name).\n"
    "- search_by_project: Find a specific project or contract by name in Contract Finder (requires entity_name).\n"
    "- department_all_sources: All documents for a department across Business Cases, SR Bids, and Contract "
    "Finder (requires entity_name).\n"
    "- business_case_all: All Business Case documents, no org filter.\n"
    "- sr_bids_all: All SR Bid documents, no org filter.\n"
    "- contract_finder_all: All Contract Finder documents, no org filter.\n\n"
    "Selection Logic:\n"
    "- Department + business cases -> metadata_filtered_business_case_department.\n"
    "- ALB + business cases -> metadata_filtered_business_case_alb.\n"
    "- Department + SR bids -> metadata_filtered_sr_bids_department.\n"
    "- ALB + SR bids -> metadata_filtered_sr_bids_alb.\n"
    "- Department + contracts -> metadata_filtered_contract_finder_department.\n"
    "- Department across all sources -> department_all_sources.\n"
    "- Specific project/contract name -> search_by_project.\n"
    "- General business cases -> business_case_all.\n"
    "- General SR bids -> sr_bids_all.\n"
    "- General contracts -> contract_finder_all.\n\n"
    "RETRY ESCALATION (append suffix to mode on failure):\n"
    "1. First failure (TimeLimitExceededException) -> call wait_after_timeout(), then append '_throttled'\n"
    "   e.g. 'default_throttled', 'business_case_all_throttled'\n"
    "   Reduces graph traversal depth and node limits.\n"
    "2. Second failure -> call wait_after_timeout(), then append '_super_throttled'\n"
    "   e.g. 'default_super_throttled', 'business_case_all_super_throttled'\n"
    "   Drops to pure vector search — no graph traversal, cannot timeout."
)

_ENTITY_NAME_DESCRIPTION = (
    "The name of the entity to filter by. Meaning depends on mode:\n"
    "- department modes: the department name (maps to 'department' or 'department_name' field).\n"
    "- alb modes: the ALB name (maps to 'alb' field).\n"
    "- search_by_project: the project or contract name (maps to 'contract_name' field).\n"
    "- department_all_sources: the department name, matched across all document types.\n"
    "Leave empty for unfiltered modes (default, *_all).\n"
    "Do NOT guess — only provide if explicitly mentioned in the query."
)

_DEFAULT_TOOL_DESCRIPTION = (
    "Knowledge base containing Business Cases, Spending Review (SR) Bids, and Contract Finder procurement data.\n\n"
    "Data sources:\n"
    "- Business Cases: internal digital spend control business cases.\n"
    "- SR Bids 2025: Spending Review bid documents by department.\n"
    "- Contract Finder: public procurement contracts with supplier and department metadata.\n\n"
    "Capabilities:\n"
    "- Deep graph-based retrieval across entities and relationships.\n"
    "- Filter by document type, department, ALB, or project/contract name.\n\n"
    "How to choose 'mode':\n"
    "1. Department + Business Case -> 'metadata_filtered_business_case_department' + entity_name\n"
    "2. ALB + Business Case -> 'metadata_filtered_business_case_alb' + entity_name\n"
    "3. Department + SR Bid -> 'metadata_filtered_sr_bids_department' + entity_name\n"
    "4. ALB + SR Bid -> 'metadata_filtered_sr_bids_alb' + entity_name\n"
    "5. Department + Contract Finder -> 'metadata_filtered_contract_finder_department' + entity_name\n"
    "6. Department across all sources -> 'department_all_sources' + entity_name\n"
    "7. Specific project/contract -> 'search_by_project' + entity_name\n"
    "8. All Business Cases -> 'business_case_all'\n"
    "9. All SR Bids -> 'sr_bids_all'\n"
    "10. All Contract Finder -> 'contract_finder_all'\n"
    "11. Broad/conceptual sweep -> 'default'\n\n"
    "Retry escalation on TimeLimitExceededException:\n"
    "- Call wait_after_timeout(), then first retry: append '_throttled' (e.g. 'default_throttled')\n"
    "- Call wait_after_timeout(), then second retry: append '_super_throttled' — vector-only, cannot timeout"
)

tool_parameters = ToolParameters(
    parameters=[
        ArgTransform(name="mode", default="default", description=_MODE_DESCRIPTION),
        ArgTransform(name="entity_name", default=None, description=_ENTITY_NAME_DESCRIPTION),
    ],
    update_params_function=update_tool_params,
)
