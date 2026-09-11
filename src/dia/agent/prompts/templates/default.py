from __future__ import annotations

from dia.agent.config import settings
from dia.agent.prompts.fragments import (
    ATHENA_SCHEMA_REFERENCE,
    COMMON_CITATION_RULES,
    COMMON_INVESTIGATION_METHODOLOGY,
    COMMON_OUTPUT_RULES,
    COMMON_RULES,
    COMMON_TOOL_REFERENCE,
    COMMON_TOOLS_AND_SOURCES,
    DEFAULT_OUTPUT_SPEC,
    GRAPH_MODES_REFERENCE,
    GRAPH_TIMEOUT_GUARD,
    SOURCE_DIAGNOSTICS,
    SQL_HARD_RULES,
    default_required_graph_sequence,
    department_matching_rules,
    hard_gates,
)
from dia.agent.prompts.fragments.utils import block, join_sections


def get_default_system_prompt(department_name: str = "") -> str:
    scope = f"for {department_name}" if department_name else "across central government"
    target = department_name if department_name else "All departments (cross-government)"
    return join_sections(
        GRAPH_TIMEOUT_GUARD,
        "<system_prompt>",
        block(
            "role_and_objective",
            f"""
            You are a Senior Intelligence Analyst preparing a comprehensive Digital Business
            Review briefing {scope}.

            Your job is to piece together fragmented information from multiple classified
            and public sources into a single, deeply detailed intelligence product that a
            CDO or Permanent Secretary could use to understand the department's entire
            digital landscape.

            Be exhaustive. A thin summary is a failure. Output should contain specific
            programme names, Spend IDs, supplier names, contract values, risk scores,
            timeline dates, and cross-references between sources. Think of yourself as an
            investigative analyst building a dossier — every claim must be sourced, every
            connection mapped.

            Target department: {target}
            """,
        ),
        COMMON_RULES,
        COMMON_TOOL_REFERENCE,
        COMMON_TOOLS_AND_SOURCES,
        GRAPH_MODES_REFERENCE,
        department_matching_rules(),
        ATHENA_SCHEMA_REFERENCE,
        COMMON_INVESTIGATION_METHODOLOGY,
        default_required_graph_sequence(department_name),
        SQL_HARD_RULES,
        COMMON_OUTPUT_RULES,
        DEFAULT_OUTPUT_SPEC,
        SOURCE_DIAGNOSTICS,
        COMMON_CITATION_RULES,
        hard_gates(
            min_words=settings.default_persona_min_words,
            min_graph_calls=settings.default_persona_min_graph_calls,
            first_n_must_be_graph=settings.default_persona_first_n_must_be_graph,
            min_web_calls=settings.default_persona_min_web_calls,
            extra_rules=[
                "Prioritise entities that appear across multiple document sources — these are highest confidence.",
                "When data is ambiguous or missing, explicitly state uncertainty.",
                "Do not hallucinate programmes, Spend IDs, or financial figures.",
            ],
        ),
        "</system_prompt>",
    )
