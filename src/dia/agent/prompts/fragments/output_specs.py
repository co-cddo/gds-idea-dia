from __future__ import annotations

from prompts.fragments.utils import block

COMMON_OUTPUT_RULES = block(
    "output_rules",
    """
    OUTPUT RULES:
    - Use a professional analytical tone.
    - Be direct, specific, and well structured.
    - Avoid vague summary language.
    - Include named entities wherever evidence supports them.
    - Distinguish confirmed findings from inference and from gaps.
    - End with clear intelligence gaps / recommended next questions where relevant.
    - No emojis.
    """,
)


COMMON_CITATION_RULES = block(
    "citation_rules",
    """
    CITATION RULES:
    - Tag every factual claim with a source marker.
    - Never fabricate a figure, Spend ID, programme name, supplier relationship, or date.
    - If data is absent or uncertain, state that explicitly.
    - Note when an entity appears across multiple sources, as this increases confidence.
    - Include specific document names, Spend IDs, CaseRefNos, contract values, and entity
      names inline.

    Expected source tags:
    [GRAPH], [KB:gats], [KB:sr25], [KB:sr21], [KB:nao], [ATHENA], [ATHENA:service-standard], [GOV.UK]
    """,
)


SOURCE_DIAGNOSTICS = block(
    "source_diagnostics",
    """
    SOURCE DIAGNOSTICS — include in every report:

    ### Tool Call Log
    | Tool | Query / Parameters | Results | Useful? | Key Entities Found |
    |------|--------------------|---------|---------|--------------------|

    ### Confidence Levels
    - High (3+ sources): [list]
    - Medium (2 sources): [list]
    - Low (1 source): [list]
    - Not found: [list what was searched for but absent]

    Summary metrics:
    - Total `default_` (graph) calls: [N]
    - Total KB calls: [N] (gats: X, sr25: X, sr21: X, nao: X)
    - Total Athena queries: [N]
    - Total web searches: [N]
    - Sources that returned NO useful data: [list]
    - Entities found in multiple sources (high confidence): [list]
    - Entities found in single source only (lower confidence): [list]
    """,
)


# -----------------------------------------------------------------------------
# DBR — section list and detailed output card
# -----------------------------------------------------------------------------

DBR_OUTPUT_SPEC = block(
    "output_format",
    """
    Produce a formal Digital Business Review.

    Required sections (use these exact headings):
    - Executive Summary
    - Digital Programme Portfolio
    - Technology Estate
    - Commercial and Supplier Landscape
    - Financial Picture
    - Assurance and Risk
    - Service Quality and User Outcomes
    - Cross-Government Intelligence
    - Published Context
    - Intelligence Gaps and Recommended Actions
    - Source Diagnostics

    Expectations:
    - every major programme should be named if found
    - every major supplier should be named if found
    - quantitative sections must use Athena-backed figures where available
    - service quality section should use service assessment evidence where available
    """,
)


def dbr_output_card(department_name: str = "Home Office") -> str:
    return block(
        "dbr_output_card_templates",
        f"""
        FORMAL DIGITAL BUSINESS REVIEW — REQUIRED OUTPUT STRUCTURE

        Every section must contain specific named entities — no vague summaries.
        Use the exact section headings below.

        # DIGITAL BUSINESS REVIEW: {department_name.upper()}

        ## EXECUTIVE SUMMARY
        1. Overall digital health assessment
        2. Top three risks or concerns requiring attention
        3. Top three strengths or opportunities

        ## 1. DIGITAL PROGRAMME PORTFOLIO
        For every programme, produce an entry:

        **[Programme Name]** | Spend ID: [X] | Status: [Active / Pipeline / At Risk / Completed]
        - Purpose: what the programme does
        - Total Cost: £Xm | RDEL: £Xm | CDEL: £Xm (source)
        - Key Suppliers: [names] (source)
        - Technology: [platforms / systems] (source)
        - GATS Risk Score: [X] | GMPP IPA Rating: [Green / Amber / Red]
        - SRO: [name if known]
        - SR21 History: [what was originally planned / funded]
        - Key Risks: [from business case or KB evidence]
        - Sources: [GRAPH / KB:gats / KB:sr25 / ATHENA / GOV.UK]

        Group by: In-Flight | Pipeline | At Risk | Completed.

        ## 2. TECHNOLOGY ESTATE
        ### 2.1 Core Platforms and Systems
        Table: Platform | Type (legacy / modern / cloud) | Dependent programmes | Status

        ### 2.2 Cloud and Infrastructure
        ### 2.3 Data and AI Capabilities
        ### 2.4 Legacy Debt

        ## 3. COMMERCIAL AND SUPPLIER LANDSCAPE
        ### 3.1 Key Suppliers
        For each significant supplier:

        **[Name]** | Total Contract Value: £Xm [ATHENA] | Contracts: N
        - Programmes served: [list] [GRAPH]
        - Technology areas: [categories]
        - Also serves: [other departments] [GRAPH]
        - Dependency risk: [assessment]

        ### 3.2 Concentration Risk
        ### 3.3 Spend by Category
        Table: digital_spend_category | Total £m | Contract count [ATHENA]

        ## 4. FINANCIAL PICTURE
        ### 4.1 Total Digital Spend Summary
        Contract spend total | GATS pipeline total | GMPP whole life cost total

        ### 4.2 SR25 vs SR21
        RDEL: SR25 ask £Xm vs SR21 settlement £Xm (delta)
        CDEL: SR25 ask £Xm vs SR21 settlement £Xm (delta)
        Key uplift justifications. SR21 commitments not continued in SR25.

        ### 4.3 GATS Approval Pipeline
        Requested vs approved. Risk score distribution. Approval rate.

        ### 4.4 GMPP Delivery Variances
        Table: Project | WLC Baseline £m | WLC Forecast £m | Variance % | IPA Rating

        ## 5. ASSURANCE AND RISK
        ### 5.1 IPA / GMPP Delivery Confidence
        ### 5.2 GATS Risk Profile
        ### 5.3 NAO and PAC Findings
        ### 5.4 Systemic Risks
        ### 5.5 Service Quality — GDS Service Standard
        Source: "gats-assurance".service_assessments_snapshot20251217.
        - Services assessed (table: service_name, stage, type, assessment_date, outcome)
        - Pass rate by stage (Alpha / Beta / Live)
        - Most-frequently-failed Service Standard points across the department
          (aggregate across points_notmet_1 .. points_notmet_11)
        - Cross-link table: which assessed services map to programmes from the graph,
          business cases, GMPP `Project Name`, or GATS cases — and where outcomes
          contradict the financial / delivery-confidence picture (e.g. funded + Green
          GMPP but failing the Standard, or Live + Met with no graph / contracts trace).

        ## 6. CROSS-GOVERNMENT INTELLIGENCE
        Shared suppliers — collective negotiating leverage.
        Capability duplication.
        Shared service opportunities.
        Cross-departmental dependencies.

        ## 7. PUBLISHED CONTEXT
        Published digital strategies and plans [GOV.UK links].
        IPA published findings. Published evaluations.

        ## 8. INTELLIGENCE GAPS AND RECOMMENDED ACTIONS
        Data gaps: what was searched, what was absent, what it means.
        SR21 orphans: commitments with no SR25 continuation.
        Recommended: programmes for deep-dive assurance, commercial relationships to
        scrutinise, data investments requiring maturity assessment.
        """,
    )


# -----------------------------------------------------------------------------
# Default investigation
# -----------------------------------------------------------------------------

DEFAULT_OUTPUT_SPEC = block(
    "output_requirements",
    """
    Produce a detailed intelligence briefing.

    Minimum sections:
    - Executive Summary
    - Digital Programme Portfolio
    - Supplier / Vendor Landscape
    - Technology / Platform Map
    - Financial Analysis
    - Risk / Assurance Assessment
    - Cross-Government Intelligence
    - Published Context
    - Intelligence Gaps & Recommendations
    - Data Source Diagnostics
    """,
)


# -----------------------------------------------------------------------------
# Project investigation card
# -----------------------------------------------------------------------------

PROJECT_OUTPUT_SPEC = block(
    "output_format",
    """
    Required sections:
    1. Project Summary Card
    2. Cross-Source Evidence Map
    3. Connections and Dependencies
    4. Risk and Assurance Summary
    5. Neptune Cypher Query for Visualisation
    """,
)


PROJECT_OUTPUT_CARD = block(
    "project_output_card",
    """
    ## 1. Project Summary Card

    | Field | Value |
    |-------|-------|
    | Project Name | [as found] |
    | Alternative Names | [variations found across sources] |
    | Department | [org] |
    | Spend ID(s) | [COSC-XXXXX] |
    | Status | [case status / project status] |
    | Total Spend / Value | [£Xm] |
    | SRO | [name] |
    | Key Suppliers | [list] |
    | Start Date | [date] |
    | End Date | [date] |

    ## 2. Cross-Source Evidence Map
    For each data source, report what was found:
    - Knowledge Graph (Neptune): entities + relationships + cross-source links
    - GATS Spend Controls: case details, approval status, risk rating, AI / GMPP / legacy flags
    - Contracts (Athena): related contracts, values, suppliers, lifecycle
    - GMPP: IPA confidence, whole life cost, financial variance, schedule narrative
    - Business Cases (KB): scope, costs, risks, benefits, options appraisal, governance
    - SR25 Bids (KB): funding ask, RDEL / CDEL, departmental SR positioning
    - SR21 Bids (KB): historical baseline — what was originally planned / funded
    - NAO Reports (KB): audit findings, PAC recommendations
    - GOV.UK Publications: published strategies, updates, reviews

    ## 3. Connections and Dependencies
    - Supplier dependencies (who delivers what)
    - Platform / technology dependencies
    - Programme interdependencies
    - Cross-government shared elements

    ## 4. Risk and Assurance Summary
    - GATS risk rating + assurance outcome
    - GMPP IPA confidence (if applicable)
    - NAO / PAC findings (if any)
    - Identified risks from business case / SR bids
    - Concentration risks (single supplier, single platform)
    """,
)


# -----------------------------------------------------------------------------
# Supplier lock-in
# -----------------------------------------------------------------------------

SUPPLIER_LOCKIN_OUTPUT_SPEC = block(
    "output_requirements",
    """
    Required sections:
    1. Executive Risk Summary
    2. Supplier Dependency Map
    3. Supplier–Programme–Department Network
    4. Lock-In Category Analysis
    5. Concentration Risk
    6. Cross-Government Shared Risks
    7. Direct Awards and Extensions
    8. Exit Risk Assessment
    9. Neptune Cypher Queries
    10. Intelligence Gaps
    """,
)


SUPPLIER_LOCKIN_OUTPUT_CARD = block(
    "supplier_lockin_output_card",
    """
    For each significant supplier, produce a structured card:

    | Field | Detail |
    |-------|--------|
    | Total contract value | £Xm |
    | Number of contracts | N |
    | Programmes dependent | List |
    | Departments linked | List |
    | Lock-in category | Proprietary Platform / Core System / Managed Service / Integration / Architectural |
    | Exit complexity | High / Medium / Low + rationale |
    | Contract end dates | Dates |
    | Extensions granted | Yes / No + number |
    | Direct awards | Yes / No |
    | NAO / PAC flags | Yes / No + summary |
    | Evidence sources | [GRAPH] [KB:gats] [ATHENA] |

    Concentration Risk Heatmap (ordered by risk):
    | Supplier | Programmes | Departments | Total Value | Lock-In Level |

    Exit Risk Assessment — for each high-lock-in supplier:
    - Is there an exit or transition plan in any business case or SR bid?
    - Has NAO / PAC commented on exit risk?
    - What would exit require technically?
    - What is the realistic re-competition timeline?
    """,
)


# -----------------------------------------------------------------------------
# Supplier ecosystem
# -----------------------------------------------------------------------------

SUPPLIER_ECOSYSTEM_OUTPUT_SPEC = block(
    "output_requirements",
    """
    Required sections:
    1. Ecosystem Overview
    2. Supplier Directory
    3. Ecosystem Structure Analysis
    4. Concentration and Diversity Assessment
    5. Cross-Government Positioning
    6. Emerging and Niche Suppliers
    7. Capability Gaps
    8. Strategic Observations and Recommendations
    """,
)


SUPPLIER_ECOSYSTEM_OUTPUT_CARD = block(
    "supplier_ecosystem_output_card",
    """
    For each supplier (ordered by total contract value), produce a structured card:

    | Field | Detail |
    |-------|--------|
    | Supplier Type | [from taxonomy] |
    | Total contract value | £Xm |
    | Number of contracts | N |
    | Programmes / capabilities | List |
    | Technologies / platforms delivered | List |
    | Delivery model | Managed service / Staff aug / Licence / Mixed |
    | Strategic importance | Commodity / Important / Critical / Irreplaceable |
    | Cross-government presence | Yes / No + other departments |
    | Evidence sources | [GRAPH] [KB:gats] [ATHENA] |

    Concentration metrics table:

    | Metric | Value |
    |--------|-------|
    | Total suppliers identified | N |
    | Top 3 suppliers' share of total value | X% |
    | Suppliers appearing in 3+ programmes | N |
    | Single-supplier programmes | N |
    """,
)


# -----------------------------------------------------------------------------
# Targeted question
# -----------------------------------------------------------------------------

TARGETED_QUESTION_OUTPUT_SPEC = block(
    "output_requirements",
    """
    Answer directly and keep it tight.

    Required structure:
    - Direct answer (1-3 sentences)
    - Ranked organisations / programmes table
    - Notes (only if helpful)

    Prioritise the most well-evidenced matches first.
    """,
)


TARGETED_QUESTION_OUTPUT_CARD = block(
    "targeted_question_output_card",
    """
    OUTPUT TABLE — ranked, most-evidenced first:

    | Organisation | What they are doing | Programme / Contract | Supplier / Technology | Value | Sources |
    |--------------|---------------------|----------------------|------------------------|-------|---------|

    - One row per organisation. Multi-source matches at the top.
    - Put the exact programme name, Spend ID, or contract title in the relevant column.
    - Include the £ figure only where you have it from a source. Do not invent figures.

    Notes (only if useful):
    - High-confidence findings (corroborated across sources) vs single-source mentions.
    - Notable suppliers or shared technologies (e.g. several orgs all using Dynamics 365 / Salesforce).
    - What you searched for that returned nothing, if relevant to interpreting the answer.
    """,
)


# -----------------------------------------------------------------------------
# Sovereign stack
# -----------------------------------------------------------------------------

SOVEREIGN_STACK_OUTPUT_SPEC = block(
    "output_format",
    """
    Required sections:
    - Executive Summary
    - Master Assessment Table
    - Per-Layer Analysis (all layers)
    - Investment Prioritisation
    - Cross-Cutting Assessment
    - Hypotheses Scorecard
    - Intelligence Gaps & Validation
    - Source Diagnostics
    - References
    """,
)


def sovereign_stack_output_card(today: str) -> str:
    return block(
        "sovereign_stack_output_tables",
        f"""
        MASTER ASSESSMENT TABLE — one row per layer, in stack order L1 -> L7:

        | Layer | UK role | Evidence of UK capability | Evidence of dependency | Strategic risk | Best achievable shift | Recommended lever | Confidence |
        |-------|---------|---------------------------|------------------------|----------------|-----------------------|-------------------|------------|

        Example row:
        | L3 Cloud, Compute & Platform | Taker / shaper | UK compute assets, data centres, research compute [GRAPH][GOV.UK] | Foreign hyperscalers, GPU supply, cloud lock-in [ATHENA][KB:nao] | High | Taker -> shaper | Compute investment, procurement, cloud competition, sovereign workloads | Medium |

        PER-LAYER ANALYSIS — one section per layer, all seven, in stack order:

        ### LAYER [N] — [LAYER NAME from <seven_layer_stack>]
        - **Classification:** Taker / Shaper / Maker (+ any niche makership) | **Confidence:** High/Medium/Low
        - **Control test:** Location | Ownership | Operational control | Substitutability | Strategic consequence
        - **Evidence:**
          - A. Capability: [...]
          - B. Dependency: [...]
          - C. Demand: [...]
          - D. Policy leverage: [...]
        - **Scores (1-5):** Domestic capability | Scale | Control | Resilience | Substitutability | Market strength | Policy leverage
        - **Best achievable shift:** Taker -> Shaper, Shaper -> Maker, hold-and-deepen niche.

        INVESTMENT PRIORITISATION TABLE:

        | Intervention | Layer(s) | Strategic criticality | Dependency risk | UK right to win | Additionality | Time to impact | Spillovers | Cost / feasibility | Priority |
        |--------------|----------|-----------------------|-----------------|-----------------|---------------|----------------|------------|--------------------|----------|

        Group recommendations by time-to-impact (1-3 / 3-7 / 7-15 years).

        HYPOTHESES SCORECARD:
        For each starting hypothesis: Confirmed / Qualified / Refuted + the evidence and source tags.

        REFERENCES — MUST appear as the FINAL section. Group by source type. Include the
        date of each source so readers can assess currency relative to today ({today}).

        ### Knowledge Graph (default_)
        | # | Query summary | Mode | Key entities returned | Source document dates (if visible) |
        |---|---------------|------|----------------------|-----------------------------------|

        ### Knowledge Bases
        | # | KB tool | Query | Key findings | Source document date(s) |
        |---|---------|-------|--------------|------------------------|

        ### Athena SQL
        | # | Table | Query summary | Key findings | Date range of data |
        |---|-------|---------------|--------------|-------------------|

        ### GOV.UK Publications
        | # | Title | URL | Publication / last-updated date | Key findings |
        |---|-------|-----|---------------------------------|--------------|

        ### Temporal Currency Summary
        | Source type | Typical date range | Currency vs today ({today}) | Notes |
        |-------------|--------------------|------------------------------|-------|
        | SR21 bids | 2020-2021 | Historical baseline | Intentions may be completed or cancelled |
        | SR25 bids | 2024-2025 | Current | Most recent investment plans |
        | GATS business cases | 2021-2025 (varies) | Check per case | Dates vary widely |
        | Contracts (Athena) | 2018-2026 (varies) | Check end dates | Only active contracts = current dependency |
        | GMPP 24-25 | 2024-2025 | Current | Latest delivery confidence |
        | NAO reports | Varies | Check per report | Recommendations may have been actioned |
        | GOV.UK publications | Varies | Check publication date | Strategies may have been superseded |
        """,
    )


# -----------------------------------------------------------------------------
# Pitch deck
# -----------------------------------------------------------------------------

PITCH_DECK_OUTPUT_SPEC = block(
    "html_deck_specification",
    """
    Output must be a single self-contained HTML file.
    No external libraries, fonts, images, or frameworks.
    Presentation should render as a polished executive slide deck.
    Use a consistent design system and 16:9 slide canvases.
    """,
)


PITCH_DECK_DESIGN_SYSTEM = block(
    "pitch_deck_design_system",
    """
    DESIGN SYSTEM — UK Civil Service / GDS / McKinsey-style executive presentation.

    Core delivery rules:
    - Use one HTML file only.
    - Use embedded CSS only.
    - No external fonts, libraries, scripts, images, or frameworks.
    - Build each slide as a 16:9 presentation canvas.
    - The deck should render cleanly in a browser and feel like a designed slide deck.
    - Prefer semantic HTML and highly structured CSS.
    - Do not generate speaker notes or markdown slides.

    Visual design:
    - Primary dark navy: #050A3D.
    - Accent cyan: #21D6D6.
    - White content slides with navy headers.
    - Clean executive layout with strong hierarchy and minimal clutter.
    - Consistent footer on every slide with "OFFICIAL".
    - Typography: sober, modern, presentation-appropriate (system fonts: -apple-system,
      BlinkMacSystemFont, 'Segoe UI', sans-serif).
    - Use restrained accents, subtle borders, and sharp information hierarchy.
    - The deck must look like it was designed by one designer from start to finish.

    Deck architecture:
    - Build the presentation as vertically stacked slide sections in one HTML page.
    - Each slide centred 16:9 card / canvas (aspect-ratio: 16/9 or equivalent).
    - Use reusable CSS classes for shared layout patterns.
    - Keep spacing, typography scale, card radii, borders, shadows, banners, and footer
      treatment consistent across slides.

    Slide design methodology:
    1. Define the shared design system in CSS first (colours, spacing, typography, slide
       shell, headers, footer, common components).
    2. Build slides one by one: structure -> hierarchy -> minimal decoration.
    3. Treat each slide as a consultancy slide:
       - One clear message per slide
       - Obvious focal point
       - Supporting detail subordinate to the main idea
       - No dense paragraphs
       - Use panels, grids, pipelines, callouts, hero metrics, comparison structures
    4. If a slide feels crowded: remove copy first, tighten spacing second, reduce
       secondary text third. Preserve the primary focal element.

    Quality bar — verify before finishing:
    - Self-contained HTML only, no external dependencies
    - 16:9 slides
    - Consistent "OFFICIAL" footer on every slide
    - Visual hierarchy clear on every slide
    - No overlapping or colliding content
    - Slide copy fits comfortably within the canvas
    - Design system consistent from first to last slide
    """,
)
