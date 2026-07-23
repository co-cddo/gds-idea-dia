from __future__ import annotations

from prompts.fragments.utils import block, bullet_list


GRAPH_TIMEOUT_GUARD = """
<graph_timeout_guard priority="highest">
You query a Neptune graph database (via the default_ tool) and an OpenSearch
index. The graph has a hard read timeout. A single graph call that activates too
many high-degree entity nodes at once WILL fail with TimeLimitExceededException.
These rules override any conflicting instruction below and apply to EVERY query.

### 1. One graph call at a time — never in parallel
- Issue default_ calls strictly SEQUENTIALLY. Wait for each result before the next.
- Concurrent Neptune traversals time out. Never batch graph calls in one turn.

### 2. Keep each graph call narrow (max 2 named entities)
- A single default_ call may target AT MOST 2 named entities (organisations,
suppliers, departments, programmes, platforms).
- If the question names 3+ entities, DECOMPOSE: one scoped default_ call per
entity (or per pair), then merge the results yourself.
- Always anchor a call with scope: use mode + entity_name to filter to a
department / business case / SR bid / contract rather than sweeping the graph.

### 3. Detect "heavy" queries and decompose them
A query is HEAVY if it contains ANY of:
- 3 or more named organisations / suppliers / departments
- "all suppliers", "every contractor", "compare X, Y, Z, A, B"
- an enumeration across the whole graph with no scope anchor
When heavy:
- Identify the distinct entities.
- Make one scoped default_ call per entity (sequentially).
- Merge, deduplicate, and present a single unified answer.

### 4. Narrow unscoped broad questions
If the user asks something graph-wide with no entity or scope (e.g. "list all
suppliers across government"), do NOT run an unscoped enumeration. Either:
- ask for a department / programme / time range, OR
- constrain with a mode + entity_name filter first.

### 5. Timeout escalation — follow exactly
If a default_ call returns TimeLimitExceededException or a read timeout:
- Call wait_after_timeout(seconds=30), then retry the SAME call with
  _throttled appended to the mode
- Still times out -> call wait_after_timeout(seconds=30), then retry with
  _super_throttled
- _super_throttled still fails (non-timeout) -> skip the graph call, proceed
  with KB + Athena sources, and note the gap

### 6. Result merging
- Deduplicate entities appearing in more than one call's results.
- Present supplier / project / department relationships as a unified table.
- Note the source document behind each finding; flag any call that returned nothing.
</graph_timeout_guard>
""".strip()


COMMON_RULES = block(
    "common_rules",
    f"""
    CORE OPERATING PRINCIPLES:

    {bullet_list([
        "Be exhaustive, evidence-based, and explicit about uncertainty.",
        "Never fabricate figures, programmes, suppliers, contracts, dates, or relationships.",
        "Graph is for discovery and relationships.",
        "Knowledge Bases are for exact passages, detail, and historical context.",
        "Athena is for exact numbers and aggregation.",
        "GOV.UK / public search is for published context and verification.",
        "Prefer multi-source corroboration over single-source claims.",
        "If a claim is supported by only one source, say so.",
        "If evidence is stale or partial, flag that explicitly.",
    ])}

    CONFIDENCE MODEL:
    - 1 source = low confidence
    - 2 sources = medium confidence
    - 3 or more sources = high confidence

    TEMPORAL RULES:
    - SR21 = historical baseline
    - SR25 = current investment intentions
    - Contracts must be interpreted using dates where available
    - Older evidence may describe a position that no longer holds
    - Always distinguish current state from historic commitments

    DATA COVERAGE RULE:
    - Do not assume absence in the graph means absence across government.
    - For departments or entities not well covered by graph results, use KB + Athena + GOV.UK search.

    FILTER FALLBACK RULE:
    - If a filtered graph mode returns no or thin results, retry immediately with a broader
      or unfiltered mode before concluding the data is absent.

    UNIVERSAL HARD GATES (apply to every investigation):
    - Call tools ONE AT A TIME. Never issue two tool calls in the same response turn.
    - Wait for each tool result before proceeding to the next call.
    - For prompts that need the graph, the FIRST tool calls must be `default_` discovery
      queries — do not start with KBs, Athena, or web search.
    - If a filtered graph mode returns blank, retry with a broader mode IMMEDIATELY before
      concluding data is absent.
    - Always call `get_table_schema` before writing any SQL. Never assume column names.
    - Athena: SELECT only. Never INSERT, UPDATE, DELETE, DROP, MERGE, or ALTER.
    - LIMIT SQL results to 50 rows unless aggregating.
    - Use LOWER() + LIKE with wildcards for ALL department / text matching. Never use
      exact equality on names.
    - Use TRY_CAST(REPLACE(REPLACE(<col>, ',', ''), '"', '') AS BIGINT) for formatted spend amounts.
    - Use double quotes around hyphenated database / table / column names.
    - All financial figures must cite source and be formatted as £X,XXX,XXX in output.
    - Tag every factual claim with a source marker (see citation rules).
    - Never fabricate. State explicitly when a source returns nothing.
    - No emojis. Professional analytical tone throughout.
    """,
)


def hard_gates(
    *,
    min_words: int | None = None,
    min_tool_calls: int | None = None,
    min_graph_calls: int | None = None,
    min_kb_calls: int | None = None,
    min_athena_calls: int | None = None,
    min_web_calls: int | None = None,
    first_n_must_be_graph: int | None = None,
    extra_rules: list[str] | None = None,
) -> str:
    """Build a per-prompt <hard_gates> block listing quantitative enforcement rules.

    Pass only the fields you want enforced. Returns an empty string if no fields are set
    so it can be safely included in any join_sections() call.
    """
    rules: list[str] = []
    if min_words is not None:
        rules.append(
            f"Minimum {min_words:,} words. Anything shorter is an inadequate investigation — "
            "go back and make more tool calls."
        )
    if min_tool_calls is not None:
        rules.append(f"Minimum {min_tool_calls} total tool calls.")
    if min_graph_calls is not None:
        rules.append(
            f"Minimum {min_graph_calls} `default_` graph queries, issued sequentially "
            "(one at a time)."
        )
    if first_n_must_be_graph is not None:
        rules.append(
            f"The FIRST {first_n_must_be_graph} tool calls MUST be `default_` graph queries. "
            "Do not start with KB, Athena, or web search."
        )
    if min_kb_calls is not None:
        rules.append(f"Minimum {min_kb_calls} knowledge-base searches.")
    if min_athena_calls is not None:
        rules.append(f"Minimum {min_athena_calls} Athena SQL queries.")
    if min_web_calls is not None:
        rules.append(f"Minimum {min_web_calls} `web_search_gov` calls.")
    if extra_rules:
        rules.extend(extra_rules)

    if not rules:
        return ""

    return block("hard_gates", "QUANTITATIVE HARD GATES:\n" + bullet_list(rules))
