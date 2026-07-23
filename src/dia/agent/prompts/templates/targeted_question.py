from __future__ import annotations

from prompts.fragments import (
    GRAPH_TIMEOUT_GUARD,
    COMMON_RULES,
    hard_gates,
    COMMON_TOOL_REFERENCE,
    COMMON_TOOLS_AND_SOURCES,
    GRAPH_MODES_REFERENCE,
    ATHENA_SCHEMA_REFERENCE,
    SQL_HARD_RULES,
    COMMON_INVESTIGATION_METHODOLOGY,
    TARGETED_QUESTION_METHOD,
    COMMON_OUTPUT_RULES,
    COMMON_CITATION_RULES,
    TARGETED_QUESTION_OUTPUT_SPEC,
    TARGETED_QUESTION_OUTPUT_CARD,
    TARGETED_QUESTION_SYNONYMS,
    TARGETED_QUESTION_GRAPH_QUERIES,
    TARGETED_QUESTION_ATHENA_QUERIES,
)
from prompts.fragments.utils import block, join_sections


def get_targeted_question_system_prompt() -> str:
    return join_sections(
        GRAPH_TIMEOUT_GUARD,
        "<system_prompt>",
        block(
            "role_and_objective",
            """
            You are an assurance intelligence analyst answering TARGETED questions about
            who across government is doing what. Take a specific question — usually of the
            form "which organisations / departments / programmes are working on
            [CAPABILITY or TOPIC]" — and return a direct, evidence-backed answer.

            You are NOT writing a full Digital Business Review. Answer the question that was
            asked, concisely, with a ranked list of organisations and the evidence behind
            each. Do not pad with unrelated material. Be specific: name the organisation,
            name the programme or contract, give the figure if you have one, and tag the source.
            """,
        ),
        TARGETED_QUESTION_SYNONYMS,
        COMMON_RULES,
        COMMON_TOOL_REFERENCE,
        COMMON_TOOLS_AND_SOURCES,
        GRAPH_MODES_REFERENCE,
        ATHENA_SCHEMA_REFERENCE,
        COMMON_INVESTIGATION_METHODOLOGY,
        TARGETED_QUESTION_METHOD,
        TARGETED_QUESTION_GRAPH_QUERIES,
        TARGETED_QUESTION_ATHENA_QUERIES,
        SQL_HARD_RULES,
        COMMON_OUTPUT_RULES,
        TARGETED_QUESTION_OUTPUT_SPEC,
        TARGETED_QUESTION_OUTPUT_CARD,
        COMMON_CITATION_RULES,
        hard_gates(
            min_graph_calls=2,
            extra_rules=[
                "Answer the question that was asked. Do not produce a full DBR or dossier.",
                "Always search MULTIPLE phrasings / synonyms — a single phrasing misses results.",
                "Never fabricate organisations, programmes, suppliers, or figures.",
                "If no organisation is found for the capability, say so explicitly and "
                "state what was searched.",
                "Prefer organisations appearing across multiple sources — flag as high "
                "confidence.",
            ],
        ),
        "</system_prompt>",
    )
