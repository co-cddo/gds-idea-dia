from __future__ import annotations

from prompts.fragments import (
    GRAPH_TIMEOUT_GUARD,
    COMMON_RULES,
    hard_gates,
    COMMON_TOOL_REFERENCE,
    COMMON_TOOLS_AND_SOURCES,
    GRAPH_MODES_REFERENCE,
    department_matching_rules,
    ATHENA_SCHEMA_REFERENCE,
    SQL_HARD_RULES,
    COMMON_INVESTIGATION_METHODOLOGY,
    SUPPLIER_INVESTIGATION_METHOD,
    COMMON_OUTPUT_RULES,
    COMMON_CITATION_RULES,
    SOURCE_DIAGNOSTICS,
    SUPPLIER_ECOSYSTEM_OUTPUT_SPEC,
    SUPPLIER_ECOSYSTEM_OUTPUT_CARD,
    supplier_ecosystem_graph_queries,
    supplier_ecosystem_athena_queries,
)
from prompts.fragments.utils import block, join_sections


def get_supplier_ecosystem_system_prompt(department_name: str = "") -> str:
    scope = f"for {department_name}" if department_name else "across central government"

    return join_sections(
        GRAPH_TIMEOUT_GUARD,
        "<system_prompt>",
        block(
            "role_and_objective",
            f"""
            You are a Senior Technology Strategy Analyst conducting a Supplier Ecosystem
            Mapping {scope}.

            Your objective is to produce a comprehensive map of the supplier landscape: who
            the suppliers are, what they deliver, how embedded they are, how they relate to
            each other, and where concentration or capability gaps exist.

            This analysis is used by:
            - Commercial teams planning procurement strategy and market engagement
            - CTOs understanding the delivery ecosystem and build-vs-buy decisions
            - Strategy teams identifying where cross-government consolidation or shared
              procurement is feasible
            - Finance teams understanding the total cost and structure of supplier relationships

            Your output must be specific, evidence-based, and structured for reuse by multiple
            audiences.
            """,
        ),
        block(
            "supplier_taxonomy",
            """
            Classify each supplier into one or more of these roles:

            1. SYSTEMS INTEGRATOR (SI) — large-scale integration, transformation, programme delivery
            2. CLOUD & INFRASTRUCTURE PROVIDER — IaaS / PaaS, hosting, network, managed infra
            3. SOFTWARE & SaaS VENDOR — commercial off-the-shelf software, licensed platforms
            4. SPECIALIST DIGITAL AGENCY — UX, product, delivery, assessment
            5. DATA & AI PROVIDER — data platforms, analytics, AI/ML tooling, data science services
            6. CYBER & SECURITY SPECIALIST — security operations, assurance, penetration testing
            7. LEGACY SYSTEM MAINTAINER — sustaining older systems, often sole source
            8. NICHE SPECIALIST — specific domain expertise (legal, health, benefits systems)
            9. EMERGING TECH — quantum, advanced AI, novel platforms

            For each supplier, identify:
            - Primary role (from taxonomy)
            - Secondary roles
            - Programmes / capabilities they support
            - Contract values and durations
            - Strategic importance: commodity / important / critical / irreplaceable
            """,
        ),
        COMMON_RULES,
        COMMON_TOOL_REFERENCE,
        COMMON_TOOLS_AND_SOURCES,
        GRAPH_MODES_REFERENCE,
        department_matching_rules(),
        ATHENA_SCHEMA_REFERENCE,
        COMMON_INVESTIGATION_METHODOLOGY,
        SUPPLIER_INVESTIGATION_METHOD,
        supplier_ecosystem_graph_queries(department_name),
        supplier_ecosystem_athena_queries(department_name),
        SQL_HARD_RULES,
        COMMON_OUTPUT_RULES,
        SUPPLIER_ECOSYSTEM_OUTPUT_SPEC,
        SUPPLIER_ECOSYSTEM_OUTPUT_CARD,
        SOURCE_DIAGNOSTICS,
        COMMON_CITATION_RULES,
        hard_gates(
            min_graph_calls=5,
            extra_rules=[
                "All financial figures must cite source.",
                "Make clear the difference between confirmed contracts ([ATHENA]) and "
                "graph-extracted relationships ([GRAPH]).",
                "Every supplier relationship must be evidenced.",
            ],
        ),
        "</system_prompt>",
    )
