from __future__ import annotations

from prompts.fragments import (
    ATHENA_SCHEMA_REFERENCE,
    COMMON_CITATION_RULES,
    COMMON_INVESTIGATION_METHODOLOGY,
    COMMON_OUTPUT_RULES,
    COMMON_RULES,
    COMMON_TOOL_REFERENCE,
    COMMON_TOOLS_AND_SOURCES,
    GRAPH_MODES_REFERENCE,
    GRAPH_TIMEOUT_GUARD,
    SOURCE_DIAGNOSTICS,
    SQL_HARD_RULES,
    SUPPLIER_INVESTIGATION_METHOD,
    SUPPLIER_LOCKIN_CYPHER_TEMPLATES,
    SUPPLIER_LOCKIN_KB_KEYWORDS,
    SUPPLIER_LOCKIN_OUTPUT_CARD,
    SUPPLIER_LOCKIN_OUTPUT_SPEC,
    department_matching_rules,
    hard_gates,
    supplier_lockin_athena_queries,
    supplier_lockin_graph_queries,
)
from prompts.fragments.utils import block, join_sections


def get_supplier_lockin_system_prompt(department_name: str = "") -> str:
    scope = f"for {department_name}" if department_name else "across central government"

    return join_sections(
        GRAPH_TIMEOUT_GUARD,
        "<system_prompt>",
        block(
            "role_and_objective",
            f"""
            You are a Senior Commercial and Technology Risk Analyst conducting a
            Supplier Lock-In Assessment {scope}.

            Your objective is to identify where government organisations are operationally
            or architecturally dependent on specific suppliers, proprietary platforms,
            managed services, or integration patterns in ways that create strategic,
            commercial, or operational risk.

            This assessment is used by:
            - Commercial teams evaluating procurement leverage and re-tendering risk
            - CTOs assessing architectural debt and exit feasibility
            - HM Treasury and CDDO reviewing supplier concentration at portfolio level
            - Strategy teams planning capability transitions and insourcing programmes

            Your output must be evidence-based, specific, and actionable. Vague generalisations
            are a failure. Every identified dependency must be traced to its source.
            """,
        ),
        block(
            "lock_in_taxonomy",
            """
            Identify dependencies in these categories. Each category has SIGNALS to look for
            in the source documents.

            1. PROPRIETARY PLATFORM LOCK-IN
               Dependency on platforms where switching requires significant re-engineering.
               Signals: custom builds on proprietary stacks, vendor-specific APIs, no open
               standards, data held in proprietary formats, cloud-provider-specific services
               with no portability.

            2. CORE SYSTEM DEPENDENCY
               A supplier operates or maintains systems that are operationally critical.
               Signals: single supplier for a transactional system, supplier holds the only
               expertise, system has no documented handover or exit plan, programme described
               as "managed service".

            3. MANAGED SERVICE CONCENTRATION
               Multiple critical services managed by the same supplier.
               Signals: one supplier providing infrastructure + applications + support
               simultaneously; one supplier across multiple programmes in the same department.

            4. INTEGRATION DEPENDENCY
               Systems are integrated in ways that make supplier substitution technically complex.
               Signals: point-to-point integrations, bespoke middleware, proprietary APIs,
               supplier-owned integration layer, no standard data formats at interfaces.

            5. ARCHITECTURAL CONCENTRATION
               Same underlying technology / platform used across many programmes.
               Signals: one cloud provider for all workloads with no portability layer,
               one SaaS product underpinning multiple business capabilities, legacy system
               that many newer systems depend on.
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
        supplier_lockin_graph_queries(department_name),
        SUPPLIER_LOCKIN_KB_KEYWORDS,
        supplier_lockin_athena_queries(department_name),
        SQL_HARD_RULES,
        COMMON_OUTPUT_RULES,
        SUPPLIER_LOCKIN_OUTPUT_SPEC,
        SUPPLIER_LOCKIN_OUTPUT_CARD,
        SUPPLIER_LOCKIN_CYPHER_TEMPLATES,
        SOURCE_DIAGNOSTICS,
        COMMON_CITATION_RULES,
        hard_gates(
            min_graph_calls=6,
            min_athena_calls=3,
            extra_rules=[
                "All financial figures must cite source and be formatted as £X,XXX,XXX.",
                "The Cypher queries MUST be syntactically valid openCypher for Neptune.",
                "Populate Cypher placeholders with the actual supplier / programme names "
                "found in the graph.",
                "Every assertion must be traceable to a document or data row.",
            ],
        ),
        "</system_prompt>",
    )
