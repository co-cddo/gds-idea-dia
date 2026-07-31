from __future__ import annotations

from dia.agent.prompts.fragments.utils import block

COMMON_INVESTIGATION_METHODOLOGY = block(
    "investigation_methodology",
    """
    NON-NEGOTIABLE SEQUENCING AND EXECUTION RULES:

    SEQUENTIAL EXECUTION:
    - Call tools one at a time.
    - Never parallelise graph queries.
    - Read each graph result before issuing the next graph call.

    PHASE ORDER:
    1. Graph discovery first
    2. Knowledge Base detail second
    3. Athena quantification third
    4. GOV.UK/public search last

    GRAPH-FIRST RULE:
    - Your first phase must establish the entity map: programmes, suppliers, systems, risks, technologies, and dependencies.
    - Do not start Athena until you understand what entities you are quantifying.
    - Do not rely on KBs alone where the graph can first reveal cross-source relationships.

    GRAPH FALLBACK RULE:
    - If a filtered mode returns blank or thin results, retry with a broader mode or unfiltered mode.
    - If graph calls keep failing after throttled fallbacks, continue with KB and Athena and note the graph gap.

    SYNTHESIS RULE:
    - Use the graph to discover
    - Use KBs to explain
    - Use Athena to quantify
    - Use GOV.UK to contextualise

    HEAVY QUERY RULE:
    - Decompose broad or enumerative questions into smaller graph queries.
    - Merge and deduplicate findings yourself.
    """,
)


DBR_INVESTIGATION_METHOD = block(
    "dbr_investigation_method",
    """
    DBR INVESTIGATION FLOW:

    PHASE 1 — Graph Discovery:
    - Identify digital programmes, suppliers, platforms, systems, technologies, risks, and dependencies.
    - Run data/AI-focused queries, legacy/debt queries, and broad supplier / technology discovery.

    PHASE 2 — Graph Drill-Down:
    - Drill into the top programmes and suppliers found in Phase 1.
    - Identify cross-government overlaps and repeated dependencies.

    PHASE 3 — Knowledge Bases:
    - For each major programme: query business cases and SR25
    - For programmes with historical lineage: query SR21
    - For major programmes, suppliers, and issues: query NAO / PAC material

    PHASE 4 — Athena:
    - Quantify contract value, spend by category, GATS pipeline, risk, GMPP confidence, and any other structured metrics relevant to the review

    PHASE 5 — Published Context:
    - Look for digital strategies, transformation plans, published programme references, and public assurance context

    FINAL STEP:
    - Produce a cross-source, evidence-tagged report with diagnostics and intelligence gaps.
    """,
)


PROJECT_INVESTIGATION_METHOD = block(
    "project_investigation_method",
    """
    PROJECT INVESTIGATION FLOW:

    1. Graph discovery for the named project/programme
    2. Graph drill-down for suppliers, technologies, risks, timelines, dependencies
    3. Athena checks for spend controls, contracts, and GMPP references
    4. KB lookups for business case, SR25, SR21, and NAO references
    5. GOV.UK/public search for published context
    6. Produce structured evidence summary plus Neptune openCypher query
    """,
)


SUPPLIER_INVESTIGATION_METHOD = block(
    "supplier_investigation_method",
    """
    SUPPLIER INVESTIGATION FLOW:

    1. Graph discovery of suppliers, programmes, departments, and technologies
    2. Cross-government probe for repeated supplier/platform usage
    3. KB checks for exit risk, managed service language, future embedding, or audit commentary
    4. Athena checks for contract value, extensions, direct awards, concentration, and pipeline exposure
    5. GOV.UK/public search for published context
    6. Produce dependency/concentration analysis with explicit evidence
    """,
)


TARGETED_QUESTION_METHOD = block(
    "targeted_question_method",
    """
    TARGETED QUESTION FLOW:

    1. Decompose the capability/topic into synonyms and related terms
    2. Graph discovery across default / business_case_all / sr_bids_all as appropriate
    3. KB corroboration for the same topic terms
    4. Athena contract/spend check where structured evidence exists
    5. GOV.UK/public search only if needed for published context
    6. Answer directly with ranked organisations/programmes and evidence
    """,
)


SOVEREIGN_STACK_METHOD = block(
    "sovereign_stack_method",
    """
    SOVEREIGN STACK FLOW:

    Work LAYER BY LAYER, not tool by tool across the whole stack.

    For each layer:
    1. Graph discovery of technologies, suppliers, dependencies, and named entities
    2. KB supplementary discovery, especially where graph coverage is thin
    3. Graph drill-down on the highest-value entities
    4. KB enrichment (SR25, SR21, GATS, NAO)
    5. Athena quantification
    6. GOV.UK/public context and gap-fill
    7. Produce layer evidence summary before moving to the next layer

    After all layers:
    - score
    - classify taker / shaper / maker
    - identify intervention opportunities
    - write the final report
    """,
)
