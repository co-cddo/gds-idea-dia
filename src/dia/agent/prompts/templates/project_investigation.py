from __future__ import annotations

from dia.agent.prompts.fragments import (
    ATHENA_SCHEMA_REFERENCE,
    COMMON_CITATION_RULES,
    COMMON_INVESTIGATION_METHODOLOGY,
    COMMON_OUTPUT_RULES,
    COMMON_RULES,
    COMMON_TOOL_REFERENCE,
    COMMON_TOOLS_AND_SOURCES,
    GRAPH_MODES_REFERENCE,
    GRAPH_TIMEOUT_GUARD,
    PROJECT_ATHENA_QUERIES,
    PROJECT_CYPHER_TEMPLATES,
    PROJECT_GRAPH_QUERIES,
    PROJECT_INVESTIGATION_METHOD,
    PROJECT_KB_QUERIES,
    PROJECT_OUTPUT_CARD,
    PROJECT_OUTPUT_SPEC,
    SOURCE_DIAGNOSTICS,
    SQL_HARD_RULES,
    hard_gates,
)
from dia.agent.prompts.fragments.utils import block, join_sections


def get_project_investigation_system_prompt() -> str:
    return join_sections(
        GRAPH_TIMEOUT_GUARD,
        "<system_prompt>",
        block(
            "role_and_objective",
            """
            You are a project intelligence investigator. Given a project or programme name,
            you exhaustively search every available data source to build the complete picture
            of how that project exists across government systems. You trace every connection:
            spend controls, business cases, SR bids, contracts, GMPP data, and the knowledge graph.

            Your output has two parts:
            1. A structured intelligence summary showing everything found about the project
               across sources.
            2. A Neptune openCypher query that can be run to visualise the project's nodes
               and relationships in the graph.

            Search variations of the name, partial matches, and related entities. A project
            may appear under slightly different names across sources.
            """,
        ),
        COMMON_RULES,
        COMMON_TOOL_REFERENCE,
        COMMON_TOOLS_AND_SOURCES,
        GRAPH_MODES_REFERENCE,
        ATHENA_SCHEMA_REFERENCE,
        COMMON_INVESTIGATION_METHODOLOGY,
        PROJECT_INVESTIGATION_METHOD,
        PROJECT_GRAPH_QUERIES,
        PROJECT_KB_QUERIES,
        PROJECT_ATHENA_QUERIES,
        SQL_HARD_RULES,
        COMMON_OUTPUT_RULES,
        PROJECT_OUTPUT_SPEC,
        PROJECT_OUTPUT_CARD,
        PROJECT_CYPHER_TEMPLATES,
        SOURCE_DIAGNOSTICS,
        COMMON_CITATION_RULES,
        hard_gates(
            min_graph_calls=3,
            min_kb_calls=2,
            min_athena_calls=2,
            extra_rules=[
                "Search for the project name AND reasonable variations (abbreviations, full names, acronyms).",
                "If nothing found under one name, try broader searches (department + capability area).",
                "Always report which sources returned NO results — absence of evidence is itself intelligence.",
                'If a source returns nothing, say "Not found in [source]".',
                "The Cypher query MUST be syntactically valid openCypher for Neptune.",
                "Athena and KB queries CAN run in parallel with each other (graph queries cannot).",
            ],
        ),
        "</system_prompt>",
    )
