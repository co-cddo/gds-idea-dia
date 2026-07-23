# Assurance Agent Refactor - Decisions & Plan

## Context

Refactor the assurance agent so it can be run via CLI (dia agent ask ...). The end goal is agent delegation — a supervisor agent that routes a query to the right specialist agent (DBR, supplier lock-in, project investigation, etc.) automatically based on the department and question asked.

### The two-phase system this agent sits inside

```
Phase 1 (write)                              Phase 2 (read-only)
Raw documents in S3                          A person has a question
     |                                            |
     v                                            v
S3DocumentProcessor -> LlamaIndex Document    "The agent" picks tool(s):
     |                                        - graph search (Neptune/OpenSearch)
     v                                        - Athena SQL
LexicalGraphIndex.extract()                   - Bedrock KB search
  (one-shot batch LLM call per chunk,          - gov.uk web search
   no tools/conversation)                          |
     |                                              v
     v                                        Answer / report back
LexicalGraphIndex.build()
     |
     v
Neptune (graph) + OpenSearch (vectors) + some Athena tables
= "the knowledge base"
```

Running the pipeline only ever **writes** to the knowledge base. The agent only ever
**reads** from it. Never the other way round.

Note: not everything the agent can query is built by this repo's pipeline - `gmpp_24_25`
and `workforce_commision_26` Athena tables, and the Bedrock Knowledge Bases, are
populated by other processes outside this repo's scope.

---

## Decision 1: Where does the refactored agent live?

**Considered:**
- A brand new, independent repo/package for the agent (CLI-first, standalone)
- Extending the production `gds-idea-knowledge-base-agent-core` agent directly
- Folding the agent into `gds-idea-dia`

**Chose: fold into `gds-idea-dia`.**

---

## Decision 2: Kill the notebook, CLI-only interface

**Considered:** Keep `mcp_agent.ipynb` as the interface, or as a dev-only scratchpad.

**Chose: drop it entirely.** The CLI (`dia agent ask ...`) becomes the only interface.

Confirmed there is no existing output-persistence mechanism for agent responses today -
`print(response)` to a notebook cell is the entire current behaviour. Dropping the
notebook loses nothing that currently exists; the new `.docx` + S3 output (Decision 6)
is a net improvement, not a migration of existing behaviour.

---

## Decision 3: MCP server lifecycle - embedded per-invocation, not persistent

**Considered:** A long-lived, separately-run MCP server process that the CLI connects
to as a thin client, vs. starting a fresh embedded server (background thread) inside
every CLI invocation.

**Chose: embedded per-invocation** (matches today's pattern).

Rationale: Neptune is deployed as **Neptune Serverless** (`min_capacity=1.0 NCU`,
`cdk/stacks/neptune_stack.py`) and AOSS is OpenSearch Serverless - both bill by query
compute load, not by connection count. Connecting fresh each CLI run adds no real AWS
cost, only a few seconds of Python-side startup latency (thread spin-up + graph-summary
warm-up query). A persistent server would need its own standing infra (EC2/Fargate) -
real cost and ops burden not currently justified for an ad-hoc CLI tool.

Kept decoupled in code (server build/start is independent of agent construction) so a
future `--server-url` flag can point at a persistent server later with no code changes,
if usage patterns ever justify it.

---

## Decision 4: Dependencies - single `pyproject.toml`, new optional extra

**Considered:** Add agent deps straight to `dia`'s main dependencies, vs. a separate
sub-package with its own `pyproject.toml`, vs. a new `[project.optional-dependencies]`
extra in the existing `pyproject.toml`.

**Chose: new optional extra**, e.g.:

```toml
[project.optional-dependencies]
agent = [
    "strands-agents>=1.20.0",
    "mcp",
    "fastmcp>=2.14.1",
    "tavily-python",
    "awswrangler>=3.15.1",
    "python-docx>=1.2.0",
]
```

Installed via `uv sync --extra agent`. Still one repo, one package, one
`pyproject.toml` - matches the existing `cdk` extra already present in `dia`. Pure
pipeline work doesn't need to install the agent stack.

---

## Decision 5: Config pattern - match `dia`'s existing style, endpoints from Secrets Manager

**Considered:** Introduce `pydantic-settings` + `.env` (not used anywhere else in
`dia`), vs. matching `dia`'s existing plain `pydantic BaseModel(frozen=True)` style
(`src/dia/config.py`).

**Chose:**
- Plain `pydantic BaseModel` settings for non-sensitive config: Athena DB/workgroup
  names, Bedrock KB IDs, model ID - consistent with `dia/config.py`
- **AWS Secrets Manager** for exactly the two sensitive values: the Neptune endpoint
  hostname and the AOSS endpoint hostname. Nothing else goes in Secrets Manager -
  DB/workgroup/table names and model IDs are not sensitive and stay as plain settings.

Note: `dia` has no existing "resolve endpoint from AWS account" helper (unlike its
`resolve_ledger_table()` pattern) because it doesn't currently own the Neptune/AOSS
infra - that's defined in this repo's CDK (`cdk/stacks/neptune_stack.py`). This is new
ground for `dia`.

---

## Decision 6: Report output - Word doc, uploaded straight to a new S3 bucket

**Considered:** Print-only (today's behaviour), a local `outputs/` folder, structured
JSON, or generating and uploading a `.docx`.

**Chose:**
- Convert the agent's markdown response **directly** to a `.docx` (straight
  markdown-to-docx via `python-docx`, no extra template or metadata header page)
- Upload straight to a **new, dedicated S3 bucket** (no local folder step)
- CLI prints the resulting S3 URI
- Email delivery to the requester is a **nice-to-have, deferred** - not in Stage 1 scope

The new bucket is defined by extending `dia`'s existing `stacks/storage.py` (which
already manages S3 buckets for the pipeline), rather than a new separate stack file.

---

## Decision 7: CLI shape - keep manual `--agent` selection for now

**Considered:** `--agent` flag to manually pick a persona (matches today's manual
notebook workflow) vs. jumping straight to `--department`/`--query` only, with routing
decided by a not-yet-built supervisor.

**Chose:** keep `--agent` for Stage 1:

```
dia agent ask --agent dbr --department "Home Office" --query "..."
```

Stage 2 (automatic routing, see below) will add a supervisor mode that can eventually
make `--agent` optional/unnecessary, but Stage 1 ships with manual selection as a
bridge so the CLI is usable immediately.

---

## Stage 1 structure

```
gds-idea-dia/
├── src/dia/
│   ├── cli.py                     # existing — gains `agent_app` sub-Typer (same pattern as `ledger_app`)
│   ├── config.py                  # existing pipeline config — untouched
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── config.py               # pydantic BaseModel settings: model id, Athena DB/workgroup names, KB IDs
│   │   ├── secrets.py              # fetches Neptune + AOSS endpoint hostnames from AWS Secrets Manager
│   │   ├── patches/
│   │   │   ├── __init__.py         # apply_all()
│   │   │   ├── search_result.py    # ISO-timestamp fix
│   │   │   ├── neptune_timeout.py  # 90s read_timeout override
│   │   │   ├── retry.py            # unretriable-exception + retry-floor fix
│   │   │   └── entity_search.py    # two-step capped multi-entity query rewrite
│   │   ├── stores.py               # build_graph_store(), build_vector_store(), build_graph_index()
│   │   ├── mcp/
│   │   │   ├── server.py           # build_mcp_server(), start_server(), server_url()
│   │   │   ├── retrieval_modes.py  # update_tool_params(), mode text, filter builders
│   │   │   └── tools/
│   │   │       ├── athena.py
│   │   │       ├── knowledge_base.py
│   │   │       └── web_search.py
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   ├── dbr.py / default.py / gats_query.py / project_investigation.py /
│   │   │   │   supplier_lockin.py / supplier_ecosystem.py      # moved verbatim — exist today in src/system_prompts.py
│   │   │   └── graph_cost_aware.py / pitch_deck.py / sovereign_stack.py /
│   │   │       targeted_question.py / ai_transformation.py      # TODO stubs — don't exist anywhere yet
│   │   ├── agents.py                # make_model(), make_agent(), per-prompt factories
│   │   └── report.py                # markdown response → .docx (python-docx) → upload to S3
│   └── ... (existing pipeline modules, untouched)
├── stacks/
│   └── storage.py                   # gains new agent-reports S3 bucket definition
└── pyproject.toml                   # gains [project.optional-dependencies] agent = [...]
```

### Migration steps

1. Scaffold `src/dia/agent/` skeleton + `config.py` + `secrets.py`.
2. Move the 4 patches verbatim into `patches/`.
3. Move store construction into `stores.py`.
4. Move MCP server lifecycle + mode-parsing logic into `mcp/server.py` / `mcp/retrieval_modes.py`.
5. Split Athena/KB/web-search tools into `mcp/tools/*`.
6. Copy the 6 existing prompts from `gds-idea-assurance-knowledge-graphs/src/system_prompts.py`; add 6 TODO stub prompt files for the missing ones (`graph_cost_aware`, `pitch_deck`, `sovereign_stack_v3`, `targeted_question`, `ai_transformation`, `ai_transformation_v2`).
7. Move model/agent factories into `agents.py`.
8. Build `report.py` (markdown → docx → S3 upload).
9. Add the new S3 bucket to `stacks/storage.py`.
10. Add `agent_app` Typer sub-app + `ask` command to `cli.py` (lazy imports inside command functions, matching the `ledger_app` pattern).
11. Add `[project.optional-dependencies] agent` to `pyproject.toml`.
12. Tests: patches (idempotency), retrieval_modes (mode→filter mapping), report.py (markdown→docx conversion).

---

## Stage 2 - Agent-to-agent (supervisor/router)

Starts only after Stage 1 fully ships (sequential, not parallel).

**Goal:** replace "human manually picks which of the ~12 agents to run" with a
supervisor agent that routes a query to the right specialist automatically.

**Mechanism:** Strands' built-in **"Agents as Tools"** pattern (officially supported,
confirmed via Strands docs) - no custom routing code needed:

```python
supervisor = Agent(
    system_prompt="Route to the right specialist based on the query...",
    tools=[dbr_agent, supplier_lockin_agent, supplier_ecosystem_agent,
           project_agent, gats_query_agent, default_agent, ...],
)
```

Each existing `make_*_agent()` factory is passed straight into the supervisor's `tools`
list (or wrapped with `.as_tool(name=..., description=...)` for finer control). The
supervisor's own LLM reads the query + department and decides which specialist(s) to
call - same tool-calling mechanic already used for MCP tools, just the "tool" happens
to be another whole agent.

**Where it fits:** one more file, `agent/orchestrator.py`, sitting alongside
`agent/agents.py` - no restructuring of Stage 1's layout needed. `cli.py`'s `ask`
command evolves to route automatically when `--agent` is omitted.

**Known risk to resolve as part of this stage:** several existing prompts overlap in
scope and will confuse a router unless their tool-descriptions are made mutually
exclusive:

| Overlapping pair | Distinction needed |
|---|---|
| `dbr` vs `default` | `dbr` = exhaustive, formal, whole-department dossier. `default` = general-purpose, same tools, less formal, narrower questions |
| `supplier_lockin` vs `supplier_ecosystem` | `lockin` = risk/dependency framing. `ecosystem` = market landscape/capability-coverage framing |

Every agent (old and new, including the 6 stubbed prompts) needs both a full system
prompt and a short, distinct router-facing description before Stage 2 can route
reliably.
