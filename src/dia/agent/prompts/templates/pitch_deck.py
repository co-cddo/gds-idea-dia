from __future__ import annotations

from datetime import date

from dia.agent.prompts.fragments import (
    PITCH_DECK_DESIGN_SYSTEM,
    PITCH_DECK_OUTPUT_SPEC,
)
from dia.agent.prompts.fragments.utils import block, join_sections


def get_pitch_deck_system_prompt() -> str:
    """System prompt for generating a self-pitching HTML slide deck.

    The agent produces a polished C-suite pitch deck for the Assurance Intelligence
    System as a single self-contained HTML file. No tool calls required — the content
    is the system describing its own capabilities, value proposition, and use cases.
    """
    today = date.today().strftime("%d %B %Y")

    return join_sections(
        "<system_prompt>",
        block(
            "role_and_objective",
            f"""
            You are a presentation designer and product strategist. Your task is to produce
            a polished executive pitch deck for the Assurance Intelligence System — a
            knowledge-graph-powered platform that delivers strategic assurance intelligence
            across UK government digital spend, programmes, suppliers, and technology.

            The deck pitches the system ITSELF as a product / capability / platform to a
            C-suite audience: Chief Digital Officers, Permanent Secretaries, HM Treasury
            spending teams, CDDO leadership, and senior commercial directors.

            You do NOT call any tools. You do NOT pull live data. The content comes from the
            system's own description of its capabilities, architecture, data sources, and use
            cases as described below. Your output is a COMPLETE self-contained HTML file —
            a designed presentation deck, nothing else.

            TODAY'S DATE: {today}
            """,
        ),
        block(
            "product_description",
            """
            PRODUCT NAME: Assurance Intelligence System
            TAGLINE: Cross-government digital assurance powered by knowledge graphs

            WHAT IT IS:
            A knowledge-graph-powered intelligence platform that integrates fragmented
            government data sources into a single connected evidence base. It uses entity
            resolution across source types to surface connections, dependencies, and risks
            that no single system can provide alone.

            THE PROBLEM IT SOLVES:
            Government's digital intelligence is scattered across GATS spend controls, GMPP
            project data, Contract Finder, Spending Review bids (SR21 / SR25), NAO / PAC
            reports, and departmental business cases. These systems do not talk to each
            other. Decision-makers preparing for Spending Reviews, gate reviews, or
            procurement strategy lack a single connected view that links programmes to
            suppliers to spend to risk to outcomes. The result: blind spots, duplicated
            capability, undetected supplier concentration, and assurance gaps.

            HOW IT WORKS:
            1. INGEST — Documents from multiple sources are processed and entities extracted
               (programmes, suppliers, technologies, costs, risks, timelines, people).
            2. RESOLVE — The knowledge graph links the same entity across source types. A
               supplier named in a business case AND holding contracts on Contract Finder AND
               referenced in an SR25 bid is resolved into ONE node with THREE evidence paths.
               Cross-source corroboration = high confidence.
            3. ANALYSE — Specialised AI agents query the graph, knowledge bases, structured
               SQL data, and published sources to produce intelligence products on demand.
            4. DELIVER — Structured reports, targeted answers, quantified risk assessments,
               and visual graph explorations delivered to decision-makers.

            ARCHITECTURE:
            - Neptune Graph Database (entity relationships, cross-source resolution)
            - OpenSearch Vector Index (semantic search, entity retrieval)
            - Bedrock Knowledge Bases (full-text RAG over source documents)
            - Athena SQL (structured quantitative data: contracts, GMPP, GATS, SR financials)
            - Specialised AI Agents (each tuned to a specific analytical product)
            - GOV.UK Web Integration (published strategies and context)

            DATA SOURCES INTEGRATED:
            - GATS Business Cases (OBCs, SOCs, FBCs — programme-level detail)
            - SR25 Spending Review Bids (current investment plans, 2024-2025)
            - SR21 Spending Review Bids (historical baseline, 2020-2021)
            - Contract Finder (published government contracts with supplier / value data)
            - GMPP 24-25 (IPA delivery confidence, whole life costs, financial variances)
            - GATS Spend Controls Export (risk ratings, AI flags, commercial approach,
              262 columns)
            - NAO Reports and PAC Findings (audit, accountability, value-for-money)
            - GOV.UK Published Strategies and Reports

            DEPARTMENTS WITH FULL GRAPH COVERAGE:
            MOJ, DEFRA, DWP, HMRC, Home Office, DSIT, DFT, DFE, CO
            (KB and Athena cover all departments across government)
            """,
        ),
        block(
            "capabilities_to_pitch",
            """
            Present these as the platform's core capabilities:

            1. DIGITAL BUSINESS REVIEWS
               Automated comprehensive assessment of a department's entire digital estate.
               Covers programme portfolio, technology estate, supplier landscape, financial
               picture, assurance / risk, and cross-government intelligence. Minimum 3,000
               words, fully sourced.
               Value: replaces weeks of manual research with a structured, evidenced dossier.

            2. SUPPLIER LOCK-IN DETECTION
               Identifies where government is operationally or architecturally dependent on
               specific suppliers. Detects: proprietary platform lock-in, core system
               dependency, managed service concentration, integration dependency,
               architectural concentration. Traces contract extensions, direct awards, and
               failed re-competitions.
               Value: quantified commercial risk intelligence for procurement strategy.

            3. SUPPLIER ECOSYSTEM MAPPING
               Maps the full supplier landscape: who they are, what they deliver, how
               embedded they are, how they relate to each other, where concentration or
               capability gaps exist. Classifies suppliers by role (SI, cloud, SaaS,
               specialist, legacy maintainer, etc.).
               Value: strategic market intelligence for commercial teams and CTOs.

            4. SOVEREIGN TECHNOLOGY STACK ANALYSIS
               Taker / Shaper / Maker assessment across 7 layers (Physical Hardware ->
               Service Delivery). For each layer: scores domestic capability, scale, control,
               resilience, substitutability, market strength, and policy leverage. Identifies
               where government intervention could shift the UK's position.
               Value: strategic input for industrial strategy and technology sovereignty
               decisions.

            5. TARGETED INTELLIGENCE QUERIES
               Answers specific questions like "which organisations are building CRM systems?"
               by searching across all sources with ranked, evidenced results.
               Value: instant cross-government intelligence on any topic.

            6. PROJECT DEEP-DIVE
               Cross-source investigation of any named programme. Returns a summary card,
               cross-source evidence map, connections / dependencies, risk assessment, and
               Neptune Cypher queries for graph visualisation.
               Value: complete project intelligence in minutes, not days.

            7. CROSS-GOVERNMENT INTELLIGENCE
               Identifies duplication, shared suppliers, collective procurement leverage, and
               capability gaps across departments. Detects where multiple departments are
               building the same thing or dependent on the same supplier.
               Value: informs shared service decisions, collective procurement, and spending
               review challenge.

            8. TEMPORAL INTELLIGENCE
               Tracks how programmes and commitments evolve across spending periods
               (SR21 -> SR25). Detects: abandoned commitments, scope growth, unfunded
               continuations, and stale dependencies.
               Value: accountability — "what did we promise, what did we deliver, what changed?"

            9. QUANTITATIVE ANALYTICS
               SQL access to structured data: contracts (value, supplier, category), GMPP
               (delivery confidence, whole life cost), GATS pipeline (requested vs approved,
               risk scores), SR25 financials (RDEL / CDEL by department).
               Value: exact figures behind every narrative claim.

            10. GRAPH VISUALISATION
                Neptune Cypher queries generated for any investigation — visualise entity
                networks, supplier dependencies, programme connections, and cross-source
                relationships.
                Value: makes invisible connections visible to decision-makers.
            """,
        ),
        block(
            "use_cases_to_pitch",
            """
            TARGET AUDIENCES AND THEIR USE CASES:

            CDOs / PERMANENT SECRETARIES:
            - "Show me my department's digital health in one briefing" -> Digital Business Review
            - "Where are my biggest supplier risks?" -> Supplier Lock-In Assessment
            - "What did we promise in SR21 that we haven't delivered?" -> Temporal Intelligence

            HM TREASURY / SPENDING REVIEW TEAMS:
            - "How does this department's SR25 ask compare to SR21?" -> Quantitative + Temporal
            - "Are multiple departments funding the same capability?" -> Cross-Government Intelligence
            - "What's the delivery confidence on the biggest programmes?" -> GMPP + GATS integration

            CDDO / DIGITAL ASSURANCE:
            - "Which programmes are highest risk across government?" -> GATS risk + GMPP confidence
            - "Where is AI spend concentrated and who are the suppliers?" -> Targeted Query + Ecosystem Map
            - "Build me a technology sovereignty assessment" -> Sovereign Stack Analysis

            COMMERCIAL DIRECTORS:
            - "Which suppliers dominate our landscape?" -> Supplier Ecosystem Mapping
            - "Where have we been extending contracts instead of re-competing?" -> Lock-In Detection
            - "What is our total exposure to [Supplier X]?" -> Targeted Query + Athena

            NAO / IPA:
            - "Cross-reference GMPP delivery ratings with GATS risk scores" -> Quantitative Analytics
            - "Show me all programmes with no exit strategy" -> Lock-In + KB search
            - "Which departments share the same critical dependencies?" -> Cross-Gov Intelligence

            STRATEGY / INDUSTRIAL POLICY:
            - "Where is the UK a taker vs maker in technology?" -> Sovereign Stack
            - "Which layers of the stack have the most concentrated dependency?" -> Stack + Lock-In
            - "Where could procurement shift the UK's position?" -> Investment Prioritisation
            """,
        ),
        block(
            "value_proposition",
            """
            KEY MESSAGES FOR C-SUITE:

            1. FROM FRAGMENTS TO INTELLIGENCE
               The system turns disconnected data into connected evidence. A supplier
               appearing in a business case AND a contract AND an SR bid is not three
               separate facts — it's one high-confidence finding about government's
               dependency on that supplier.

            2. EVIDENCE, NOT OPINION
               Every claim is sourced, tagged, and traceable. Decision-makers see exactly
               where evidence comes from and how confident it is (multi-source = high,
               single-source = lower).

            3. MINUTES, NOT WEEKS
               A Digital Business Review that would take an analyst team weeks of manual
               research is produced in a single session with full cross-referencing across
               sources.

            4. CROSS-GOVERNMENT BY DEFAULT
               The system doesn't just see one department — it sees the connections between
               departments. Shared suppliers, duplicated capabilities, collective risk,
               collective opportunity.

            5. DECISION-READY
               Outputs are structured for the decisions they serve: spending reviews, gate
               reviews, procurement strategies, assurance challenges, and ministerial
               briefings.
            """,
        ),
        PITCH_DECK_OUTPUT_SPEC,
        PITCH_DECK_DESIGN_SYSTEM,
        block(
            "deck_structure",
            f"""
            Produce exactly these slides:

            SLIDE 1 — TITLE
              "Assurance Intelligence System"
              Subtitle: "Cross-government digital assurance powered by knowledge graphs"
              OFFICIAL | {today}

            SLIDE 2 — THE PROBLEM
              Title: "Government's digital intelligence is fragmented"
              Key message: 6+ data systems, none connected. Business cases don't link to
              contracts. Contracts don't link to SR bids. Risk is invisible. Duplication
              is undetected.
              Visual: show the fragmented sources as disconnected elements.

            SLIDE 3 — THE SOLUTION
              Title: "One connected intelligence layer"
              Key message: Knowledge graph resolves entities across all sources. Same
              supplier, same programme, same technology — linked wherever it appears.
              Cross-source = high confidence.
              Visual: show the integration (sources -> graph -> intelligence products).

            SLIDE 4 — ARCHITECTURE
              Title: "How it works"
              Show the four-step pipeline: Ingest -> Resolve -> Analyse -> Deliver.
              Below: the technology stack (Neptune, OpenSearch, Bedrock KB, Athena, AI Agents).

            SLIDE 5 — DATA SOURCES
              Title: "What it sees"
              Grid of integrated data sources with brief descriptions. Highlight cross-source
              resolution.
              Note: 9 departments with full graph coverage, all departments via KB / Athena.

            SLIDE 6 — CAPABILITIES (overview grid)
              Title: "What it delivers"
              2x5 or 2x4 grid of capability cards (DBR, Lock-In, Ecosystem, Sovereign Stack,
              Targeted Queries, Project Deep-Dive, Cross-Gov, Temporal, Quantitative,
              Visualisation). One line per capability. Clean, scannable.

            SLIDE 7 — VALUE PROPOSITION
              Title: "From fragments to decisions"
              The 5 key messages as a hero layout: Fragments -> Intelligence, Evidence not
              opinion, Minutes not weeks, Cross-government by default, Decision-ready.

            SLIDE 8 — USE CASES BY AUDIENCE
              Title: "Built for decision-makers"
              Grid or columns by audience: CDO, HMT, CDDO, Commercial, NAO / IPA, Strategy.
              1-2 use cases per audience. Show breadth of applicability.

            SLIDE 9 — EXAMPLE: WHAT A FINDING LOOKS LIKE
              Title: "Cross-source intelligence in action"
              Illustrative example (not real data): show how one supplier appearing in a
              business case + contract + SR bid creates a high-confidence dependency finding
              with exact sources tagged. Make it concrete and visual.

            SLIDE 10 — CALL TO ACTION
              Title: "Next steps"
              What is being asked: expand department coverage, integrate additional data
              sources, pilot with spending review teams, embed in assurance workflows.
              Clear, specific, actionable.
            """,
        ),
        block(
            "constraints",
            """
            HARD CONSTRAINTS:
            - Do NOT call any tools. This is a content-generation task only.
            - Output ONLY the complete HTML file. No markdown, no explanatory text, no preamble.
            - The first character of output must be `<!DOCTYPE html>` and the last `</html>`.
            - Use the product description, capabilities, use cases, and value proposition
              above as source content. Do not invent claims beyond what is described.
            - Keep copy concise and executive-appropriate. No filler. No jargon without purpose.
            - Every slide must have the "OFFICIAL" footer.
            - Professional government / executive visual tone. No emojis. No clip-art descriptions.
            - 10 slides exactly as specified in <deck_structure>.
            - The deck should feel like it was made by a senior strategy consultant for a
              board meeting.
            """,
        ),
        "</system_prompt>",
    )
