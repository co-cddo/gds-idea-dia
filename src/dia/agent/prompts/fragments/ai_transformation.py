"""AI & Digital Transformation Intelligence Report — prompt fragments.

These blocks hold the AI-transformation-specific content (investigation areas,
AI-focused tool/query framing, methodology, and the full output specification).
They complement — and are used alongside — the shared fragments
(COMMON_TOOLS_AND_SOURCES, ATHENA_SCHEMA_REFERENCE, GRAPH_MODES_REFERENCE,
SERVICE_STANDARD_SOURCE, department_matching_rules) rather than replacing them.

All content is preserved verbatim from the original standalone prompt so no
operational context is lost; the AI-focused framing here layers on top of the
generic canonical references.
"""

from __future__ import annotations

from prompts.fragments.utils import block

# -----------------------------------------------------------------------------
# Investigation areas — the seven-area scope that defines this report
# -----------------------------------------------------------------------------

AI_TRANSFORMATION_INVESTIGATION_AREAS = block(
    "investigation_areas",
    """
    This report covers SEVEN investigation areas. Areas 5 and 6 are the MAIN FOCUS and
    should receive at least 60% of your investigation effort (tool calls). Areas 4 and 7
    are CONDITIONAL — investigate them, but if evidence is absent, include the section
    header with a note explaining what was searched and why evidence is absent.

    1. STRATEGIC CONTEXT — Current context on digital and AI in the organisation: what
       their current digital and AI spend is, existing programmes under way, main efforts
       and strategic plans over the spending review period.
       INVESTIGATE: Total digital/AI spend picture (contracts, GATS pipeline, SR25 asks).
       Existing programmes of work — what is live, what is planned, what is funded.
       Strategic plans articulated in SR25 bids or published strategies. Main digital/AI
       efforts and how they relate to departmental priorities. How the current position
       compares to SR21 baseline (what was promised then vs now).

    2. LEADERSHIP AND GOVERNANCE — How the department is organising and governing its
       digital and AI transformation agenda, including senior accountability, AI
       preparedness arrangements, and decision-making structures.
       INVESTIGATE: Who is accountable for AI/digital transformation (CDO, CTO, SROs).
       Governance structures for AI deployment and oversight. AI preparedness arrangements
       — is there a clear strategy, board-level sponsorship, dedicated AI governance?
       Decision-making structures for AI investment and deployment. Evidence of governance
       frameworks for responsible AI. Whether AI decisions are centralised or distributed.

    3. DELIVERY MODEL — How digital and AI capability is organised and delivered across
       the department, including the roles of central and business teams, use of suppliers,
       delivery partners, and federated versus centralised operating models.
       INVESTIGATE: How is AI/digital work structured — central digital team, distributed
       business units, or hybrid? What is the balance between in-house delivery and
       supplier/partner delivery? Who are the key delivery partners and what do they do?
       Is there a clear operating model for AI or is it ad-hoc? Evidence of federated vs
       centralised approaches. Whether the department builds, buys, or partners for AI.

    4. WORKFORCE CAPABILITY [CONDITIONAL — include findings only if business cases or
       Athena structured data contain relevant evidence; if not, include section header
       with explanation of what was searched and why evidence is absent]
       The department's current digital and AI capability, key skills gaps, workforce
       challenges, and plans to recruit, retain, and develop specialist talent.
       INVESTIGATE: Current AI/data/engineering headcount (if evidenced in business cases,
       SR bids, or Athena data). Skills gaps identified. Recruitment challenges. Ratio of
       permanent to contractor/supplier staff doing AI work. Plans for capability building.
       Whether the department has genuine in-house technical capability or is wholly
       reliant on suppliers for AI work.
       NOTE: The `workforce_commision_26` Athena table holds digital/DDaT workforce
       metrics (FTE, grade/role mix, contractor vs civil-servant resourcing, pay and
       day-rate, diversity) per department/ALB — query it for this area.

    5. CURRENT AI ADOPTION [MAIN FOCUS — allocate maximum investigation effort here]
       The extent to which AI is currently being adopted across the department, including
       access to tools, usage levels, automation activity, and deployment of AI-enabled
       solutions. This section also includes a dedicated contract and supplier dependency
       analysis.
       INVESTIGATE: Which AI tools and platforms are accessible to staff. What frontier
       models are available and through what vehicles. Usage levels — is access broad or
       limited to specific teams? Automation activity — what processes are being automated
       with AI? AI-enabled solutions deployed in production. What is genuinely live vs
       still in pilot. Infrastructure supporting AI workloads (cloud, compute, platforms).
       ALSO INVESTIGATE (contract/supplier analysis): Search contracts for anything
       relating to AI — filter for AI-labelled contracts AND large tech/cloud contracts
       that could underpin AI workloads (e.g. big AWS/Azure/GCP hosting, cloud compute,
       managed infrastructure). Focus on the biggest contracts by value. Identify the
       largest supplier dependencies. Map which platforms are in use, who provides them,
       and what programmes run on them. Assess vendor lock-in risk for each significant
       AI supplier.

    6. PRIORITY USE CASES [MAIN FOCUS — allocate maximum investigation effort here]
       The department's most significant digital and AI use cases, including live
       deployments, pilots and future opportunities, and the outcomes they are intended
       to deliver.
       INVESTIGATE: Every AI/data/ML use case found — name, status, technology, cost,
       supplier, maturity, intended outcomes. Distinguish: live deployments at scale vs
       pilots/PoCs vs pipeline (planned but not yet started). For each significant use
       case: what outcome is it intended to deliver? Is it scaling or stalled? Is it
       funded for continuation? What is the delivery confidence? Cross-reference with
       Service Standard assessments where AI-enhanced services have been assessed.

    7. PRODUCTIVITY AND EFFICIENCY OPPORTUNITIES [CONDITIONAL — include findings only if
       SR bid evidence supports it; if not, include section header with explanation of
       what was searched and why evidence is absent]
       Where digital and AI could drive productivity improvements, workforce optimisation,
       efficiency savings, or service improvements, and the scale of the potential impact.
       INVESTIGATE: Efficiency savings targets in SR25 bids. Productivity improvement
       claims in business cases. Automation opportunities identified but not yet acted on.
       Where AI could reduce headcount requirements, processing times, or operational
       costs. Scale of potential impact if articulated in evidence. Compare what is
       claimed vs what is delivered. Where the department has published an interim
       efficiencies report (SR25 follow-up) or plans for SR27, query
       `kb_search_efficiency_reports` for its stated efficiency-savings focus and plans.

    SUPPORTING LENSES (woven into the areas above, not separate sections):
    - FINANCIAL PICTURE — AI-related spend woven into Area 1 (strategic context) and
      Area 5 (contract analysis). GATS pipeline, SR25 asks, contract values.
    - ASSURANCE AND RISK — Delivery confidence on AI programmes, GATS risk scores,
      NAO/PAC findings. Woven into Area 6 (use cases) and Area 5 (lock-in risk).
    - SERVICE QUALITY — Service Standard assessment outcomes for AI-enhanced services.
      Woven into Area 6 (priority use cases) as validation of delivery.
    """,
)


# -----------------------------------------------------------------------------
# AI-focused tool + source framing (layers AI emphasis on top of the shared
# COMMON_TOOLS_AND_SOURCES / ATHENA_SCHEMA_REFERENCE fragments)
# -----------------------------------------------------------------------------

AI_TRANSFORMATION_KB_FOCUS = block(
    "ai_transformation_kb_focus",
    """
    KNOWLEDGE BASE — AI-FOCUSED USAGE (applies on top of the general KB guidance):

    `kb_search_gats_business_cases`
    Full text of OBCs, SOCs, FBCs from GATS. Use after graph to get verbatim passages:
    exact cost breakdowns by year, full risk registers with likelihood/impact scores,
    options appraisals, benefits realisation plans, governance structures, commercial
    strategy, delivery milestones. FOCUS on business cases relating to AI, data, ML,
    automation, intelligent systems, and agentic workflows.

    `kb_search_sr25_bids`
    Full text of SR25 spending review submissions. Use to get:
    exact RDEL/CDEL by year (25/26 through 28/29), CDEL profiles, efficiency savings
    targets, specific capability commitments, headcount plans, uplift justifications,
    BCR calculations. FOCUS on AI/data investment lines, engineering headcount asks,
    frontier model procurement, and Big Bets target commitments.

    `kb_search_sr21_bids`
    Full text of SR21 submissions — NOT in the graph. Historical baseline.
    Use to: compare SR21 AI/data commitments against SR25 asks, identify AI programmes
    funded in SR21 but absent from SR25 (abandoned?), track how AI programme scope and
    cost evolved, understand what was originally promised for AI/data capability.
    Key question: "what AI/data capability did the department commit to building with
    SR21 money and did it materialise?"

    `kb_search_nao_reports`
    NAO reports and PAC findings — NOT in the graph. Accountability layer.
    Cross-reference EVERY major AI programme, supplier, and capability area found in
    other sources. Search by: (1) AI programme name, (2) AI/data supplier name,
    (3) capability area (e.g. "machine learning", "automation", "data platform"),
    (4) department + "AI" or department + "data".
    Look for: cost overruns on AI/data programmes, delivery failures, systemic issues
    with AI adoption, unacted recommendations, value-for-money judgements on tech spend.

    `kb_search_efficiency_reports`
    Interim efficiencies reports per department (SR25 follow-up) — NOT in the graph.
    Use for Area 7: where the department plans to focus efficiency savings, the scale
    and profile of those savings, and priorities/plans for the upcoming SR27 bids.

    KB usage rules:
    - Use ONLY after graph has surfaced specific entities to investigate
    - For each major AI programme: query business cases KB AND sr25 KB
    - For programmes with SR21 history: query sr21 KB to understand evolution
    - For every major AI programme, supplier, and risk: query nao KB
    """,
)


AI_TRANSFORMATION_SERVICE_STANDARD_CROSS_LENS = block(
    "ai_transformation_service_standard_cross_lens",
    """
    HOW SERVICE STANDARD LINKS TO OTHER SOURCES — CRITICAL CROSS-LENS:
    The Service Standard table is the **user-outcome lens** that complements the financial
    and delivery-confidence lenses. Always triangulate:
    - `service_name` / `service_id` -> match against programmes/projects in graph
      (`default_`) and business-case KB results. A programme named in a business case
      often has a corresponding service assessed here. Use LOWER()/LIKE matching.
    - `department` -> match using the same LOWER()/LIKE patterns as other tables.
    - GMPP `Project Name` -> many GMPP-tracked digital programmes deliver services
      that appear in this table. Cross-reference `gmpp_24_25` Project Name against
      `service_name` here.
    - GATS spend cases -> cases that funded a service build should reconcile with
      the service's stage and outcome. Funded but never reached Beta? Funded but
      failing the Standard? These are flag conditions.
    - TRIANGULATION RULES:
      - Live + Met + low GATS RiskScore + Green GMPP rating -> high-confidence delivery
      - Not Met + Live + high GATS RiskScore + Amber/Red GMPP -> flagged systemic concern
      - Assessed but absent from graph/contracts -> service exists outside the formal
        programme/spend record (worth surfacing)
      - In graph/GATS/GMPP but never assessed -> no independent user-needs validation
    """,
)


# -----------------------------------------------------------------------------
# Required query enumerations (graph / Athena / web)
# -----------------------------------------------------------------------------


def ai_transformation_required_graph_queries(department_name: str = "Home Office") -> str:
    return block(
        "ai_transformation_required_graph_queries",
        f"""
        REQUIRED GRAPH QUERIES (minimum 8, sequential, ONE AT A TIME):

        1. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           — "AI programmes, machine learning, data science, automation, intelligent systems,
           AI use cases, deployed AI solutions, Spend IDs, costs, suppliers" [Areas 5+6]
        2. mode="metadata_filtered_sr_bids_department", entity_name="{department_name}"
           — "AI investment, digital and AI strategic plans, data capability, efficiency
           savings, productivity improvements, AI RDEL CDEL funding asks" [Areas 1+7]
        3. mode="default"
           — "AI contracts, machine learning services, model access procurement, data
           platform contracts, cloud AI services, cloud hosting, compute infrastructure
           for {department_name}" [Area 5 contracts]
        4. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           — "data platforms, analytics infrastructure, AI/ML tooling, model deployment,
           AI-enabled solutions in production, automation activity" [Area 5]
        5. mode="metadata_filtered_business_case_department", entity_name="{department_name}"
           — "AI governance, accountability structures, AI preparedness, decision-making,
           responsible AI, risk governance" [Area 2]
        6. mode="metadata_filtered_sr_bids_department", entity_name="{department_name}"
           — "delivery model, central digital team, business units, suppliers, delivery
           partners, operating model, federated, centralised" [Area 3]
        7. mode="default" — entity drill-down:
           "all suppliers, AI technologies, models, platforms, risks, and costs connected
           to [top AI programme/use case found in earlier queries]" [Area 5+6]
        8. mode="default" — cross-government:
           "which departments are building similar AI capabilities, using the same AI
           suppliers or platforms as {department_name}?" [Cross-gov]

        Use the FALLBACK RULE: if a filtered mode (e.g.
        metadata_filtered_business_case_department) returns no or thin results, IMMEDIATELY
        retry with mode="business_case_all" or mode="default". Documents may be indexed
        under a slightly different department name. Never conclude data is absent until you
        have tried the unfiltered version.
        """,
    )


def ai_transformation_required_athena_queries(department_name: str = "Home Office") -> str:
    return block(
        "ai_transformation_required_athena_queries",
        f"""
        REQUIRED ATHENA QUERIES (minimum 8, sequential, ONE AT A TIME):

        1. `list_athena_tables` — discover all tables
        2. `get_table_schema` for each table before querying
        3. GATS: total requested/approved/risk by department — FOCUS on cases with AI,
           data, machine learning, automation, or intelligent in title/description [Area 1]
        4. SR25: RDEL/CDEL totals and uplifts for the department — identify AI/data-specific
           funding lines [Area 1]
        5. Contracts: top 20 contracts by value with title, seller, and category — include
           ALL large tech/cloud contracts (not just AI-labelled) that could underpin AI
           workloads [Area 5]
        6. Contracts: aggregate spend by seller_name for AI/data/cloud categories — identify
           largest supplier dependencies [Area 5]
        7. Contracts: aggregate spend by digital_spend_category — highlight AI/data/cloud
           categories [Area 5]
        8. Direct awards: SELECT co_organisationsubmitter, co_casename, co_currentsupplier,
           co_proposedsupplier, co_spendamount, co_commercialapproach FROM
           spend_controls_data_export WHERE co_directaward_yesno = 'Yes' — filter to
           AI/data/cloud cases [Area 5 lock-in]
        9. Contract extensions: SELECT co_organisationsubmitter, co_casename,
           co_currentsupplier, co_spendamount FROM spend_controls_data_export WHERE
           co_contractextension_yesno = 'Yes' — filter to AI/data/cloud cases [Area 5 lock-in]
        10. GMPP: all projects for department with IPA confidence, whole life cost, variance
            — flag AI/data/automation programmes [Area 6]
        11. GMPP: projects rated Amber/Red or Red that relate to AI, data, or digital
            transformation [Area 6]
        12. Service Standard: count of assessments by stage and outcome for {department_name}
            — from "gats-assurance".service_assessments_snapshot20251217 [Area 6]
        13. Service Standard: which Standard points (points_notmet_1..11) the department
            most frequently fails to meet — aggregate across all assessments [Area 6]
        14. Workforce (conditional, Area 4): digital/DDaT FTE, grade/role mix, and
            contractor vs civil-servant resourcing for the department from
            assurance_contracts.workforce_commision_26 — match on department /
            department_name / department_alb_combined with LOWER() + LIKE

        DEPARTMENT NAME MATCHING — CRITICAL:
        Data uses inconsistent casing. Always use LOWER() + LIKE with wildcards.
        Never use exact equality (=) for department name filtering.
        Use backticks for hyphenated table names. Wrap hyphenated database names and
        spaced/special column names in double quotes.
        """,
    )


def ai_transformation_web_searches(department_name: str = "Home Office") -> str:
    return block(
        "ai_transformation_web_searches",
        f"""
        REQUIRED GOV.UK SEARCHES (minimum 2, via `web_search_gov`):

        Searches gov.uk/government/publications. Use for published context and verification.
        Use for: departmental AI strategy, data strategy, IPA annual report, AI transformation
        plans, published outcome delivery plans, Big Bets announcements, DSIT AI coordination,
        Future Civil Service Programme, contract award notices for AI services, NAO reports on
        AI/data programmes.

        1. "{department_name} AI strategy" or "{department_name} artificial intelligence" or
           "{department_name} data strategy"
        2. "[major AI programme name from graph] {department_name}"
        """,
    )


# -----------------------------------------------------------------------------
# Investigation methodology (phase-by-phase execution plan)
# -----------------------------------------------------------------------------

AI_TRANSFORMATION_INVESTIGATION_METHOD = block(
    "ai_transformation_investigation_method",
    """
    NON-NEGOTIABLE SEQUENCING AND EXECUTION RULES:

    SEQUENTIAL EXECUTION — CRITICAL:
    - Call tools ONE AT A TIME. Never call two tools in the same turn.
    - Wait for each tool result before calling the next tool.
    - Do NOT batch or parallelize any tool calls — Neptune and Bedrock have concurrency limits.
    - After each `default_` call: read the result, extract entities, then make the next call.
    - This sequential discipline is mandatory. Parallel calls cause timeout failures.

    PHASE ORDER:
    - First 6+ tool calls MUST be `default_` graph queries (one at a time)
    - If filtered mode returns blank -> retry immediately with broader mode (next single call)
    - Start KBs only after 6+ graph queries complete
    - Start Athena only after KB phase is underway
    - Minimum 24 tool calls for a complete report: 8 graph + 6 KB + 8 Athena + 2 web
    - Fewer than 20 total calls will produce an inadequate report

    INVESTIGATION EFFORT ALLOCATION:
    - Areas 5 (Current AI Adoption) and 6 (Priority Use Cases) are MAIN FOCUS — allocate
      at least 60% of your tool calls to investigating these areas.
    - Areas 4 (Workforce) and 7 (Productivity) are conditional — investigate them but do
      not spend more than 1-2 tool calls each unless evidence is rich.

    ---

    PHASE 1 — Graph Broad Sweep — Map the AI & Digital Estate:
    TOOLS: `default_` ONLY. Run all 4 standard queries ONE AT A TIME. Retry blanks with
    broader mode. After EACH call: stop, read output, note entities, then make the next call.
    Goal: Build a raw entity list covering AI programmes, use cases, data platforms,
    suppliers, contracts, governance structures, and delivery model evidence.
    For each query result, note every named entity and which source type it came from.
    Entities appearing across multiple source types are your priority investigations.

    PHASE 2 — Graph Deep Dive — Use Cases, Suppliers, Governance, Delivery:
    TOOLS: `default_` ONLY. Minimum 4 more queries, ONE AT A TIME.
    Run: governance/accountability query (area 2), delivery model query (area 3),
    entity drill-downs for top AI use cases/programmes (areas 5+6), and one
    cross-government query (mode="default") for shared AI suppliers/platforms.
    Goal: Relationship map. For each major AI entity — connections, costs, risks,
    supplier dependencies, governance structures, cross-gov presence.

    PHASE 3 — Knowledge Base Evidence Gathering:
    TOOLS: `kb_search_*`. Minimum 6 calls, ONE AT A TIME.
    For each major AI programme/use case: business cases KB (costs, risks, delivery model)
    + SR25 KB (funding figures, strategic plans, efficiency targets).
    For programmes with SR21 history: SR21 KB (baseline and evolution).
    For all AI programmes, suppliers, and risks: NAO KB (audit record).
    Also search for: workforce/talent evidence (area 4 conditional), governance evidence
    (area 2), productivity/efficiency claims (area 7 conditional — including
    kb_search_efficiency_reports for the interim efficiencies report / SR27 plans).
    Goal: Verbatim evidence to back up graph findings with exact numbers, strategic
    plans, governance structures, and delivery model details.

    PHASE 4 — Athena Financial + Contract/Supplier Analysis:
    TOOLS: `list_athena_tables`, `get_table_schema`, `execute_sql`. Minimum 8 queries, ONE
    AT A TIME.
    Run all standard queries (GATS, SR25, GMPP, Service Standard, and — for area 4 —
    workforce_commision_26). PLUS the dedicated contract/supplier dependency queries:
    - Top contracts by value (AI + large tech/cloud that underpins AI)
    - Aggregate spend by supplier for AI/cloud categories
    - Direct awards for AI/data/cloud cases
    - Contract extensions for AI suppliers found
    Cross-reference every Athena figure against graph findings.
    Goal: Quantified financial picture for AI investment with exact £ figures,
    supplier dependency data for the Platform Dependency Map and Lock-In Assessment,
    and Service Standard validation for use cases.

    PHASE 5 — Cross-Government AI Context:
    TOOLS: `default_` with mode="default" and no department_name filter.
    For top 3 AI suppliers and top 2 AI platforms: who else uses them?
    For key AI capability areas: which departments are building the same thing?
    Which departments use the same cloud/AI platforms?
    Goal: Cross-government AI context — shared suppliers, shared platforms,
    collective procurement leverage, and duplication risk.

    PHASE 6 — Published Context:
    TOOLS: `web_search_gov`. Minimum 2 searches.
    Search for published AI/data/digital strategy and any major AI programme coverage.
    Include GOV.UK links in final report.
    """,
)


# -----------------------------------------------------------------------------
# Output specification (the full report structure)
# -----------------------------------------------------------------------------


def ai_transformation_output_spec(department_name: str = "Home Office") -> str:
    return block(
        "output_format",
        f"""
        Produce a formal AI & Digital Transformation Intelligence Report. Minimum 4,000 words.
        Maximum 10,000 words. Every section must contain specific named entities — no vague
        summaries. This is an intelligence product — not a summary. Build the evidence base
        exhaustively.

        ---

        # AI & DIGITAL TRANSFORMATION INTELLIGENCE REPORT: {department_name.upper()}

        ---

        ## EXECUTIVE SUMMARY AND MATURITY ASSESSMENT

        Provide:
        1. Overall AI & digital transformation maturity assessment — where does {department_name}
           sit on the spectrum from "no meaningful AI activity" to "AI-embedded in operations at scale"?
        2. RAG rating for each of the 7 investigation areas with one-line justification:

           | Area | Rating | Justification |
           |------|--------|---------------|
           | 1. Strategic Context | R/A/G | [one line] |
           | 2. Leadership and Governance | R/A/G | [one line] |
           | 3. Delivery Model | R/A/G | [one line] |
           | 4. Workforce Capability | R/A/G | [one line, or "Insufficient evidence"] |
           | 5. Current AI Adoption | R/A/G | [one line] |
           | 6. Priority Use Cases | R/A/G | [one line] |
           | 7. Productivity/Efficiency | R/A/G | [one line, or "Insufficient evidence"] |

        3. Top three emerging risks (e.g. supplier lock-in, unfunded ambitions, governance gaps,
           platform dependency, skills shortage)
        4. Top three opportunities or strengths
        5. One-paragraph headline: what does the evidence say about this department's AI
           transformation trajectory?

        ---

        ## 1. STRATEGIC CONTEXT

        ### 1.1 Current Digital and AI Context
        - Overall posture: where is the department in its digital/AI journey?
        - Key strategic framing from SR25 bids and published strategies

        ### 1.2 Current Digital and AI Spend
        - Total AI/data contract spend: £Xm across N contracts [ATHENA]
        - Total GATS AI-related pipeline: £Xm requested, £Xm approved [ATHENA]
        - SR25 AI/data funding ask: RDEL £Xm, CDEL £Xm [ATHENA/KB:sr25]
        - SR21 vs SR25 comparison: what was promised then vs what is asked now

        ### 1.3 Existing Programmes Under Way
        - Major AI/digital programmes currently in flight (names, costs, status)
        - What is funded vs unfunded

        ### 1.4 Main Efforts and Strategic Plans
        - Strategic plans articulated in SR25 bids for the spending review period
        - Key ambitions and commitments

        ---

        ## 2. LEADERSHIP AND GOVERNANCE

        ### 2.1 Senior Accountability
        - Who is accountable for AI/digital transformation? (CDO, CTO, named SROs)
        - Board-level sponsorship and engagement

        ### 2.2 AI Preparedness Arrangements
        - Governance frameworks for AI deployment
        - Risk assessment processes for model use
        - Responsible AI governance (evidence of, or absence thereof)

        ### 2.3 Decision-Making Structures
        - How AI investment and deployment decisions are made
        - Centralised vs distributed decision-making
        - Evidence of clear strategy vs ad-hoc approaches

        ---

        ## 3. DELIVERY MODEL

        ### 3.1 Central vs Business Unit Organisation
        - How is AI/digital work structured within the department?
        - Is there a central digital/AI team? What does it own vs what do business units own?

        ### 3.2 Role of Suppliers and Delivery Partners
        - Who are the key delivery partners and what do they do?
        - Balance of in-house vs outsourced delivery
        - Are suppliers building and running AI, or is it genuinely in-house?

        ### 3.3 Federated vs Centralised Operating Model
        - Evidence of operating model choices
        - How AI capability is distributed across the organisation
        - Whether there is a clear, coherent delivery model or fragmentation

        ---

        ## 4. WORKFORCE CAPABILITY [CONDITIONAL]

        NOTE TO AGENT: Only produce substantive findings if business cases, SR bids, or Athena
        structured data (including the workforce_commision_26 table) contain relevant evidence
        about workforce, talent, skills, or capability. If sources do not reference these topics
        for {department_name}, include this section header with a note explaining: what was
        searched, which tools were queried, and why evidence is absent.

        ### 4.1 Current Digital and AI Capability
        - Engineering, data science, AI specialist headcount (if evidenced)
        - Ratio: permanent vs contractor/supplier staff doing AI work

        ### 4.2 Key Skills Gaps
        - Skills gaps identified in business cases or SR bids
        - Which AI/data skills are missing?

        ### 4.3 Workforce Challenges
        - Recruitment challenges, retention issues, pay constraints
        - Competition with private sector for talent

        ### 4.4 Plans to Recruit, Retain, and Develop Specialist Talent
        - Funded plans for capability building
        - Training and upskilling programmes

        ---

        ## 5. CURRENT AI ADOPTION [MAIN FOCUS]

        ### 5.1 Access to AI Tools and Platforms
        - Which AI tools and platforms are accessible to staff?
        - Which frontier models are available and through what vehicles?
        - Is access broad (all staff) or limited to specific teams/pilots?
        - Cloud AI platforms in use (AWS Bedrock, Azure AI, GCP Vertex, etc.)
        - Compute posture: GPU/TPU access, cost, scalability

        ### 5.2 Usage Levels and Automation Activity
        - How widely are AI tools actually being used?
        - What processes are being automated with AI?
        - Measured productivity gains (if any)
        - Is usage growing or plateauing?

        ### 5.3 Deployed AI-Enabled Solutions
        - AI solutions in production (not just pilots)
        - Scale: users, transactions processed, automation rates
        - What is genuinely live vs still in controlled pilot

        ### 5.4 AI Contract and Supplier Dependency Analysis

        This sub-section is MANDATORY. It requires dedicated Athena queries to populate.

        Search contracts for anything relating to AI — filter for explicitly AI-labelled
        contracts AND large tech/cloud contracts that could underpin AI workloads (e.g.
        big AWS/Azure/GCP hosting, cloud compute, managed infrastructure contracts that are
        not labelled "AI" but clearly provide the platform for AI workloads).

        Focus on the biggest contracts by value. Identify the largest supplier dependencies.

        **Table A: AI/Cloud Platform Dependency Map**

        Map which platforms are in use, who provides them, what security classification they
        operate at, and which programmes/systems run on them. List the most significant
        programmes tied to each platform.

        | Platform | Provider | Classification | Key Programmes/Systems |
        |----------|----------|---------------|----------------------|
        | [e.g. Azure UK South] | [e.g. Microsoft] | [Official/Official-Sensitive/Secret] | [Most significant programmes found] |
        | [e.g. AWS Bedrock eu-west-2] | [e.g. Amazon] | [Classification] | [Most significant programmes found] |

        Classification = the security classification the platform operates at (Official /
        Official-Sensitive / Secret). Key Programmes/Systems = the most significant ones only.

        **Table B: AI Vendor Lock-In Risk Assessment**

        For each significant AI/cloud supplier, assess lock-in risk:

        | Supplier | Lock-In Risk | Rationale |
        |----------|-------------|-----------|
        | [Name] | Red/Amber/Green | [Brief explanation covering the factors below] |

        When assessing lock-in risk, the rationale MUST cover whichever of these factors apply:
        - Whether programmes tied to this supplier/platform are approaching **end of service**
          or contract expiry with no replacement funded
        - Whether there are **software licences** that create dependency (proprietary,
          non-transferable, embedded in architecture)
        - Whether there are **significant switching costs** (re-platforming, data migration,
          model re-training, integration rework)
        - Whether there is **dependency on specific infrastructure** for AI workloads (e.g.
          Azure UK South for GPT-4o/LLM inference — what happens if that region or model
          access is unavailable or re-priced?)
        - Whether there are **alternatives** available or whether this is genuinely sole-source
        - Evidence of **direct awards** or **contract extensions** signalling inability to
          re-compete

        ### 5.5 Supplier Concentration Risk Summary
        - Which suppliers hold the most AI contract value?
        - Are there single points of failure?
        - What is the cross-government picture for these suppliers?

        ---

        ## 6. PRIORITY USE CASES [MAIN FOCUS]

        For every significant AI/data/ML use case found, produce an entry:

        **[Use Case Name]** | Spend ID: [X] | Status: [Live / Pilot / Pipeline / At Risk / Stalled]
        - Purpose: what AI/ML capability is being built or deployed
        - AI Technology: models, platforms, tools in use
        - Total Cost: £Xm | RDEL: £Xm | CDEL: £Xm (source)
        - Key Suppliers: [names] — who is building/running it?
        - Scale: users, transactions processed, automation rate if known
        - Maturity: PoC / Alpha / Beta / Live / Scaling
        - SR25 funding: is this use case funded for continuation/scaling?
        - Intended Outcomes: what is this meant to deliver?
        - Key Risks: [from business case or KB evidence]
        - Sources: [GRAPH / KB:gats / KB:sr25 / ATHENA / GOV.UK]

        Group by: Live Deployments at Scale | Pilots and PoCs | Pipeline (planned/seeking funding) | At Risk/Stalled

        ### 6.1 Summary Table
        Table: Use Case | AI Technology | Maturity | Annual Cost £m | Supplier | Intended Outcome

        ### 6.2 Service Standard Validation
        Independent user-needs validation lens. Source: "gats-assurance".service_assessments_snapshot20251217.
        - AI-related services assessed (table: service_name, stage, type, assessment_date, outcome)
        - Pass rate for AI-enhanced services by stage (Alpha / Beta / Live)
        - Most-frequently-failed Service Standard points
        - Cross-link: which assessed services map to AI use cases found in the graph,
          business cases, GMPP, or GATS — and where assessment outcome contradicts
          the delivery-confidence picture

        ---

        ## 7. PRODUCTIVITY AND EFFICIENCY OPPORTUNITIES [CONDITIONAL]

        NOTE TO AGENT: Only produce substantive findings if SR bid evidence (or the interim
        efficiencies report via kb_search_efficiency_reports) supports productivity/efficiency
        claims. If those sources do not reference these topics for {department_name}, include
        this section header with a note explaining: what was searched, which tools were queried,
        and why evidence is absent.

        ### 7.1 Where Digital/AI Could Drive Productivity Improvements
        - Specific opportunities identified in SR25 bids or business cases
        - Automation targets and expected gains

        ### 7.2 Workforce Optimisation Opportunities
        - Where AI could reduce processing times, headcount requirements, or operational burden
        - Evidence of actual vs claimed productivity gains

        ### 7.3 Efficiency Savings or Service Improvements
        - Efficiency savings targets in SR25 bids and the interim efficiencies report
        - Service improvement claims and evidence

        ### 7.4 Scale of Potential Impact
        - Quantified impact estimates (if articulated in evidence)
        - Comparison: what is claimed vs what is being delivered

        ---

        ## 8. CROSS-GOVERNMENT AI INTELLIGENCE

        - Which departments share AI suppliers with {department_name}? Collective leverage?
        - Which departments are building similar AI capabilities? Duplication risk?
        - Which departments use the same AI platforms (e.g. same Azure region, same Bedrock setup)?
        - Shared learning opportunities and mutual dependencies
        - Cross-government AI contracts and frameworks available

        ---

        ## 9. INTELLIGENCE GAPS AND RECOMMENDED ACTIONS

        ### Gaps
        - Data gaps: what was searched, what was absent, what it means
        - Missing evidence: governance frameworks, workforce numbers, platform details
        - SR21 AI orphans: commitments with no SR25 continuation
        - Areas 4 or 7: if marked as insufficient evidence, explain what this means

        ### Recommended Actions
        - Programmes requiring deeper assessment
        - Supplier relationships to scrutinise for lock-in
        - Governance frameworks to establish
        - Platform dependencies to address
        - Workforce interventions needed
        """,
    )


# =============================================================================
# VERSION 2 FRAGMENTS
# -----------------------------------------------------------------------------
# v2 addresses reviewer feedback on the v1 report output:
#   - figures repeated with inconsistent framing (target vs reported) and no
#     named source document
#   - the agent doing its own arithmetic (e.g. applying a % to a £ value) and
#     getting it wrong
#   - contract/supplier sums that did not reconcile across the report
#     (same contracts combined to different totals in different sections)
#   - the same programme / finding restated in multiple sections
#   - government-wide figures and targets presented without any link to the
#     requested department
#
# v2 layers new discipline + reference rules on top and swaps in a revised
# output spec. v1 fragments above are left untouched.
# =============================================================================


AI_TRANSFORMATION_REPORTING_DISCIPLINE = block(
    "reporting_discipline",
    """
    REPORTING DISCIPLINE — HIGHEST PRIORITY. These rules override any conflicting
    instruction in the output specification below. The purpose of this report is to
    serve every relevant fact to a human analyst on a platter: each fact stated once,
    cleanly sourced, with no duplication and no invented arithmetic.

    ------------------------------------------------------------------------
    1. NO CALCULATIONS — ABSOLUTE
    ------------------------------------------------------------------------
    - Report figures ONLY as they are stated verbatim in a source.
    - NEVER sum, subtract, multiply, divide, take a percentage of, compute a delta,
      annualise, extrapolate, or otherwise derive any number.
    - NEVER combine two or more figures into a total unless a single source already
      states that exact combined total. If a source lists £A and £B separately, present
      them separately — do NOT write "£A+B" or a combined figure.
    - A percentage is NOT a licence to calculate. If a source states "30%", quote "30%"
      exactly as stated, attribute it, and STOP. Do NOT apply it to any £ value to
      produce a savings/impact figure. Applying a stated % to a stated £ amount is a
      calculation and is forbidden.
    - If the analytically useful number would require a calculation, state the inputs
      verbatim with their sources and write: "combined figure not stated in source".

    ------------------------------------------------------------------------
    2. EVERY FIGURE NAMES ITS SOURCE DOCUMENT (and carries a [n] reference)
    ------------------------------------------------------------------------
    - Every figure, target, date, contract value, headcount, and named claim must carry
      an inline numbered reference marker: [1], [2], [3] ... (see reference_rules).
    - The reference must resolve to a specific named source DOCUMENT — e.g. the exact
      NAO report title and year, the specific SR25 bid, the named business case, or the
      Athena table + query. "A target of 30%" with no named document is forbidden.
    - Distinguish a TARGET from a REPORTED / ACTUAL figure using the source's own
      language. If the source calls it a target, call it a target; if it is an
      outturn/actual, say so. Never silently convert a target into an achievement or
      vice versa. Never call a figure "a target" unless the source labels it one.

    ------------------------------------------------------------------------
    3. INTERNAL SOURCES TAKE PRECEDENCE OVER GOV.UK
    ------------------------------------------------------------------------
    - Source precedence (highest first): internal structured data (Athena) and internal
      documents (GATS business cases, SR25/SR21 bids, NAO/PAC, efficiency reports,
      Service Standard) > GOV.UK published material.
    - Lead every quantitative claim with the internal figure. Use GOV.UK only for
      published context, narrative framing, and verification.
    - Where an internal source and GOV.UK disagree or overlap, present the internal
      figure as primary, note the GOV.UK figure as secondary, and flag the conflict
      explicitly. NEVER average, reconcile, or blend conflicting figures.

    ------------------------------------------------------------------------
    4. STATE EACH FACT ONCE — MECE, NO DUPLICATION
    ------------------------------------------------------------------------
    - Every programme, contract, supplier, figure, use case, target, and finding is
      stated IN FULL in exactly ONE home section (its most natural home).
    - Everywhere else it is relevant, reference it by name and section number only
      (e.g. "the Home Office Biometrics programme (see 6, entry HOB)"). Do NOT restate
      its cost, description, status, or supplier a second time.
    - Do not repeat the same contextual finding across sections. A finding such as
      "the department has no dedicated AI line in its SR25 bid" is stated ONCE, in its
      home section, and referenced thereafter — never restated multiple times.
    - Before finalising, scan for duplication: if the same number or sentence appears in
      two places, delete the second occurrence and replace it with a cross-reference.
    - Sections must be mutually exclusive and collectively exhaustive. Where a clear link
      between data sources exists, state it. Where sources cannot be reconciled into one
      picture, say so explicitly rather than forcing or duplicating.

    ------------------------------------------------------------------------
    5. CONTRACT & SUM CONSISTENCY — SINGLE CANONICAL LEDGER
    ------------------------------------------------------------------------
    This is critical and the report is judged on it.
    - Build ONE canonical contract ledger, once, from Athena, before writing any prose.
      One row per contract: exact contract/title, supplier, exact value as stated, and
      source reference. This ledger is the SINGLE SOURCE OF TRUTH.
    - Every mention of a contract or supplier value anywhere in the report must match the
      ledger exactly — same value, same count, same names. No drift between sections.
    - State explicitly and consistently: HOW MANY contracts there are, WHAT each one is,
      and WHAT each one is worth. If it is unclear how many contracts underlie a figure,
      say so — do NOT paper over it with a combined number.
    - NEVER present a combined/aggregate contract total (e.g. a single "£670m" for
      AWS + SageMaker) unless a source states that combined total. If you only have
      individual values, list them individually and label any total as
      "not stated in source — individual values shown".

    ------------------------------------------------------------------------
    6. DEPARTMENT-SPECIFIC FIGURES ONLY
    ------------------------------------------------------------------------
    - Every figure, target, and statement of scale must be about the REQUESTED department.
    - Do NOT report government-wide numbers or cross-government targets (e.g. civil-
      service-wide savings targets, DSIT/centre-set AI ambitions, "Big Bets" totals)
      unless the figure is explicitly attributed to the requested department in a source.
    - Cross-government material is limited to relationships only (shared suppliers,
      shared platforms, named comparators) — see the Cross-Government section. It must
      contain NO government-wide figures or targets.
    - If a source only gives a government-wide number, either omit it or state clearly
      that it is government-wide and that no department-specific figure was found — never
      present it as if it were the department's number, and never derive the department's
      share from it (that would be a calculation, see rule 1).

    ------------------------------------------------------------------------
    7. BREAK EACH THEME DOWN BY DATA SOURCE
    ------------------------------------------------------------------------
    - Within each of the investigation-area sections, attribute findings to the data
      source they came from so a human can see exactly which source supports each fact
      and can spot gaps.
    - Where the section supports it, group findings under the contributing sources
      (Graph / GATS / SR25 / SR21 / NAO / Efficiency report / Athena contracts / GMPP /
      Service Standard / GOV.UK), and state where a source returned nothing for that
      theme.
    """,
)


AI_TRANSFORMATION_REFERENCE_RULES = block(
    "reference_rules",
    """
    CITATION & REFERENCING — NUMBERED [n] SCHEME:

    - Use inline numbered reference markers throughout: [1], [2], [3] ...
    - Assign each distinct SOURCE DOCUMENT (or Athena table+query) a stable number the
      first time it is cited, and reuse that same number everywhere it recurs. Do NOT
      give the same document two different numbers.
    - Multiple references on one claim: [2][5]. A claim corroborated by several sources
      cites all of them (this signals higher confidence).
    - Every figure, target, date, value, and named claim MUST carry at least one [n].
    - Do NOT use inline [TAG] style ([GRAPH], [KB:gats], etc.) in the body prose — the
      source TYPE is captured in the reference list instead. Keep the body clean with
      only [n] markers.

    FINAL SECTION — REFERENCES (mandatory, appears last, before Source Diagnostics):
    A single numbered list mapping every [n] used in the report to its source. Format:

    | # | Source type | Document / table | Date | What it evidences |
    |---|-------------|------------------|------|-------------------|
    | 1 | NAO | <exact report title> | <year> | 30% figure; VfM finding on X |
    | 2 | KB:sr25 | <department> SR25 bid | 2024/25 | RDEL/CDEL asks for programme Y |
    | 3 | ATHENA | assurance_contracts.<table> — top contracts by value | data as at <date> | Canonical contract ledger |
    | 4 | GOV.UK | <publication title + URL> | <pub date> | Published AI strategy context |

    Source type is one of: GRAPH, KB:gats, KB:sr25, KB:sr21, KB:nao, KB:efficiency,
    ATHENA, ATHENA:service-standard, GOV.UK. Every number used in the report must trace
    to a row here. If a claim cannot be tied to a specific source, remove it.
    """,
)


AI_TRANSFORMATION_KB_FOCUS_V2 = block(
    "ai_transformation_kb_focus",
    """
    KNOWLEDGE BASE — AI-FOCUSED USAGE (applies on top of the general KB guidance):

    `kb_search_gats_business_cases`
    Full text of OBCs, SOCs, FBCs from GATS. Use after graph to get verbatim passages:
    exact cost breakdowns by year (quote them verbatim — do not re-total them), full
    risk registers with likelihood/impact scores, options appraisals, benefits
    realisation plans, governance structures, commercial strategy, delivery milestones.
    FOCUS on business cases relating to AI, data, ML, automation, intelligent systems,
    and agentic workflows.

    `kb_search_sr25_bids`
    Full text of SR25 spending review submissions. Use to get:
    exact RDEL/CDEL by year (25/26 through 28/29) as stated, CDEL profiles, efficiency
    savings targets (quote as stated, and label as targets), specific capability
    commitments, headcount plans, uplift justifications. Do NOT recompute BCRs or any
    other ratio — quote only figures the bid itself states. FOCUS on AI/data investment
    lines, engineering headcount asks, and frontier model procurement, all scoped to the
    requested department only.

    `kb_search_sr21_bids`
    Full text of SR21 submissions — NOT in the graph. Historical baseline.
    Use to: compare (qualitatively) SR21 AI/data commitments against SR25 asks, identify
    AI programmes funded in SR21 but absent from SR25 (abandoned?), track how AI
    programme scope evolved. Report the SR21 figure and the SR25 figure side by side as
    stated — do NOT compute the delta between them.
    Key question: "what AI/data capability did the department commit to building with
    SR21 money and did it materialise?"

    `kb_search_nao_reports`
    NAO reports and PAC findings — NOT in the graph. Accountability layer.
    When you cite an NAO/PAC figure or judgement, name the exact report and year and give
    it a [n] reference. Only report figures the report attributes to the requested
    department; if a figure is government-wide, say so and do not present it as the
    department's own (and never derive the department's share — that is a calculation).
    Cross-reference EVERY major AI programme, supplier, and capability area found in
    other sources by: (1) AI programme name, (2) supplier name, (3) capability area,
    (4) department + "AI"/"data".

    `kb_search_efficiency_reports`
    Interim efficiencies reports per department (SR25 follow-up) — NOT in the graph.
    Use for Area 7: where the department plans to focus efficiency savings, and the
    scale/profile of those savings AS STATED (do not compute), and priorities for SR27.

    KB usage rules:
    - Use ONLY after graph has surfaced specific entities to investigate.
    - For each major AI programme: query business cases KB AND sr25 KB.
    - For programmes with SR21 history: query sr21 KB to understand evolution.
    - For every major AI programme, supplier, and risk: query nao KB.
    - Internal KB/Athena figures take precedence over GOV.UK (see reporting_discipline).
    """,
)


def ai_transformation_output_spec_v2(department_name: str = "Home Office") -> str:
    return block(
        "output_format",
        f"""
        Produce a formal AI & Digital Transformation Intelligence Report. Minimum 4,000
        words. Maximum 10,000 words. Every section must contain specific named entities —
        no vague summaries. This is an intelligence product built to serve every relevant
        fact to a human analyst on a platter.

        READ FIRST — this output spec is subordinate to <reporting_discipline> and
        <reference_rules>. In particular:
        - State every fact ONCE in its home section; cross-reference elsewhere by name and
          section number. Never restate a number, description, or finding.
        - Do NOT perform any calculation. Quote figures verbatim with a [n] reference to a
          named source document.
        - Use ONE canonical contract ledger (built in 5.4) as the single source of truth
          for every contract/supplier value mentioned anywhere in the report.
        - Report department-specific figures only. No government-wide numbers or targets.
        - Attribute findings to their data source within each section.

        ---

        # AI & DIGITAL TRANSFORMATION INTELLIGENCE REPORT: {department_name.upper()}

        ---

        ## EXECUTIVE SUMMARY AND MATURITY ASSESSMENT

        Provide:
        1. Overall AI & digital transformation maturity assessment for {department_name} —
           where does it sit from "no meaningful AI activity" to "AI embedded at scale"?
        2. RAG rating for each of the 7 investigation areas with one-line justification:

           | Area | Rating | Justification |
           |------|--------|---------------|
           | 1. Strategic Context | R/A/G | [one line] |
           | 2. Leadership and Governance | R/A/G | [one line] |
           | 3. Delivery Model | R/A/G | [one line] |
           | 4. Workforce Capability | R/A/G | [one line, or "Insufficient evidence"] |
           | 5. Current AI Adoption | R/A/G | [one line] |
           | 6. Priority Use Cases | R/A/G | [one line] |
           | 7. Productivity/Efficiency | R/A/G | [one line, or "Insufficient evidence"] |

        3. Top three emerging risks (e.g. supplier lock-in, unfunded ambitions, governance
           gaps, platform dependency, skills shortage).
        4. Top three opportunities or strengths.
        5. One-paragraph headline on the department's AI transformation trajectory.
        Every figure quoted here must be stated verbatim from a named source [n]; do not
        compute any headline number (including any "scale of savings").

        ---

        ## 1. STRATEGIC CONTEXT

        ### 1.1 Current Digital and AI Context
        - Overall posture and key strategic framing (SR25 bids, published strategies).

        ### 1.2 Current Digital and AI Spend (department-specific, quoted only)
        - Total AI/data contract spend AS STATED — cross-reference the canonical ledger in
          5.4; do NOT re-total here. Give the count of contracts and the ledger reference.
        - GATS AI-related pipeline figures as stated: £X requested, £X approved [n].
        - SR25 AI/data funding ask as stated: RDEL £X, CDEL £X [n].
        - SR21 vs SR25: state each figure side by side as stated — do NOT compute the delta.
        Present figures grouped by source (Athena contracts / GATS / SR25 / SR21).

        ### 1.3 Existing Programmes Under Way
        - Major AI/digital programmes currently in flight — name, home-section pointer to
          full detail in Section 6, funded vs unfunded status. State each programme ONCE
          here at a summary level; full use-case detail lives in Section 6 only.

        ### 1.4 Main Efforts and Strategic Plans
        - Strategic plans and commitments articulated in SR25 bids for the SR period.

        ---

        ## 2. LEADERSHIP AND GOVERNANCE

        ### 2.1 Senior Accountability
        - Who is accountable (CDO, CTO, named SROs); board-level sponsorship.

        ### 2.2 AI Preparedness Arrangements
        - Governance frameworks for AI deployment; risk assessment for model use;
          responsible-AI governance (evidence of, or documented absence).

        ### 2.3 Decision-Making Structures
        - How AI investment/deployment decisions are made; centralised vs distributed;
          clear strategy vs ad-hoc. Attribute each finding to its source.

        ---

        ## 3. DELIVERY MODEL

        ### 3.1 Central vs Business Unit Organisation
        ### 3.2 Role of Suppliers and Delivery Partners
        - In-house vs outsourced balance. Reference supplier values from the 5.4 ledger;
          do not restate contract sums here.
        ### 3.3 Federated vs Centralised Operating Model

        ---

        ## 4. WORKFORCE CAPABILITY [CONDITIONAL]

        NOTE TO AGENT: Produce substantive findings only if business cases, SR bids, or
        Athena structured data (including workforce_commision_26) contain relevant
        evidence for {department_name}. If not, include this header with a note stating
        what was searched, which tools were queried, and why evidence is absent.

        ### 4.1 Current Digital and AI Capability (headcount as stated, not derived)
        ### 4.2 Key Skills Gaps
        ### 4.3 Workforce Challenges
        ### 4.4 Plans to Recruit, Retain, and Develop Specialist Talent

        ---

        ## 5. CURRENT AI ADOPTION [MAIN FOCUS]

        ### 5.1 Access to AI Tools and Platforms
        - Tools/platforms accessible to staff; frontier models available and via what
          vehicles; breadth of access; cloud AI platforms; compute posture.

        ### 5.2 Usage Levels and Automation Activity
        - How widely tools are used; processes automated; usage trend. Quote any measured
          figures verbatim [n]; do not compute rates.

        ### 5.3 Deployed AI-Enabled Solutions
        - Solutions in production vs pilot; scale figures as stated.

        ### 5.4 AI Contract and Supplier Dependency Analysis — CANONICAL LEDGER

        This sub-section is MANDATORY and is built FIRST, before any other section quotes a
        contract value. It establishes the single source of truth for all contract/supplier
        figures in the report. Run the dedicated Athena contract queries to populate it.

        Scope: explicitly AI-labelled contracts AND large tech/cloud contracts that could
        underpin AI workloads (e.g. large AWS/Azure/GCP hosting, cloud compute, managed
        infrastructure not labelled "AI" but clearly providing the AI platform). Focus on
        the biggest contracts by value, for {department_name} only.

        **Table 0: Canonical Contract Ledger (single source of truth)**
        One row per contract. Every other mention of a contract/supplier value in this
        report MUST match this table exactly. Do NOT add a total row unless a source states
        the combined total; if you show a total, label it and cite it.

        | # | Contract / title | Supplier | Value (as stated) | Source [n] |
        |---|------------------|----------|-------------------|-----------|

        State in prose immediately after the table: how many contracts are listed, and
        whether their values are stated individually or combined in any source. If a
        headline figure (e.g. a single supplier total) exists in a source, cite it and its
        source [n]; otherwise state "combined total not stated in source".

        **Table A: AI/Cloud Platform Dependency Map** (references the ledger — no new sums)

        | Platform | Provider | Classification | Key Programmes/Systems |
        |----------|----------|---------------|----------------------|

        Classification = security classification the platform operates at (Official /
        Official-Sensitive / Secret). Key Programmes/Systems = the most significant only,
        cross-referenced to Section 6 by name.

        **Table B: AI Vendor Lock-In Risk Assessment**

        | Supplier | Lock-In Risk | Rationale |
        |----------|-------------|-----------|

        Rationale MUST cover whichever apply: programmes approaching end of service/contract
        expiry with no replacement funded; proprietary/non-transferable licences;
        significant switching costs; dependency on specific infrastructure for AI workloads;
        availability of alternatives vs sole-source; evidence of direct awards or contract
        extensions signalling inability to re-compete. All values referenced from Table 0.

        ### 5.5 Supplier Concentration Risk Summary
        - Which suppliers hold the most AI contract value (per Table 0, no re-totalling);
          single points of failure. Cross-government presence is noted by name only and
          moved to Section 8 — no cross-gov figures here.

        ---

        ## 6. PRIORITY USE CASES [MAIN FOCUS]

        This is the HOME section for every use case. Each use case is described in full here
        exactly once; other sections reference it by name and "see 6".

        For every significant AI/data/ML use case found, produce an entry:

        **[Use Case Name]** | Spend ID: [X] | Status: [Live / Pilot / Pipeline / At Risk / Stalled]
        - Purpose: what AI/ML capability is being built or deployed
        - AI Technology: models, platforms, tools in use
        - Cost: quote RDEL/CDEL/total AS STATED with [n] — do not sum or derive
        - Key Suppliers: [names] — reference values from the 5.4 ledger, do not restate sums
        - Scale: users/transactions/automation rate if stated
        - Maturity: PoC / Alpha / Beta / Live / Scaling
        - SR25 funding: funded for continuation/scaling? (as stated)
        - Intended Outcomes; Key Risks
        - References: [n][n]

        Group by: Live Deployments at Scale | Pilots and PoCs | Pipeline | At Risk/Stalled.
        List each use case under ONE group only.

        ### 6.1 Summary Table
        Use Case | AI Technology | Maturity | Annual Cost £m (as stated) | Supplier | Intended Outcome

        ### 6.2 Service Standard Validation
        Source: "gats-assurance".service_assessments_snapshot20251217.
        - AI-related services assessed (service_name, stage, type, assessment_date, outcome)
        - Counts by stage/outcome as returned (do not compute pass rates unless the source
          provides them)
        - Most-frequently-failed Service Standard points
        - Cross-link: which assessed services map to use cases above, and where the outcome
          contradicts the delivery-confidence picture.

        ---

        ## 7. PRODUCTIVITY AND EFFICIENCY OPPORTUNITIES [CONDITIONAL]

        NOTE TO AGENT: Produce substantive findings only if SR bid evidence (or the interim
        efficiencies report via kb_search_efficiency_reports) supports productivity/
        efficiency claims for {department_name}. If not, include this header with a note on
        what was searched and why evidence is absent.

        ### 7.1 Where Digital/AI Could Drive Productivity Improvements (as stated)
        ### 7.2 Workforce Optimisation Opportunities
        ### 7.3 Efficiency Savings or Service Improvements
        - Efficiency savings targets in SR25 bids and the interim efficiencies report,
          QUOTED as stated and labelled as targets, with [n]. Do NOT apply any % to any £
          value to produce a savings figure.
        ### 7.4 Scale of Potential Impact
        - Report ONLY impact figures the source itself states, verbatim, with [n]. If the
          source gives a % and a separate £ base, present both separately and state that a
          combined impact figure is not stated in source. Compare claimed vs delivered
          using stated figures only.

        ---

        ## 8. CROSS-GOVERNMENT AI INTELLIGENCE (relationships only — NO figures)

        This section contains NO government-wide figures and NO targets. Named
        relationships only, all anchored to {department_name}:
        - Which departments share AI suppliers with {department_name} (name the shared
          supplier and the departments) — collective-leverage relationships.
        - Which departments are building similar AI capabilities (duplication risk) — named.
        - Which departments use the same AI platforms (e.g. same Azure region/Bedrock setup).
        - Shared learning opportunities and mutual dependencies, named.
        Do not state any spend figure, target, or scale number in this section.

        ---

        ## 9. INTELLIGENCE GAPS AND RECOMMENDED ACTIONS

        ### Gaps
        - Data gaps: what was searched, what was absent, what it means.
        - Missing evidence; SR21 AI orphans (commitments with no SR25 continuation, stated
          side by side, not computed); Areas 4/7 insufficient-evidence explanations.

        ### Recommended Actions
        - Programmes for deeper assessment; supplier relationships to scrutinise for
          lock-in; governance frameworks to establish; platform dependencies; workforce
          interventions.

        ---

        ## REFERENCES
        The numbered reference list per <reference_rules>. Every [n] used above resolves to
        exactly one row here. This section is mandatory and appears before Source Diagnostics.
        """,
    )
