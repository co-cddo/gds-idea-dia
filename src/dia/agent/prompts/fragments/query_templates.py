"""Per-investigation graph + Athena query templates.

These restore the operational specificity that was lost when the monolithic
src/system_prompts.py was split into small templates. Each block here is the
canonical "how to actually query" reference for one type of investigation.

All blocks are built as functions where the dynamic parts (department name,
mode resolution, SQL filters) are computed at call time, mirroring the
behaviour of the original prompts.
"""

from __future__ import annotations

from dia.agent.prompts.fragments.utils import block

# -----------------------------------------------------------------------------
# DBR — required graph + Athena query enumerations
# -----------------------------------------------------------------------------


def dbr_required_graph_queries(department_name: str = "Home Office") -> str:
    return block(
        "dbr_required_graph_queries",
        f"""
        DBR — REQUIRED GRAPH QUERIES (minimum 8, sequential, ONE AT A TIME):

        1. mode="department_all_sources", entity_name="{department_name}"
           "Major digital programmes, technology platforms, suppliers, and capabilities."

        2. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           "Programmes with business cases: names, costs, suppliers, risks, systems,
            Spend IDs, delivery timelines."

        3. mode="metadata_filtered_sr_bids_department", entity_name="{department_name}"
           "Spending review priorities, RDEL/CDEL funding asks, transformation programmes,
            data/AI investments, workforce plans."

        4. mode="metadata_filtered_contract_finder_department", entity_name="{department_name}"
           "Contracts, suppliers, technologies, and procurement activity."

        5. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           "Data platforms, analytics, AI/ML, data infrastructure, data governance, data sharing."

        6. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           "Legacy systems, technical debt, migrations, decommissioning,
            end-of-life platforms, mainframe."

        7. mode="default" (entity drill-down for top programme found above)
           "All suppliers, dependencies, risks, technologies, and costs connected to [Programme X]."

        8. mode="default", entity_name=""
           "Which departments share suppliers, platforms, or capabilities with {department_name}?"

        Use the FALLBACK RULE: if a metadata_filtered_* call returns thin results, retry
        immediately with `business_case_all` / `sr_bids_all` / `contract_finder_all` / `default`.
        """,
    )


def dbr_required_athena_queries(department_name: str = "Home Office") -> str:
    dept_lower = department_name.lower()
    return block(
        "dbr_required_athena_queries",
        f"""
        DBR — REQUIRED ATHENA QUERIES (minimum 8, sequential):

        1. `list_athena_tables` — discover all tables.
        2. `get_table_schema` for each table you intend to query.

        3. GATS — total requested / approved / risk by department:
           SELECT OrganisationSubmitter,
                  COUNT(*) AS cases,
                  SUM(TotalValueRequested) AS requested,
                  SUM(TotalValueApproved) AS approved,
                  AVG(RiskScore) AS avg_risk
           FROM "gats-assurance-ai".<gats_cases_table>
           WHERE LOWER(OrganisationSubmitter) LIKE '%{dept_lower}%'
           GROUP BY OrganisationSubmitter

        4. SR25 — RDEL/CDEL totals and uplifts for the department:
           SELECT department, total_rdel, total_cdel, rdel_uplift, cdel_uplift, benefit_cost_ratio
           FROM "gats-assurance-ai".<sr25_table>
           WHERE LOWER(department) LIKE '%{dept_lower}%'

        5. Contracts — total spend and contract count by seller for this department:
           SELECT seller_name,
                  COUNT(*) AS contracts,
                  SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
           FROM assurance_contracts.extracted_contracts
           WHERE LOWER(buyer_name) LIKE '%{dept_lower}%'
           GROUP BY seller_name
           ORDER BY total_value DESC
           LIMIT 50

        6. Contracts — top 20 contracts by value with title and category:
           SELECT title, seller_name, value, digital_spend_category, lifecycle_stage
           FROM assurance_contracts.extracted_contracts
           WHERE LOWER(buyer_name) LIKE '%{dept_lower}%'
           ORDER BY TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT) DESC
           LIMIT 20

        7. Contracts — aggregate spend by digital_spend_category:
           SELECT digital_spend_category,
                  COUNT(*) AS contracts,
                  SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
           FROM assurance_contracts.extracted_contracts
           WHERE LOWER(buyer_name) LIKE '%{dept_lower}%'
           GROUP BY digital_spend_category
           ORDER BY total_value DESC

        8. GMPP — all projects for the department with IPA confidence, whole life cost, variance:
           SELECT "Project Name",
                  "IPA Delivery Confidence Assessment",
                  "Whole Life Cost (£m)",
                  "Financial Year Variance (%)",
                  "Schedule Narrative",
                  "SRO Name"
           FROM assurance_contracts.gmpp_24_25
           WHERE LOWER(Department) LIKE '%{dept_lower}%'

        9. GMPP — projects rated Amber/Red or Red (flag these):
           SELECT "Project Name", "IPA Delivery Confidence Assessment", "Whole Life Cost (£m)"
           FROM assurance_contracts.gmpp_24_25
           WHERE LOWER(Department) LIKE '%{dept_lower}%'
             AND ("IPA Delivery Confidence Assessment" LIKE '%Amber%'
                  OR "IPA Delivery Confidence Assessment" LIKE '%Red%')

        10. Service Standard — count of assessments by stage and outcome for the department:
            SELECT stage, outcome, COUNT(*) AS assessments
            FROM "gats-assurance".service_assessments_snapshot20251217
            WHERE LOWER(department) LIKE '%{dept_lower}%'
            GROUP BY stage, outcome
            ORDER BY stage, outcome

        11. Service Standard — most-frequently-failed Standard points:
            SELECT
              SUM(CASE WHEN points_notmet_1  IS NOT NULL AND points_notmet_1  != '' THEN 1 ELSE 0 END) AS p1,
              SUM(CASE WHEN points_notmet_2  IS NOT NULL AND points_notmet_2  != '' THEN 1 ELSE 0 END) AS p2,
              SUM(CASE WHEN points_notmet_3  IS NOT NULL AND points_notmet_3  != '' THEN 1 ELSE 0 END) AS p3,
              SUM(CASE WHEN points_notmet_4  IS NOT NULL AND points_notmet_4  != '' THEN 1 ELSE 0 END) AS p4,
              SUM(CASE WHEN points_notmet_5  IS NOT NULL AND points_notmet_5  != '' THEN 1 ELSE 0 END) AS p5,
              SUM(CASE WHEN points_notmet_6  IS NOT NULL AND points_notmet_6  != '' THEN 1 ELSE 0 END) AS p6,
              SUM(CASE WHEN points_notmet_7  IS NOT NULL AND points_notmet_7  != '' THEN 1 ELSE 0 END) AS p7,
              SUM(CASE WHEN points_notmet_8  IS NOT NULL AND points_notmet_8  != '' THEN 1 ELSE 0 END) AS p8,
              SUM(CASE WHEN points_notmet_9  IS NOT NULL AND points_notmet_9  != '' THEN 1 ELSE 0 END) AS p9,
              SUM(CASE WHEN points_notmet_10 IS NOT NULL AND points_notmet_10 != '' THEN 1 ELSE 0 END) AS p10,
              SUM(CASE WHEN points_notmet_11 IS NOT NULL AND points_notmet_11 != '' THEN 1 ELSE 0 END) AS p11
            FROM "gats-assurance".service_assessments_snapshot20251217
            WHERE LOWER(department) LIKE '%{dept_lower}%'

        12. Service Standard cross-link — match service_name to programmes from graph/KB
            and to "Project Name" in gmpp_24_25.
        """,
    )


def dbr_web_searches(department_name: str = "Home Office") -> str:
    return block(
        "dbr_web_searches",
        f"""
        DBR — REQUIRED GOV.UK SEARCHES (minimum 2):
        1. "{department_name} digital strategy" or "{department_name} technology"
        2. "[major programme name from graph] {department_name}"

        Optional further searches:
        - "[supplier name] {department_name}"
        - "IPA annual report major projects 2024"
        - "NAO {department_name}"
        """,
    )


# -----------------------------------------------------------------------------
# Default investigation — required graph sequence
# -----------------------------------------------------------------------------


def default_required_graph_sequence(department_name: str = "Home Office") -> str:
    return block(
        "default_required_graph_sequence",
        f"""
        DEFAULT — REQUIRED GRAPH QUERY SEQUENCE (minimum 5, sequential):

        1. `default_(query="major digital programmes, suppliers, platforms, and capabilities",
                     mode="department_all_sources",
                     entity_name="{department_name}")`

        2. `default_(query="programmes with business cases, suppliers, costs, risks, and systems",
                     mode="metadata_filtered_business_case_department",
                     entity_name="{department_name}")`

        3. `default_(query="spending review investment priorities, funding asks, capabilities,
                            and transformation programmes",
                     mode="metadata_filtered_sr_bids_department",
                     entity_name="{department_name}")`

        4. `default_(query="contracts, suppliers, technologies, and procurement activity",
                     mode="metadata_filtered_contract_finder_department",
                     entity_name="{department_name}")`

        5. Entity drill-downs for top programmes / suppliers found above:
           `default_(query="What is connected to [Entity X]? suppliers, risks, contracts, dependencies",
                    mode="department_all_sources",
                    entity_name="{department_name}")`

        6. Cross-government:
           `default_(query="Which departments use [Supplier/Platform Y]?",
                    mode="default",
                    entity_name="")`
        """,
    )


# -----------------------------------------------------------------------------
# Project investigation — graph + Athena templates
# -----------------------------------------------------------------------------

PROJECT_GRAPH_QUERIES = block(
    "project_graph_queries",
    """
    PROJECT INVESTIGATION — GRAPH QUERY SEQUENCE (sequential, max 4 in this phase):

    Step 1.1: `default_(query="[PROJECT NAME] programme project", mode="default")`
              -> find the project entity and immediate connections. WAIT for result.

    Step 1.2: `default_(query="[PROJECT NAME] suppliers technologies platforms dependencies",
                        mode="default")`
              -> supplier / tech connections. WAIT for result.

    Step 1.3: `default_(query="[PROJECT NAME] risks costs timelines milestones",
                        mode="default")`
              -> financial and risk data. WAIT for result.

    Step 1.4 (if department known):
              `default_(query="[PROJECT NAME]",
                        mode="metadata_filtered_business_case_department",
                        entity_name="[DEPT]")`

    Step 1.5: `default_(query="[PROJECT NAME]", mode="sr_bids_all")`

    Record ALL entity names, types, and relationships discovered.
    Search variations of the name, partial matches, and abbreviations — a project may
    appear under slightly different names across sources.
    """,
)


PROJECT_ATHENA_QUERIES = block(
    "project_athena_queries",
    """
    PROJECT INVESTIGATION — ATHENA QUERIES (always `get_table_schema` first):

    1. Spend controls (GATS) — find the case:
       SELECT co_spendid, co_casename, co_organisationsubmitter, co_shortdescription,
              co_casestatus, co_spendamount, co_assurancerating, co_caseriskrating,
              co_aiquantum_yesno, co_dt_spendcategory, co_commercialapproach,
              co_currentsupplier, co_proposedsupplier, co_sroname,
              co_spendstartdate, co_contractenddate, co_gmpp_yesno
       FROM assurance_contracts.spend_controls_data_export
       WHERE LOWER(co_casename) LIKE '%[project_name_lower]%'

    2. Contracts — find related contracts:
       SELECT buyer_name, seller_name, title, value, status, date, end_date,
              digital_spend_category, lifecycle_stage, delivery_model
       FROM assurance_contracts.extracted_contracts
       WHERE LOWER(title) LIKE '%[project_name_lower]%'

    3. GMPP — find delivery confidence and whole life cost:
       SELECT "Project Name", Department,
              "IPA Delivery Confidence Assessment",
              "Whole Life Cost (£m)",
              "Financial Year Forecast (£m)",
              "End Date"
       FROM assurance_contracts.gmpp_24_25
       WHERE LOWER("Project Name") LIKE '%[project_name_lower]%'

    Also search by organisation/department if the project name is too specific.
    """,
)


PROJECT_KB_QUERIES = block(
    "project_kb_queries",
    """
    PROJECT INVESTIGATION — KB SEARCHES:
    1. `kb_search_gats_business_cases("[PROJECT NAME]")` — OBC / SOC / FBC detail
    2. `kb_search_sr25_bids("[PROJECT NAME]")` — SR25 funding context
    3. `kb_search_sr21_bids("[PROJECT NAME]")` — historical SR21 baseline
    4. `kb_search_nao_reports("[PROJECT NAME]")` — any NAO / PAC scrutiny

    Extract: costs, timelines, risks, governance, benefits, dependencies.
    """,
)


# -----------------------------------------------------------------------------
# Supplier lock-in — graph + Athena (parameterised by department scope)
# -----------------------------------------------------------------------------


def supplier_lockin_graph_queries(department_name: str = "") -> str:
    if department_name:
        all_mode = "department_all_sources"
        bc_mode = "metadata_filtered_business_case_department"
        sr_mode = "metadata_filtered_sr_bids_department"
        cf_mode = "metadata_filtered_contract_finder_department"
        dept_filter = f'entity_name="{department_name}"'
    else:
        all_mode = "default"
        bc_mode = "business_case_all"
        sr_mode = "sr_bids_all"
        cf_mode = "contract_finder_all"
        dept_filter = 'entity_name=""'

    return block(
        "supplier_lockin_graph_queries",
        f"""
        SUPPLIER LOCK-IN — GRAPH QUERY SEQUENCE (minimum 6, sequential):

        Query 1: mode="{all_mode}", {dept_filter}
          "Which suppliers, vendors, and managed service providers appear?
           What programmes and projects do they support?
           List each supplier and the programmes they are connected to."

        Query 2: mode="{bc_mode}", {dept_filter}
          "What suppliers are named in business cases? For each supplier, which programme or
           project is it linked to? Are any suppliers named as the primary or sole provider?"

        Query 3: mode="{cf_mode}", {dept_filter}
          "Which suppliers hold contracts? For each supplier, what is the contract title,
           the buying department, and any related programmes or projects mentioned?"

        Query 4: mode="{sr_mode}", {dept_filter}
          "Which suppliers or technologies are named in spending review bids? Are any
           suppliers tied to specific future programmes or investment plans?"

        Query 5: mode="default", entity_name=""
          "Which suppliers appear across multiple departments? Which technology platforms are
           used by more than one department or more than one programme?"

        Query 6: mode="{all_mode}", {dept_filter}
          "What are the strongest supplier-to-project links in the graph? Which projects have
           the deepest dependency on a single supplier based on how they are described?"

        For EACH supplier found, record:
        - Supplier name (exact as it appears in the graph)
        - Programmes / projects it is linked to
        - Departments those programmes belong to
        - Document types it appears in (business case / SR bid / contract)
        - Any co-occurring suppliers (suppliers in the same programme)
        """,
    )


def supplier_lockin_athena_queries(department_name: str = "") -> str:
    dept_lower = department_name.lower() if department_name else ""
    dept_sql = f"AND LOWER(buyer_name) LIKE '%{dept_lower}%'" if department_name else ""
    dept_sql_gats = f"AND LOWER(co_organisationsubmitter) LIKE '%{dept_lower}%'" if department_name else ""

    return block(
        "supplier_lockin_athena_queries",
        f"""
        SUPPLIER LOCK-IN — ATHENA QUERIES (minimum 3, always `get_table_schema` first):

        1. By supplier — total contract value and number of contracts:
           SELECT seller_name,
                  COUNT(*) AS contracts,
                  SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
           FROM assurance_contracts.extracted_contracts
           WHERE LOWER(seller_name) LIKE '%[supplier]%'
           {dept_sql}
           GROUP BY seller_name
           ORDER BY total_value DESC

        2. Long-duration / extended contracts (lock-in signal):
           SELECT buyer_name, seller_name, title, value, end_date, lifecycle_stage
           FROM assurance_contracts.extracted_contracts
           WHERE lifecycle_stage IN ('extension', 'renewal')
           {dept_sql}
           ORDER BY end_date DESC

        3. Direct awards (reduced competition, lock-in signal):
           SELECT co_organisationsubmitter, co_casename, co_currentsupplier, co_proposedsupplier,
                  co_spendamount, co_commercialapproach
           FROM assurance_contracts.spend_controls_data_export
           WHERE co_directaward_yesno = 'Yes'
           {dept_sql_gats}

        4. Contract extensions (failed re-competitions or deliberate extensions):
           SELECT co_organisationsubmitter, co_casename, co_currentsupplier, co_spendamount
           FROM assurance_contracts.spend_controls_data_export
           WHERE co_contractextension_yesno = 'Yes'
           {dept_sql_gats}
        """,
    )


SUPPLIER_LOCKIN_KB_KEYWORDS = block(
    "supplier_lockin_kb_keywords",
    """
    SUPPLIER LOCK-IN — KB SEARCH KEYWORDS:

    For top suppliers found in graph:
    - `kb_search_gats_business_cases("[SUPPLIER]")` — look for:
      "exit strategy", "handover plan", "re-tendering risk", "IP ownership",
      "data portability", "single point of failure", "only supplier", "bespoke",
      "proprietary", "managed service", "transition plan".

    - `kb_search_sr25_bids("[SUPPLIER]")` — is the supplier embedded in future investment
      plans? Are SR25 bids contingent on this supplier?

    - `kb_search_nao_reports("[SUPPLIER]")` — has the NAO flagged this supplier or any
      managed service arrangement? Look for: failed re-competitions, cost overruns on
      extensions, supplier leverage cited as a risk.
    """,
)


# -----------------------------------------------------------------------------
# Supplier ecosystem — graph + Athena (parameterised by department scope)
# -----------------------------------------------------------------------------


def supplier_ecosystem_graph_queries(department_name: str = "") -> str:
    if department_name:
        all_mode = "department_all_sources"
        bc_mode = "metadata_filtered_business_case_department"
        cf_mode = "metadata_filtered_contract_finder_department"
        dept_filter = f'entity_name="{department_name}"'
    else:
        all_mode = "default"
        bc_mode = "business_case_all"
        cf_mode = "contract_finder_all"
        dept_filter = 'entity_name=""'

    return block(
        "supplier_ecosystem_graph_queries",
        f"""
        SUPPLIER ECOSYSTEM — GRAPH QUERY SEQUENCE (max 4 in initial discovery, sequential):

        Query 1: mode="{all_mode}", {dept_filter}
          "List all suppliers, vendors, delivery partners, and technology providers.
           What do they deliver?"

        Query 2: mode="{bc_mode}", {dept_filter}
          "Which suppliers are involved in digital programmes? What is each supplier's
           scope and role?"

        Query 3: mode="{cf_mode}", {dept_filter}
          "What procurement contracts exist? Which suppliers hold them? What capabilities
           do they cover?"

        Query 4: mode="default", entity_name=""
          "Which of these suppliers serve multiple departments? What capabilities do they
           provide cross-government?"

        Record every supplier entity with their connected programmes, platforms, and technologies.
        """,
    )


def supplier_ecosystem_athena_queries(department_name: str = "") -> str:
    dept_lower = department_name.lower() if department_name else ""
    dept_sql = f"WHERE LOWER(buyer_name) LIKE '%{dept_lower}%'" if department_name else ""
    dept_sql_gats = f"AND LOWER(co_organisationsubmitter) LIKE '%{dept_lower}%'" if department_name else ""
    buyers_or_cats = "buyers" if not department_name else "categories"

    return block(
        "supplier_ecosystem_athena_queries",
        f"""
        SUPPLIER ECOSYSTEM — ATHENA QUERIES (always `get_table_schema` first):

        1. Full supplier footprint:
           SELECT seller_name,
                  COUNT(*) AS contracts,
                  COUNT(DISTINCT buyer_name) AS {buyers_or_cats},
                  SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
           FROM assurance_contracts.extracted_contracts
           {dept_sql}
           GROUP BY seller_name
           ORDER BY contracts DESC
           LIMIT 50

        2. Technology category breakdown:
           SELECT digital_spend_category,
                  COUNT(*) AS contracts,
                  COUNT(DISTINCT seller_name) AS distinct_suppliers
           FROM assurance_contracts.extracted_contracts
           {dept_sql}
           GROUP BY digital_spend_category
           ORDER BY contracts DESC

        3. Delivery model split:
           SELECT delivery_model,
                  COUNT(*) AS contracts,
                  COUNT(DISTINCT seller_name) AS suppliers
           FROM assurance_contracts.extracted_contracts
           {dept_sql}
           GROUP BY delivery_model
           ORDER BY contracts DESC

        4. GATS supplier pipeline exposure:
           SELECT co_proposedsupplier,
                  COUNT(*) AS cases,
                  SUM(TRY_CAST(REPLACE(REPLACE(co_spendamount, ',', ''), '"', '') AS BIGINT)) AS total_requested
           FROM assurance_contracts.spend_controls_data_export
           WHERE co_proposedsupplier IS NOT NULL AND co_proposedsupplier != ''
           {dept_sql_gats}
           GROUP BY co_proposedsupplier
           ORDER BY total_requested DESC
           LIMIT 30
        """,
    )


# -----------------------------------------------------------------------------
# Targeted question — synonym examples + Athena templates
# -----------------------------------------------------------------------------

TARGETED_QUESTION_SYNONYMS = block(
    "targeted_question_synonyms",
    """
    TARGETED QUESTION — SYNONYM EXPANSION:

    Before searching, decompose the question and expand the capability/topic into synonyms
    and related terms. The same capability is described many ways across documents. Always
    search several phrasings.

    Worked examples:
    - "CRM" -> "customer relationship management", "CRM", "case management",
      "customer record", "contact management", "Dynamics 365", "Salesforce",
      "customer service platform"
    - "identity" -> "identity verification", "digital identity", "One Login",
      "GOV.UK Verify", "IDV"
    - "data platform" -> "data platform", "data lake", "analytics platform",
      "data warehouse", "data mesh"
    - "AI" -> "artificial intelligence", "machine learning", "AI", "LLM",
      "generative AI", "ML model", "foundation model"
    - "case management" -> "case management", "case working", "workflow",
      "case handling system"
    - "HR / payroll" -> "HR system", "payroll", "human resources", "people system",
      "Workday", "Oracle HCM", "SAP SuccessFactors"
    - "finance / ERP" -> "finance system", "ERP", "general ledger", "Oracle Fusion",
      "SAP S/4HANA", "Workday Financials"

    Typical questions you handle:
    - "Which organisations are working on building Customer Relationship Management (CRM) systems?"
    - "Who is investing in identity verification / case management / data platforms / AI?"
    - "Which departments have contracts with [supplier] for [capability]?"
    - "Where is spend on [technology] happening across government?"
    """,
)


TARGETED_QUESTION_GRAPH_QUERIES = block(
    "targeted_question_graph_queries",
    """
    TARGETED QUESTION — GRAPH QUERY SEQUENCE (2-4 queries, sequential):

    Query 1: mode="default", entity_name=""
      "Which organisations, departments, or programmes are working on
       [CAPABILITY + synonyms]? Name each organisation and the programme,
       system, or contract that links them to it."

    Query 2: mode="business_case_all", entity_name=""
      "Which business cases describe building or procuring [CAPABILITY + synonyms]?
       Which department submitted each, and what programme is it for?"

    Query 3: mode="sr_bids_all", entity_name=""
      "Which spending review bids fund [CAPABILITY + synonyms]? Which department,
       and what is planned?"

    Query 4 (only if a department was named):
      mode="department_all_sources", entity_name="[DEPT]"
      Confirm the department's specific activity in this capability.

    Record, for each hit: organisation, programme/contract name, supplier (if any),
    source type.
    """,
)


TARGETED_QUESTION_ATHENA_QUERIES = block(
    "targeted_question_athena_queries",
    """
    TARGETED QUESTION — ATHENA QUERIES (always `get_table_schema` first):

    Adapt LIKE terms to your synonym list. Example for "CRM":

    Contracts mentioning the capability:
       SELECT buyer_name, seller_name, title, value, digital_spend_category, named_commercial_technologies
       FROM assurance_contracts.extracted_contracts
       WHERE LOWER(title) LIKE '%crm%'
          OR LOWER(title) LIKE '%customer relationship%'
          OR LOWER(digital_spend_description) LIKE '%customer relationship management%'
          OR LOWER(named_commercial_technologies) LIKE '%dynamics%'
          OR LOWER(named_commercial_technologies) LIKE '%salesforce%'
       LIMIT 50

    GATS spend controls mentioning the capability:
       SELECT co_organisationsubmitter, co_casename, co_shortdescription,
              co_spendamount, co_casestatus
       FROM assurance_contracts.spend_controls_data_export
       WHERE LOWER(co_casename) LIKE '%crm%'
          OR LOWER(co_shortdescription) LIKE '%customer relationship management%'
       LIMIT 50

    Rank organisations by exposure to the topic:
       SELECT buyer_name,
              COUNT(*) AS contracts,
              SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
       FROM assurance_contracts.extracted_contracts
       WHERE [capability filters as above]
       GROUP BY buyer_name
       ORDER BY total_value DESC
       LIMIT 50
    """,
)


# -----------------------------------------------------------------------------
# Sovereign stack — coverage + per-layer search templates
# -----------------------------------------------------------------------------

SOVEREIGN_STACK_DATA_COVERAGE = block(
    "data_coverage",
    """
    DATA COVERAGE — DEPARTMENT LIMITS (CRITICAL):

    The knowledge graph (`default_`) and `kb_search_nao_reports` contain data ONLY for these
    departments:
    - MOJ (Ministry of Justice)
    - DEFRA (Department for Environment, Food & Rural Affairs)
    - DWP (Department for Work and Pensions)
    - HMRC (HM Revenue & Customs)
    - HO (Home Office)
    - DSIT (Department for Science, Innovation & Technology)
    - DFT (Department for Transport)
    - DFE (Department for Education)
    - CO (Cabinet Office)

    For ANY department NOT in the list (DHSC, MOD, FCDO, DESNZ, NHS, DLUHC, etc.):
    - The graph (`default_`) returns NO results — do not waste calls on it.
    - `kb_search_nao_reports` will also return nothing.
    - Use `kb_search_gats_business_cases` as the primary discovery and evidence tool —
      it covers business cases across ALL of government.
    - Use `kb_search_sr25_bids` and `kb_search_sr21_bids` (cover all departments).
    - Use Athena SQL (contracts, GMPP, spend_controls_data_export) — covers all departments.
    - Use `web_search_gov` for published context.

    CROSS-GOVERNMENT QUESTIONS:
    For aggregate questions (all suppliers, total spend by category, etc.), Athena SQL tables
    cover all departments and are your most complete quantitative source.

    Do NOT assume an entity is absent from government just because the graph does not surface
    it — it may exist in an uncovered department's business cases.
    """,
)


SOVEREIGN_STACK_TEMPORAL_RULES = block(
    "temporal_awareness",
    """
    TEMPORAL AWARENESS — DATING THE EVIDENCE:

    The data sources you query were produced at DIFFERENT POINTS IN TIME. Track the date
    of every piece of evidence and factor currency into your analysis.

    SOURCE DATING:
    - SR21 bids: written ~2020-2021. Historical baseline. A programme described in SR21
      may have been completed, cancelled, re-scoped, or overtaken since.
    - SR25 bids: written ~2024-2025. Most current view of investment intentions.
    - GATS business cases (OBC/SOC/FBC): filed at various dates. Check co_casesubmitdate,
      co_spendstartdate, co_contractenddate.
    - Contracts (Contract Finder / Athena): check date and end_date. A contract that ended
      in 2022 reflects PAST capability; an active contract is CURRENT dependency.
    - GMPP data: 2024-25 dataset — relatively current.
    - NAO reports: publication dates vary. 2023-2025 = strong; 2019-2021 = may describe
      issues since resolved.
    - GOV.UK publications: check publication / last-updated date.
    - Graph entities: inherit dates from their source documents.

    ANALYSIS RULES:
    1. Always record the date (or date range) of each piece of evidence cited.
    2. Weight 2024-2025 evidence more heavily than 2020-2022 for current-state judgements.
    3. Explicitly flag stale evidence (pre-2023) and note the risk that the position has changed.
    4. Distinguish completed vs active: contracts/programmes ending before today are historical.
    5. Use temporal progression: when the same entity appears in SR21 and SR25, describe
       how the position has evolved ("planned in SR21, funded in SR25" vs "funded in SR21
       but absent from SR25 — potentially cancelled or completed").
    6. For investment recommendations, note evidence date — opportunities identified from
       2021 sources may have been acted on or overtaken.
    """,
)


SOVEREIGN_STACK_SEVEN_LAYERS = block(
    "seven_layer_stack",
    """
    SEVEN-LAYER STACK — CANONICAL DEFINITION:

    Bottom-up: Layer 1 = physical foundation, Layer 7 = citizen-facing top.
    Treat governance, security, standards, skills, procurement, capital, and regulation
    as CROSS-CUTTING concerns that affect every layer — not as a separate layer.

    LAYER 1 — PHYSICAL: HARDWARE, SILICON & MATERIALS
      Semiconductors, chip design, fabrication, packaging, rare earths and critical minerals,
      sensors, photonics, hardware and devices.
      Q: Can the UK design, fabricate, package, procure, or substitute core hardware
         and secure materials?

    LAYER 2 — NETWORK & COMMUNICATIONS INFRASTRUCTURE
      Telecoms, fibre, mobile, 5G/6G, critical communications, satellite, undersea/subsea cables.
      Q: Does the UK control resilient infrastructure for moving data and communications?

    LAYER 3 — CLOUD, COMPUTE & PLATFORM
      IaaS / PaaS / SaaS, hyperscale cloud, sovereign compute, HPC, AI compute, storage,
      orchestration.
      Q: Can UK actors access and operate compute at scale without unacceptable dependency?

    LAYER 4 — DATA INFRASTRUCTURE & ANALYTICS
      Data platforms, pipelines, analytics engines, data warehouses / lakes,
      LLM data infrastructure, data governance and provenance.
      Q: Does the UK have usable, trusted, legally accessible data assets and the means
         to process them?

    LAYER 5 — SOFTWARE, APPLICATIONS & AI
      Enterprise SaaS, custom-built applications, AI / foundation / domain models, algorithms.
      Q: Can the UK build, adapt, audit, or influence the core software and AI layer?

    LAYER 6 — INTEGRATION, STANDARDS & INTEROPERABILITY
      APIs, middleware, data standards, identity federation, interoperability frameworks.
      Q: Can the UK set or influence the standards and integration fabric that connect systems?

    LAYER 7 — SERVICE DELIVERY & CITIZEN INTERFACE
      Digital public services, digital identity, user experience, citizen-facing systems
      and adoption.
      Q: Can UK institutions turn capability into trusted, adopted public services and
         market power?
    """,
)


SOVEREIGN_STACK_CONTROL_TEST = block(
    "control_test",
    """
    CONTROL TEST — apply for EACH layer:

    1. LOCATION — Is the asset physically in the UK?
    2. OWNERSHIP — UK-owned, allied-owned, foreign-owned, or state-linked overseas?
    3. OPERATIONAL CONTROL — Who can switch it off, price it, throttle it, deny access,
       or change terms?
    4. SUBSTITUTABILITY — How quickly could the UK replace it?
    5. STRATEGIC CONSEQUENCE — What happens if access is degraded during crisis,
       sanctions, cyberattack, market shock, or export restriction?
    """,
)


SOVEREIGN_STACK_EVIDENCE_METHODOLOGY = block(
    "evidence_methodology",
    """
    EVIDENCE METHODOLOGY — four kinds of evidence per layer:

    A. CAPABILITY — UK companies, research institutions, production assets, compute
       facilities, testbeds, standards bodies, patents, workforce, exports, public-sector
       programmes.
    B. DEPENDENCY — major suppliers, foreign ownership, import reliance, cloud concentration,
       licensing lock-in, export controls, critical components, single points of failure.
    C. DEMAND — government procurement, NHS / defence / energy / transport demand,
       private-sector adoption, startup and scaleup demand, sector-specific use cases.
    D. POLICY LEVERAGE — where government can shift outcomes through procurement, R&D,
       infrastructure, regulation, standards, skills, finance, public data, or international
       partnerships.

    Tool-to-evidence mapping (graph is discovery layer for ALL of these):
    - Discovery (entities, technologies, suppliers, dependencies) -> `default_` FIRST.
    - Capability / demand within government -> graph-found entities enriched via
      `kb_search_gats_business_cases`, `kb_search_sr25_bids`, GMPP and contracts in Athena,
      `web_search_gov`.
    - Dependency -> graph supplier/technology/dependency nodes FIRST, then
      `extracted_contracts` (foreign sellers, hyperscalers, GPU/cloud suppliers),
      `spend_controls_data_export` (direct awards, current/proposed supplier, legacy tech),
      NAO reports on concentration / lock-in.
    - Demand -> GATS spend, SR25 / SR21 bids, GMPP project portfolio, procurement contracts.
    - Policy leverage -> SR25 / SR21 bids (what government is funding), NAO recommendations,
      GOV.UK strategies (semiconductor strategy, AI/compute, data, digital).
    """,
)


SOVEREIGN_STACK_SCORING_MODEL = block(
    "scoring_model",
    """
    SCORING MODEL — for each layer, score the UK 1-5 (1 = very weak, 5 = very strong) on
    each dimension:

    - DOMESTIC CAPABILITY — real capability, not just ambition
    - SCALE — operates at commercially / strategically relevant scale
    - CONTROL — UK controls the IP, assets, operations, or regulatory conditions
    - RESILIENCE — withstands supplier failure, coercion, cyberattack, or export controls
    - SUBSTITUTABILITY — alternative suppliers or domestic fallback options
    - MARKET STRENGTH — UK firms that can sell into domestic and global markets
    - POLICY LEVERAGE — government action could realistically improve the position

    Then CLASSIFY each layer:
    - MAKER: strong capability, control, and scale
    - SHAPER: partial capability or strong influence, but not full-stack control
    - TAKER: material dependence with limited control or substitutability

    Add a CONFIDENCE rating (high / medium / low) reflecting how much evidence the tools
    surfaced. State explicitly when a score is inferred or weakly evidenced.
    """,
)


SOVEREIGN_STACK_INVESTMENT_PRIORITISATION = block(
    "investment_prioritisation",
    """
    INVESTMENT PRIORITISATION MATRIX — score each candidate intervention:

    - STRATEGIC CRITICALITY — would failure affect national security, economic resilience,
      public services, or growth?
    - DEPENDENCY RISK — is the UK exposed to concentration, coercion, export controls,
      or supply shock?
    - UK RIGHT TO WIN — research, firms, talent, institutions, or demand that make
      success plausible?
    - ADDITIONALITY — would intervention unlock something the market will not provide alone?
    - TIME TO IMPACT — 1-3, 3-7, or 7-15 years?
    - SPILLOVERS — would investment strengthen multiple layers of the stack?
    - COST AND FEASIBILITY — realistic investment compared with alternatives?

    Avoid the "make everything" trap. The right answer may be to shape standards,
    diversify allies, create fallback capacity, or dominate a niche rather than build
    full sovereign capability.
    """,
)


SOVEREIGN_STACK_STARTING_HYPOTHESES = block(
    "starting_hypotheses",
    """
    STARTING HYPOTHESES — TEST these against evidence; do not treat them as conclusions.
    Confirm, qualify, or refute each.

    1. Cloud and AI compute are likely high-priority dependency areas — they sit beneath
       models and applications, and UK businesses report dependence on foreign cloud and
       LLM infrastructure.
    2. Semiconductors are foundational but unlikely to be a full-stack "make everything"
       opportunity; the better question is which niches are realistic (design, compound
       semiconductors, photonics, packaging, quantum-adjacent hardware, trusted supply-chain
       partnerships).
    3. Data may be a UK shaper / maker opportunity if public-sector, health, science, and
       industrial datasets can be made usable under trusted governance.
    4. Applications and adoption may be where the UK captures value fastest, especially in
       regulated sectors (health, defence, finance, energy, public services).
    5. Standards, assurance, safety, and regulation are likely UK shaper strengths where the
       UK cannot match US or Chinese scale but can influence trusted deployment.
    """,
)


SOVEREIGN_STACK_GRAPH_PACING = block(
    "graph_pacing_rule",
    """
    GRAPH PACING RULE (mandatory for layer-by-layer sweeps):

    - Call `wait_after_timeout(seconds=10)` BETWEEN every consecutive `default_` call,
      even when the previous call succeeded. Neptune needs brief recovery time between
      traversals.
    - After a MAXIMUM of 5 consecutive `default_` calls, you MUST stop and run at least
      one non-graph tool (KB search, Athena SQL, or web_search_gov) before issuing any
      further `default_` calls. Prevents Neptune from being overwhelmed by sustained
      graph traversal load.
    - The 5-call batch limit resets after a non-graph tool runs. You may then do up to
      5 more graph calls (with waits between each), then must break again.
    - Within a single layer's Steps A + C (graph steps), if you have already used 5 graph
      calls, proceed to Steps D / E / F first, then return to finish remaining graph
      drill-downs after.
    """,
)


SOVEREIGN_STACK_PER_LAYER_STEPS = block(
    "per_layer_execution_steps",
    """
    PER-LAYER EXECUTION SEQUENCE — repeat for L1 through L7 BEFORE synthesising:

    Step A: Graph — entity & technology discovery (run FIRST per layer)
    TOOLS: `default_` ONLY, sequential. Surface what exists for this layer:
      - "Which technologies, platforms, and systems exist for [LAYER TOPIC]? Name each one."
      - "Which suppliers, vendors, and providers are linked to [LAYER TOPIC]?
         Are they UK or overseas?"
      - "Which programmes depend on [LAYER TOPIC] technologies, and what are the dependencies?"
    Use mode="default" for broad sweeps; use business_case_all / sr_bids_all /
    contract_finder_all or department/contract modes to scope when the layer is large.
    COVERAGE NOTE: graph only covers MOJ, DEFRA, DWP, HMRC, HO, DSIT, DFT, DFE, CO.

    Step B: KB supplementary discovery — departments NOT in the graph
    TOOLS: `kb_search_gats_business_cases` ONLY. Capture entities from departments outside
    the nine above:
      - `kb_search_gats_business_cases("[LAYER TOPIC]")` — surface business cases across
        ALL departments. Look for programmes, suppliers, technologies from non-graph depts.
      - Add newly found entities to the layer's entity map, tagged [KB:gats].

    Step C: Graph — dependency & connection drill-down
    TOOLS: `default_` ONLY, sequential. For the highest-value entities found in Steps A-B:
      - "What is connected to [ENTITY]? Which suppliers, programmes, technologies, risks?"
      - "Which entities appear across multiple source types
         (business case + SR bid + contract)?"
      - Cross-cutting: "Which suppliers or platforms recur in multiple departments?"

    Step D: Knowledge Bases — enrich this layer's entities
    TOOLS: `kb_search_*`. For this layer's entities:
      - `kb_search_sr25_bids("[LAYER TOPIC] investment")` — current funding plans
      - `kb_search_sr21_bids("[LAYER TOPIC]")` — historical baseline, trajectory
      - `kb_search_gats_business_cases("[FOUND PROGRAMME / TECHNOLOGY]")` — costs,
        suppliers, detail
      - `kb_search_nao_reports("[FOUND ENTITY / LAYER TOPIC]")` — audit, risk, lock-in
        NOTE: NAO KB covers only the same nine departments as the graph. For other
        departments, use `web_search_gov`.

    Step E: Athena — quantify this layer's dependency and demand
    TOOLS: Athena SQL. Always `get_table_schema` first.
      - `extracted_contracts`: spend by seller_name for this layer's technologies
        (hyperscaler / GPU / cloud concentration), spend by digital_spend_category,
        named_commercial_technologies.
      - `spend_controls_data_export`: direct awards, current/proposed supplier, legacy
        tech flags, AI/emerging-tech flags for this layer's entities.
      - `gmpp_24_25`: major projects in this layer's domain and their scale
        (whole life cost).
    Use LOWER() + LIKE for all text matching. LIMIT 50 unless aggregating.

    Step F: GOV.UK — published context and gap-fill for this layer
    TOOLS: `web_search_gov`. Layer-specific search templates:
      - Layer 1: "UK semiconductor strategy", "UK chip design", "UK critical minerals"
      - Layer 2: "UK telecoms diversification 5G", "UK subsea cables resilience"
      - Layer 3: "UK compute AI strategy", "UK sovereign cloud"
      - Layer 4: "UK data strategy", "UK national data infrastructure"
      - Layer 5: "UK AI strategy foundation models", "UK software"
      - Layer 6: "UK data standards interoperability", "UK digital identity federation"
      - Layer 7: "UK digital public services", "GOV.UK One Login digital identity"
    Flag any judgement that rests primarily on web search.

    Layer Evidence Summary (after Steps A-F):
      - Entities found (technologies, suppliers, programmes) + source tags
      - Key dependencies identified
      - Evidence gaps remaining
      - Preliminary taker / shaper / maker signal (refined later in synthesis)

    Only after ALL seven layers are complete:
      1. Apply the control test to each layer.
      2. Complete the 7-dimension 1-5 scores for each layer.
      3. Classify each layer as taker / shaper / maker with confidence rating.
      4. Identify cross-layer patterns: shared dependencies, concentration risks,
         spillover opportunities.
      5. Run candidate interventions through the prioritisation matrix.
      6. Produce the final structured report per the output format.
    """,
)
