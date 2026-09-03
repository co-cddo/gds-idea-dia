# Assurance Agent Refactor - Decisions & Plan

## Context

Refactor the assurance agent so it can be run via CLI (dia agent ask ...).

> **Direction update (superseded goal):** the original end goal below this line was
> "agent delegation" - a supervisor agent routing queries to ~12 hand-written specialist
> agents (DBR, supplier lock-in, project investigation, etc.). That approach (Decision 7 +
> Stage 2, further down this doc) is **superseded by Decision 8**: one agent, with a set of
> **skills** it can pull in based on the query, replacing the per-department specialist
> agents and the supervisor/router concept entirely. Decision 7 and Stage 2 are kept below
> for historical context but should not be implemented as written.

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

> **Superseded by Decision 8.** No `--agent` flag ships. There is one agent; skills
> replace per-persona selection. Kept below for historical context only.

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

## Decision 8: Single agent + skills, not per-department specialist agents

**Considered:** Continue building out the ~12 hand-written `make_*_agent()` personas
(one system prompt per use-case: DBR, supplier lock-in, supplier ecosystem, project
investigation, etc.) plus a Stage 2 supervisor/router agent to pick between them
(Strands "Agents as Tools"), vs. collapsing down to **one agent** that dynamically pulls
in **skills** based on the query, instead of selecting an entire bespoke system prompt.

**Chose: one agent + skills.** Rationale:
- Maintaining ~12 near-duplicate system prompts (with real overlap - see the
  `dbr`/`default` and `supplier_lockin`/`supplier_ecosystem` pairs called out in Stage 2
  below) doesn't scale, and a router just adds a second LLM call to disambiguate prompts
  that are already too similar to disambiguate reliably.
- A single agent with composable skills means new capabilities are additive (drop in a
  new skill) rather than requiring a whole new system prompt + factory function +
  router-facing description to keep in sync.
- This removes the need for a `--agent` flag (Decision 7) and a supervisor/router stage
  (Stage 2) entirely - both are superseded by this decision.

**Not yet decided (explicitly deferred, separate follow-up conversation):**
- Skills folder/module structure (e.g. `agent/skills/<name>.py`, a registry, how a skill
  is declared/discovered).
- How the agent selects which skill(s) to use for a given query (tool-calling into a
  skill-listing tool? Always-loaded skill index? Something else?).
- What happens to the existing 12 `make_*_agent()` factories and their prompt files -
  likely most of their content becomes skill content, but this migration is out of scope
  for the CLI-wiring work (PR1/PR2 below), which only wires up `make_default_agent()`.
- **Department must stay optional in the new prompt/skill design.** `AgentInput` and
  `AgentResponse.department` are already `str | None = None` (to support cross-government
  queries not tied to one department). The current per-flavour prompt templates
  (`prompts/templates/*.py`, `prompts/fragments/query_templates.py`,
  `output_specs.py::dbr_output_card`) are **not** all `None`-safe today - some do
  `department_name.upper()`/`.lower()` directly (crashes on `None`), others just
  f-string-interpolate it (renders the literal word "None" into the prompt). Only the
  `supplier_lockin`/`supplier_ecosystem` templates already handle this correctly
  (`scope = f"for {department_name}" if department_name else "across central
  government"`). Whichever skill(s) replace these prompts must build in that same
  "no department = cross-government, not a crash and not the literal string None"
  handling from the start, rather than re-inheriting the gap.

**What this means for the CLI-wiring work (PR1/PR2, see below):** since there's no
`--agent` flag, the CLI-wiring PRs deliberately keep things simple - no agent registry,
no dispatch logic. `runtime.ask()` calls `agents.make_default_agent(department)` only.
The skills design is a separate, later piece of work.

---

## Stage 1 structure

**Status: steps 1-9 below are done (on `dev`).** Only step 10 (CLI wiring) remains -
see "Stage 1b - CLI wiring (PR1 + PR2)" further down for the detailed breakdown of what
that step actually involves.

```
gds-idea-dia/
├── src/dia/
│   ├── cli.py                     # existing — gains `agent_app` sub-Typer (same pattern as `ledger_app`)  [PR2]
│   ├── config.py                  # existing pipeline config — untouched
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── config.py               # pydantic-settings: model id, Athena DB/workgroup names, KB secret names, mcp_port  [done]
│   │   ├── patches/
│   │   │   ├── __init__.py         # apply_all()  [done, not yet called anywhere — PR1 wires this in]
│   │   │   ├── search_result.py    # ISO-timestamp fix  [done]
│   │   │   ├── neptune_timeout.py  # 90s read_timeout override  [done]
│   │   │   ├── retry.py            # unretriable-exception + retry-floor fix  [done]
│   │   │   └── entity_search.py    # two-step capped multi-entity query rewrite  [done]
│   │   ├── stores.py               # build_graph_store(), build_vector_store(), build_graph_index()  [done]
│   │   ├── mcp/
│   │   │   ├── server.py           # build_mcp_server(), start_server(), server_url()  [done, but doesn't register the 4 tool modules yet — PR1 wires this in]
│   │   │   ├── retrieval_modes.py  # update_tool_params(), mode text, filter builders  [done]
│   │   │   └── tools/
│   │   │       ├── __init__.py     # gains register_all_tools()  [PR1]
│   │   │       ├── athena.py       # [done]
│   │   │       ├── graph.py        # [done]
│   │   │       ├── knowledge_base.py  # [done]
│   │   │       └── web_search.py   # [done]
│   │   ├── prompts/                # [done]
│   │   ├── agents.py                # make_model(), make_agent(), per-prompt factories  [done, but missing imports for 10 prompt functions — PR1 fixes this]
│   │   ├── runtime.py               # NEW — end-to-end bootstrap: patches -> stores -> mcp server -> agent -> answer  [PR1, gains `tunnel` param in PR2]
│   │   ├── tunnel.py                 # NEW — open_tunnel() context manager, automates the SSH tunnel + register_tunnel_host dance  [PR2]
│   │   └── report.py                # markdown response → .docx → S3  [stub, out of scope for PR1/PR2 — Decision 6, deferred, stdout only for now]
│   └── ... (existing pipeline modules, untouched)
└── pyproject.toml                   # [project.optional-dependencies] agent = [...]  [done]
```

### Migration steps

1. ~~Scaffold `src/dia/agent/` skeleton + `config.py`.~~ **Done.**
2. ~~Move the 4 patches verbatim into `patches/`.~~ **Done** (not yet wired to run - PR1).
3. ~~Move store construction into `stores.py`.~~ **Done.**
4. ~~Move MCP server lifecycle + mode-parsing logic into `mcp/server.py` / `mcp/retrieval_modes.py`.~~ **Done** (doesn't register the 4 tool modules yet - PR1).
5. ~~Split Athena/graph/KB/web-search tools into `mcp/tools/*`.~~ **Done** (nothing calls their `register()` functions outside tests yet - PR1).
6. ~~Copy/write the prompt files.~~ **Done.**
7. ~~Move model/agent factories into `agents.py`.~~ **Done** (missing 10 imports - PR1 fixes).
8. `report.py` (markdown → docx → S3 upload). **Deferred** - out of scope for PR1/PR2, stdout only (see Decision 6 note above).
9. ~~Add `[project.optional-dependencies] agent` to `pyproject.toml`.~~ **Done.**
10. Add `agent_app` Typer sub-app + `ask` command to `cli.py`, and everything needed to actually run the chain end-to-end. **This is PR1 + PR2 - see breakdown below.**
11. Tests: patches (idempotency, existing), retrieval_modes (existing), plus new tests per PR1/PR2 below.

---

## Stage 1b - CLI wiring (PR1 + PR2)

This is the detailed breakdown of migration step 10 above - the only step not yet done.
Split into two PRs so PR1 (pure wiring, fully mockable) can land and be reviewed
independently of PR2 (CLI + live-AWS tunnel concerns).

### PR1 - Internal wiring (no CLI, no networking)

Makes the existing pieces actually connect, provable via mocked tests, before any CLI
exists.

1. **`agents.py`** - add the missing import block for the 10 prompt-template functions
   it calls but never imports (currently masked by a `ruff` per-file-ignore for
   `F821`/`F822` - remove that ignore once fixed).
2. **`mcp/tools/__init__.py`** - add `register_all_tools(mcp_server)`, calling
   `athena.register()`, `graph.register()`, `knowledge_base.register()`,
   `web_search.register()`.
3. **`mcp/server.py`** - `build_mcp_server()` calls `register_all_tools(server)` before
   returning, so the finished server exposes `default_` (1) + Athena (3) + graph-timeout
   helper (1) + KB search (5) + web search (1) = **11 tools across the 4 registered
   modules** (satisfies the "all 4 MCP tools registered" AC).
4. **New file `agent/runtime.py`** - the orchestration chain:
   ```python
   """End-to-end agent bootstrap: config -> stores -> MCP server -> agent -> answer."""

   from dia.agent import agents, stores
   from dia.agent.config import settings
   from dia.agent.mcp import server as mcp_server
   from dia.agent.patches import apply_all

   def ask(department: str, query: str) -> str:
       apply_all()
       graph_store = stores.build_graph_store(settings.neptune_endpoint)
       vector_store = stores.build_vector_store(settings.aoss_endpoint)
       stores.build_graph_index(graph_store, vector_store)
       server = mcp_server.build_mcp_server(graph_store, vector_store)
       mcp_server.start_server(server)
       agent = agents.make_default_agent(department)
       result = agent(query)
       return str(result)
   ```
   No `--agent` dispatch/registry - matches Decision 8, only `make_default_agent()` is
   wired for now.
5. **Tests:** `test_agent_mcp_tools_init.py` (register_all_tools calls all 4
   `register()`s), extended MCP-server test (build_mcp_server results in all 11 tools
   registered), extended `test_agent_agents.py` (all `make_*_agent()` factories build
   their prompt string without `NameError` now that imports are fixed), new
   `test_agent_runtime.py` (`@pytest.mark.integration`, mocks `stores.*`,
   `mcp.server.build_mcp_server/start_server`, `agents.make_default_agent` at the
   boundary; asserts `apply_all()` runs before store construction, full chain called in
   order, fake agent receives `query`, `ask()` returns `str(result)`).

### PR2 - CLI command + automated tunnel

Adds the actual `dia agent ask` entrypoint and automates what
`scripts/neptune-agent-tunnel.py` currently demonstrates by hand (open the SSH tunnel,
then `register_tunnel_host(...)`) into the real agent code path.

1. **New file `agent/tunnel.py`** - `@contextmanager open_tunnel(phase="dev", port=8182,
   timeout=30.0)`: if port 8182 already has a live tunnel, reuse it (no teardown on
   exit); otherwise spawns `scripts/neptune-tunnel.sh {phase}` as a background
   subprocess, polls until the port accepts connections or times out, calls
   `dia.clients.neptune.register_tunnel_host(settings.neptune_endpoint)`, yields, then
   in `finally` (only if we started it) kills the subprocess's process group so no
   orphaned `aws ec2-instance-connect ssh` process is left running.
2. **`runtime.py`** - `ask()` gains a `tunnel: bool = False` keyword param:
   ```python
   from contextlib import nullcontext

   def ask(department: str, query: str, *, tunnel: bool = False) -> str:
       ctx = nullcontext()
       if tunnel:
           from dia.agent.tunnel import open_tunnel
           ctx = open_tunnel()
       with ctx:
           ...  # same body as PR1
   ```
   `tunnel=False` (PR1's tests) is unaffected - `nullcontext()` means zero behaviour
   change on that path.
3. **`cli.py`** - a thin pass-through, no logic beyond argument wiring:
   ```python
   agent_app = typer.Typer(help="Query the assurance agent.")
   app.add_typer(agent_app, name="agent")

   @agent_app.command("ask")
   def agent_ask(
       department: Annotated[str, typer.Option("--department", help="Department to scope the query to.")],
       query: Annotated[str, typer.Option("--query", help="Natural-language question for the agent.")],
       tunnel: Annotated[bool, typer.Option("--tunnel", help="Auto-open the Neptune dev SSH tunnel for this run.")] = False,
   ):
       from dia.agent import runtime
       typer.echo(runtime.ask(department, query, tunnel=tunnel))
   ```
4. **Tests:** `test_cli_agent.py` (`CliRunner` invokes `dia agent ask --department ...
   --query ...` with `dia.agent.runtime.ask` mocked, asserts pass-through + echoed
   output, including that `--tunnel` maps to `tunnel=True`), `test_agent_tunnel.py`
   (mocks `subprocess.Popen`/socket-connect to test readiness-poll/reuse-existing/
   timeout/teardown logic without real AWS/SSH), and an extension to
   `test_agent_runtime.py` covering the `tunnel=True` path (mocks `open_tunnel`, asserts
   it wraps the chain). Manual (non-automated) verification, since it needs real AWS/SSH:
   `uv run dia agent ask --department "Home Office" --query "..." --tunnel` against dev.

---

## Stage 2 - Agent-to-agent (supervisor/router)

> **Superseded by Decision 8.** This entire stage - a supervisor agent routing between
> ~12 hand-written specialists - is replaced by the single-agent-plus-skills direction.
> Kept below for historical context (the overlapping-prompt-pairs table is still useful
> input for whoever designs the skills split) but should not be built as written.

~~Starts only after Stage 1 fully ships (sequential, not parallel).~~

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
