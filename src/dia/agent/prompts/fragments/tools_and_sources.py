from __future__ import annotations

from dia.agent.prompts.fragments.utils import block, bullet_list

COMMON_TOOL_REFERENCE = block(
    "tool_reference",
    f"""
    EXACT TOOL NAMES:
    {
        bullet_list(
            [
                "default_ — GraphRAG knowledge graph (params: query, mode, entity_name)",
                "search_ — helper to find relevant graph tools where available",
                "wait_after_timeout — call before every throttled graph retry (mandatory)",
                "kb_search_gats_business_cases — full-text GATS business cases (OBCs / SOCs / FBCs)",
                "kb_search_sr25_bids — SR25 spending review bids (current investment plans)",
                "kb_search_sr21_bids — SR21 spending review bids (historical baseline; NOT in graph)",
                "kb_search_nao_reports — NAO reports and PAC findings (NOT in graph)",
                "kb_search_efficiency_reports — interim efficiencies reports per department (SR25 follow-up; efficiency savings focus + SR27 plans; NOT in graph)",
                "list_athena_tables — discover Athena tables",
                "get_table_schema — inspect exact table columns before writing SQL (mandatory)",
                "execute_sql — run Athena SQL (SELECT only)",
                "web_search_gov — search GOV.UK publications",
            ]
        )
    }

    CRITICAL:
    - default_ IS the GraphRAG knowledge graph. Do not be confused by the name.
    - It is your primary and most powerful tool — use it first wherever entity relationships matter.
    - Always call get_table_schema before writing SQL.
    - Always call wait_after_timeout(seconds=30) before retrying a graph call after a timeout.
    """,
)


GRAPH_MODES_REFERENCE = block(
    "graph_modes_reference",
    """
    default_ MODES — use `mode` to scope EVERY call (this is how you stay inside the timeout budget):

    | mode | What it searches | entity_name required? |
    |------|-----------------|----------------------|
    | `default` | All document types, broad sweep | No |
    | `department_all_sources` | All sources for ONE department | Yes — department name |
    | `metadata_filtered_business_case_department` | Business Cases for one department | Yes — department name |
    | `metadata_filtered_business_case_alb` | Business Cases for one ALB | Yes — ALB name |
    | `metadata_filtered_sr_bids_department` | SR Bids for one department | Yes — department name |
    | `metadata_filtered_sr_bids_alb` | SR Bids for one ALB | Yes — ALB name |
    | `metadata_filtered_contract_finder_department` | Contract Finder for one department | Yes — department name |
    | `search_by_project` | Contract Finder filtered by project/contract name | Yes — contract name |
    | `business_case_all` | All Business Cases, no org filter | No |
    | `sr_bids_all` | All SR Bids, no org filter | No |
    | `contract_finder_all` | All Contract Finder documents, no org filter | No |

    FALLBACK RULE — CRITICAL:
    If a filtered mode (e.g. `metadata_filtered_business_case_department`) returns no or thin results,
    IMMEDIATELY retry with `mode="business_case_all"` or `mode="default"` before concluding the data
    is absent. Documents may be indexed under a slightly different department name.

    RETRY ESCALATION on TimeLimitExceededException — follow exactly, never skip the wait:
    1. First failure -> call `wait_after_timeout(seconds=30)`, then retry the SAME call with
       `_throttled` appended to the mode (e.g. `default_throttled`,
       `metadata_filtered_business_case_department_throttled`). Reduces graph traversal depth.
    2. Second failure -> call `wait_after_timeout(seconds=30)`, then retry with `_super_throttled`
       appended (e.g. `default_super_throttled`,
       `metadata_filtered_business_case_department_super_throttled`). Vector-only — cannot timeout.
    3. `_super_throttled` still fails (non-timeout) -> skip the graph call, proceed with
       KB + Athena sources, and note the gap in your diagnostics section.

    Never fire a retry without the `wait_after_timeout` call in between.
    """,
)


COMMON_TOOLS_AND_SOURCES = block(
    "available_tools",
    """
    ### 1. default_ — GraphRAG Knowledge Graph (Neptune + OpenSearch) — PRIMARY SOURCE

    The graph is built from three document corpora with cross-source entity resolution:
    - **Business Cases** — OBCs, SOCs, FBCs submitted through GATS spend controls
    - **SR25 Bids** — 2025 Spending Review departmental submissions
    - **Contract Finder** — Published government contracts (titles + verbatim text)

    The graph's UNIQUE VALUE is cross-source entity resolution. The same supplier, programme,
    technology, or risk may appear across all three sources — the graph links them. No other
    tool can do this. A supplier appearing in a business case AND a contract AND an SR bid is
    a multi-evidenced, high-confidence finding.

    ### Entity types in the graph:
    | Type | Examples | Found across |
    |------|---------|--------------|
    | Programmes & Projects | Named programmes, Spend IDs, capability builds | Business cases, SR bids |
    | Suppliers & Vendors | Companies, SIs, cloud providers, managed service vendors | Business cases, Contracts |
    | Technologies & Platforms | Named systems, cloud services, SaaS products, APIs | All three sources |
    | Financial Commitments | RDEL/CDEL, contract values, whole life costs | All three sources |
    | Risks & Dependencies | Named risks, blockers, single points of failure | Business cases, SR bids |
    | People & Roles | SROs, delivery leads, programme boards | Business cases |
    | Timelines & Milestones | Go-live dates, contract end dates, SR periods | All three sources |
    | Contract Titles & Text | Verbatim contract titles and descriptions | Contracts |

    ### What the graph reveals (that other tools cannot):
    - A supplier named in a business case ALSO holds contracts worth £Xm on Contract Finder
      AND is referenced in the SR25 bid as a dependency — full exposure.
    - A programme shares a platform dependency with three other programmes — concentration
      risk invisible in any single document.
    - A technology contracted via Contract Finder but with no business case — uncontrolled spend.
    - Two departments referencing the same supplier for similar capabilities — duplication
      and shared procurement opportunity.

    ### How to call default_:
    - `query`: Specific, detailed natural language question
    - `mode`: Controls retrieval strategy and filter scope (see `<graph_modes_reference>`)
    - `entity_name`: Exact department / ALB / project / contract name; required for all
      `metadata_filtered_*`, `department_all_sources`, and `search_by_project` modes.
      Leave empty ("") for unfiltered modes.

    ### 2. Knowledge Bases — TARGETED DETAIL & HISTORICAL CONTEXT

    `kb_search_gats_business_cases` — same documents as the graph's business case nodes.
    The graph gives entities and connections; this KB gives PRECISE PASSAGES. Use for:
    exact cost breakdowns, full risk register entries with likelihood/impact, options
    appraisals, governance structures, benefits realisation plans, commercial strategy,
    delivery milestones.

    `kb_search_sr25_bids` — full text of SR25 spending review submissions. Use for:
    exact RDEL/CDEL by year (25/26 through 28/29), CDEL profiles, efficiency savings targets,
    headcount plans, uplift justifications, BCR calculations.

    `kb_search_sr21_bids` — NOT in the graph. SR21 (2021) submissions. Historical baseline.
    Use to: compare SR21 commitments against SR25 asks, identify programmes funded in SR21
    but absent from SR25 (abandoned?), track how programme scope and cost evolved.
    Key question: "what did the department say it would build for SR21 money and did it?"

    `kb_search_nao_reports` — NOT in the graph. NAO reports and PAC findings.
    Cross-reference EVERY major programme, supplier, and capability area found in other
    sources. Search by: (1) programme name, (2) supplier name, (3) capability area
    (e.g. "identity verification", "case management"), (4) department + "digital".
    Look for: cost overruns, delivery failures, systemic issues, unacted recommendations,
    value-for-money judgements.

    `kb_search_efficiency_reports` — NOT in the graph. Per-department interim efficiencies
    reports produced as a FOLLOW-UP to the SR25 bids. Use for: where a department intends to
    focus its efficiency savings, the profile/scale of those savings, and its priorities and
    plans for the upcoming SR27 spending review bids. Pairs naturally with `kb_search_sr25_bids`
    (what was asked for) — this KB shows how the department now plans to deliver savings and
    what it will bid for next. For workforce-efficiency questions, triangulate with the
    `workforce_commision_26` Athena table (actual headcount / contractor mix / pay).

    KB usage rules:
    - Use ONLY AFTER the graph has surfaced specific entities to investigate, unless graph
      coverage is thin (then KBs become fallback discovery).
    - For each major programme: query gats KB AND sr25 KB.
    - For programmes with SR21 history: query sr21 KB to understand evolution.
    - For every major programme, supplier, and risk: query nao KB.

    ### 3. Athena SQL — QUANTITATIVE EVIDENCE

    Always:
    - call `list_athena_tables` first to discover what exists
    - call `get_table_schema` before writing SQL — never assume column names
    - use `TRY_CAST(REPLACE(REPLACE(<col>, ',', ''), '"', '') AS BIGINT)` for spend amounts
      stored as formatted strings
    - use LOWER() + LIKE with wildcards for department/text matching, never exact equality
    - use backticks for hyphenated database/table names
    - LIMIT 50 unless aggregating

    See `<athena_schema_reference>` for the full table/column reference.

    ### 4. web_search_gov — GOV.UK PUBLICATIONS

    Searches gov.uk/government/publications for departmental digital strategies,
    IPA annual reports, transformation plans, outcome delivery plans, contract award
    notices, NAO reports, ministerial directions.

    Use AFTER graph and KB phases to ground internal findings in published context.
    Do not let weak public commentary override stronger internal or structured evidence.
    """,
)


def department_matching_rules() -> str:
    return block(
        "department_name_matching",
        """
        DEPARTMENT NAME MATCHING — CRITICAL:
        Data uses inconsistent casing and abbreviation. Always use LOWER() + LIKE patterns
        with wildcards rather than exact equality.

        - Home Office:  LIKE '%home office%'
        - HMRC:         LIKE '%hmrc%' OR LIKE '%hm revenue%' OR LIKE '%revenue and customs%'
        - MoJ:          LIKE '%moj%' OR LIKE '%ministry of justice%'
        - DWP:          LIKE '%dwp%' OR LIKE '%work and pensions%'
        - DfE:          LIKE '%dfe%' OR LIKE '%department for education%'
        - DHSC:         LIKE '%dhsc%' OR LIKE '%health and social care%'
        - DESNZ:        LIKE '%desnz%' OR LIKE '%energy security%'
        - DSIT:         LIKE '%dsit%' OR LIKE '%science innovation%'
        - DfT:          LIKE '%dft%' OR LIKE '%department for transport%'
        - DEFRA:        LIKE '%defra%' OR LIKE '%environment food%'
        - MOD:          LIKE '%mod%' OR LIKE '%ministry of defence%'
        - FCDO:         LIKE '%fcdo%' OR LIKE '%foreign commonwealth%'
        - DLUHC:        LIKE '%dluhc%' OR LIKE '%levelling up%' OR LIKE '%housing communities%'
        - Cabinet Office: LIKE '%cabinet office% OR LIKE %co'

        Never use exact equality (=) for department name filtering.
        """,
    )


SERVICE_STANDARD_SOURCE = block(
    "service_standard_source",
    """
    SERVICE STANDARD ASSESSMENTS — USER-OUTCOME LENS:
    Source: "gats-assurance".service_assessments_snapshot20251217 (database name has a hyphen,
    so wrap in double quotes in SQL).

    This is the user-outcome lens that complements the financial (£) and delivery-confidence
    (GMPP/GATS) lenses. It records GDS Service Standard assessment outcomes — one row per
    assessment — with: latest_update, service_id, service_name, department,
    crossgov_departmental, stage (Alpha/Beta/Live), type, assessment_date, outcome (Met/Not Met),
    points_notmet_1 .. points_notmet_11.

    HOW SERVICE STANDARD LINKS TO OTHER SOURCES — CRITICAL CROSS-LENS:
    - service_name / service_id -> match against programmes/projects in graph and business
      case KB results. Use LOWER() / LIKE matching.
    - department -> match using the same LOWER() / LIKE patterns as other tables.
    - GMPP `Project Name` -> many GMPP-tracked digital programmes deliver services that
      appear here. Cross-reference `gmpp_24_25` Project Name against `service_name`.
    - GATS spend cases -> cases that funded a service build should reconcile with the
      service's stage and outcome.

    TRIANGULATION RULES:
    - Live + Met + low GATS RiskScore + Green GMPP rating -> high-confidence delivery
    - Not Met + Live + high GATS RiskScore + Amber/Red GMPP -> flagged systemic concern
    - Assessed but absent from graph/contracts -> service exists outside the formal
      programme / spend record (worth surfacing)
    - In graph/GATS/GMPP but never assessed -> no independent user-needs validation
    """,
)
