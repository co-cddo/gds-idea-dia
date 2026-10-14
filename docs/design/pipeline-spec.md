# DIA pipeline: specification

Status: agreed in outline, reviewed by Aakash on #61. The build plan in
section 7 is the agreed order of work, in small reviewable PRs, and shows what
has been built so far. Update this document as decisions change.

## 1. Purpose

Turn UK government documents into a knowledge graph in Neptune and OpenSearch
that the DIA agent can query. The documents are business cases and spending
review (SR) bids now, and contracts, NAO reports and others later.

The first goal is to get **GATS business cases** all the way into the graph.
SR bids 2025 and the other sources follow, using the same approach.

## 2. Requirements

1. **It works in dev and prod.** The same code runs in both. Prod uses real
   data. Dev may read the same real data, or a dev copy of a source.
2. **It works in stages.** Each stage saves its output to S3 and records its
   progress in a ledger. Any stage can be re-run on its own.
3. **New data flows all the way through.** Any source can receive new or
   changed documents. There must be a way to take them from the source all the
   way into the graph.
4. **It runs in the cloud.** Long-running work must not depend on someone's
   laptop or credentials lasting for the whole run.
5. **It uses batching wherever possible,** to keep cost down and throughput up.
6. **It is safe to try things.** You can rehearse any stage locally to see what
   it would do, without changing anything real.
7. **Adding a source is easy.** Adding a new kind of document doesn't need to be
   easy, but it must be well documented.
8. **It is visible.** You can see what a run did, what failed and why, and
   where any document has reached.
9. **The graph stays correct.** Queries see the current version of each
   document, and bad data can be removed.
10. **Expensive mistakes are hard to make.** Costly or destructive actions are
    explicit and confirmed.
11. **The current code is disposable.** It is work in progress that nobody uses
    yet, so it can be redesigned freely.

## 3. Design decisions

### 3.1 Stages

| # | Stage | What it does | Batching |
|---|---|---|---|
| 1 | text | Read source documents, extract text, attach metadata | Bulk S3 reads and writes |
| 2 | chunk | Split text into chunks | Bedrock batch embeddings, for semantic splitting |
| 3 | propositions | The LLM breaks chunks into simple statements | Bedrock batch inference |
| 4 | topics | The LLM extracts topics, entities and relationships | Bedrock batch inference |
| 5 | validate | Clean each document's graph: classifications, noise, entity references, metadata types | None (pure Python) |
| 6 | embed | Embed graph items for vector search | Bedrock batch embeddings |
| 7 | load | Write to Neptune and OpenSearch, as a new version of the document | Bulk writes |

These are separate steps, run on demand:

- **purge** removes documents' data from the graph, by source or by document.
- **prune** removes old graph versions. How it works is deferred.

Each stage reads only the previous stage's output and writes its own.
Propositions and topics are separate stages, so a failure in topics doesn't
mean paying for propositions again. Validate is separate, so cleaning rules can
change and be re-applied without new LLM spend. Embed and load are separate, so
embeddings can be batched and a failed load doesn't pay for them again.

The toolkit's extract function currently runs propositions and topics
together. We need to split them out by driving its batch extractor classes
directly, as ADR 0001 on the `graph-chunking` branch already plans.

**Batching rule:** stages that call Bedrock always use batch jobs. Bedrock needs
at least 100 records per job, so a smaller job is padded up to 100 with minimal
filler records, and the filler results are discarded. The run summary and the
cost estimate show how many records were padding.

### 3.2 Where things run

- **Remote** (`--remote`): the stage runs as an ECS Fargate task on the shared
  GDS IDEA ECS cluster (the `ecs_arn` from `DeploymentConfig`), under an IAM
  role. It reads and writes the real S3 buckets, ledger
  and graph. This is the only way to change real state.
- **Local** (the default): the stage runs on your laptop. It reads real data but
  writes only to `./output/`. It is for rehearsing and debugging.
  - **Ledger:** a local run takes a copy of the real ledger for that source and
    stage. `--ignore-ledger` starts from a blank one instead.
  - **Input:** you choose with a flag whether a local stage reads its input
    from local output or from the real S3 output.
  - **Model calls:** a local run of a stage that calls Bedrock uses on-demand
    calls on a small sample, because batch jobs need S3.
  - **Load:** a local load reports what it would write.
- **Orchestration:** we start tasks from the CLI and orchestrate stages
  ourselves. Step Functions is deferred.
- **Runtime configuration:** CDK writes one JSON parameter per environment to
  SSM Parameter Store, named by `Names` (`dia-runtime-config-{phase}`). It holds
  what the runtime needs to know about the deployed infrastructure: the Neptune
  endpoint and port, the OpenSearch endpoint, the ECS cluster, the task
  definition, the subnets, the security group and the log group. Tasks and
  laptops read it the same way,
  through one validated model (`dia.runtime_config.RuntimeConfig`) that stops
  straight away with a clear message if the parameter is missing or invalid. The
  task definition sets `DIA_RUNTIME_CONFIG` to the parameter's name, so the
  dependency is visible on the task. When the variable is not set, as on a
  laptop, the name is built from `Names`. The agent still reads its endpoints
  from Secrets Manager.

### 3.3 CLI behaviour

- Pipeline commands live under `dia pipeline`: one per stage, plus `status`,
  `tasks`, `sources check` and `preflight`. The agent stays under `dia agent`,
  so the two can each have commands of the same name. The existing
  `extract-text` and `ledger` commands move under `pipeline` when they are
  rewritten.
- `dia pipeline preflight` is read-only and checks what the place it runs needs:
  - Everywhere: the account and phase, the runtime config, the ledger table,
    our buckets, and read access to the source data (through the cross-account
    role in dev).
  - Inside an ECS task only: Neptune. Only tasks reach Neptune, from inside the
    VPC, so a local run never checks it.

  It exits with an error if any check fails, and it is the first command run as
  a task.
- Stages that call Bedrock have a **cost estimate** option, which reports the
  expected number of records (including padding) and the estimated cost without
  running anything.
- Common flags: `--remote`, `--limit`, `--departments`, `--ignore-ledger`,
  `--retry-failed`, a flag to include documents marked stale, and `--yes`.
- **Dev:** running any command without `--limit` warns and asks for
  confirmation, defaulting to no.
- **Prod:** every `--remote` run asks for confirmation.
- `--yes` skips confirmation prompts.

### 3.4 Sources

- A source is defined in Python. Each definition chooses three parts, and each
  part is a protocol:
  - a **reader**, which lists documents, gives each one a stable key and a
    version, and returns its content;
  - a **metadata strategy**, which attaches metadata to each document;
  - a **document type**, which decides prompts, entity classifications, ID
    field and chunking.
- **Readers:** files in S3 now; CSV rows (one row per document) later.
- **CSV sources** must name exactly one ID column. Its values must be present,
  unique across all of the source's files, and stable over time.
  - This is checked when the definition loads, on `sources check`, and on every
    read.
  - A comparison with the ledger warns when IDs change wholesale.
- **Metadata:** every source shares one common metadata shape (source, document
  type, department, ALB, title, date, ID), plus an `extra` dictionary for fields
  specific to a source. This is our *output* shape. Source documents need not
  follow it: each source's metadata strategy maps that source's own schema into
  it, so sources whose files or exports have different layouts (including
  different generations of GATS business cases) can coexist.
- **Adding a source:**
  1. Write the definition.
  2. Run `dia sources check`.
  3. Run a small trial with `--limit`.
  4. Run the full source.
- **Adding a document type:** implement the protocol, following a written guide.

### 3.5 Source locations and environments

- Each source has **one real location**: where an existing process already
  drops its files. We never copy or move source data in prod. (An earlier idea
  of copying source data into buckets of our own for each phase is dropped.)
- **Prod** reads that location directly.
- **Dev** reads the same location through the shared cross-account role
  (`assume_role_for_development_account`, from `gds_idea_cdk_constructs`). A
  source can instead name its own **dev override bucket** in our dev account.
- Metadata follows the same rules as documents.
- The pipeline only ever reads source locations, enforced in IAM. All writes go
  to the current phase's own buckets, ledger and graph.
- It is accepted that real data will exist in dev and on laptops.
- Our buckets, tables and other resources are named by phase from one place,
  shared by the CDK and the runtime code.

### 3.6 Ledger

The ledger must answer:

1. Is document X done for stage S, at its current version?
2. What is pending for a source and stage?
3. What failed, and why?
4. What settings produced this output?
5. Which batch job is document X in?
6. Which version of document X is in the graph?
7. Is this source and stage already being run?
8. Has a document disappeared from its source?

If a run finds the same source and stage already in progress, it **fails
straight away** with a message saying so. It does not wait: a person can wait
and re-run, and queuing can be added with Step Functions later.

How it behaves:

- **New or changed documents** are pending automatically, at every stage after
  the change.
- **A change to a stage's settings**, such as the prompt, marks the affected
  documents stale. They are shown in `dia status`, and re-run only when you ask.
- **Removed documents** are recorded. They stay in the graph until purged
  explicitly.
- The storage design is decided when we build it, since the existing ledger can
  be deleted.

### 3.7 Failures

- Transient errors, such as throttling, timeouts and network errors, are retried
  within the run.
- A document that still fails is marked **failed** along with its error, and
  later runs skip it.
- A failed document becomes pending again only when its source file changes, or
  a run uses `--retry-failed`.
- A batch job that fails or expires is resubmitted by the batch handling
  itself.
- `document_type` for SR bids is `sr_bids`, and the agent's retrieval modes must
  use the same value.

### 3.8 Graph updates

- Loads are **versioned**, using graphrag-toolkit's built-in versioning. A
  re-loaded document supersedes its previous version, and the old version is
  kept.
- **Purge** uses the toolkit's `delete_sources`. It only removes shared
  entities once nothing else uses them.
- **Prune** is a separate step, deferred.
- **The agent must be changed** to query current versions only. It doesn't do
  this today.

### 3.9 Logging and status

- We use **Powertools** Logger and Metrics.
- **Remote** runs log JSON to CloudWatch. **Local** runs print readable lines to
  the console and write JSON to `./logs/`.
- Every log line carries `run_id`, `phase`, `stage`, `source`, `doc_key`,
  `event`, `outcome`, `duration_ms`, `error_type` and `code_version`.
- Metrics (processed, failed and skipped per stage and source) are emitted from
  the start.
- Each stage run writes a summary file alongside its output: counts, failures,
  timings and settings.
- `dia status` reports, from the ledger, where documents have reached.
- Alerts are deferred.

## 4. Deferred

- Step Functions orchestration
- Prune design
- Alerts and dashboards
- The CSV reader, and the contracts, SR21 and NAO/GMPP sources

## 5. Open actions

- Confirm that the cross-account role can read the SR25 locations and the GATS
  metadata. It trusts the whole dev account and has `ReadOnlyAccess`, so GATS
  documents should work.
- Confirm the prod locations for GATS metadata and SR25 documents. The current
  names end in `-dev`.
- Agree the change to the agent (current versions only) with whoever owns the
  agent.

## 6. Questions for reviewers

Settled in review of #61:

- **Batch minimum:** always batch, and pad to 100 records (section 3.1).
- **Concurrency:** fail immediately if a run is in progress (section 3.6).
- **Cost:** add a cost estimate option (section 3.3).

Still open:

- **Testing:** how should stages be tested? Unit tests, plus a small end-to-end
  run in dev?
- **Permissions and ownership:** who may run `--remote` in prod, and who owns
  the pipeline day to day?

## 7. Build plan

Scope is **GATS business cases first**. Each PR is small and reviewable, is
opened as a draft, and removes the old code it replaces. Remote running comes
as early as possible so every later stage is built to run as a task. Tick each
PR off and add its link as it is raised.

### Milestone A: remote running

- [x] 1. Spec update, this build plan and the handover (docs only) (#62)
- [x] 2. Naming: one module of phase-based names, used by both the CDK config
  and the runtime code (#62)
- [x] 3. Docker image of the `dia` package, with a local build check (#63)
- [x] 4a. The runtime config model and `dia pipeline preflight` (#65)
- [x] 4b. ECS task definition and IAM in CDK (read-only on source locations),
  the security group for Neptune access, and the runtime config parameter (#66)
- [ ] 5. `--remote` and `dia tasks`: launch any command as a task, and list
  recent tasks with status and a log link

### Milestone B: sources (GATS)

- [ ] 6. Source protocols and the common metadata model
- [ ] 7. S3 file reader, with cross-account access and the per-source dev
  override. It should also: narrow the cross-account session to the source's
  bucket and prefix (a session policy on `AssumeRole`, because the shared role
  can read all of production), and use refreshable credentials (a task's
  credentials are role credentials, so a second `AssumeRole` is role chaining and
  its sessions last at most an hour, which a long extraction in dev would outlast)
- [ ] 8. GATS metadata strategy (after looking at real GATS documents)
- [ ] 9. GATS source definition and its validation, replacing
  `sources/known.py` and `metadata/registry.py`
- [ ] 10. Powertools logging and metrics

### Milestone C: ledger and text stage

- [ ] 11. New ledger: the protocol, an in-memory version and a local-copy
  version
- [ ] 12. DynamoDB ledger: the new table in CDK, and failing fast when a run is
  already in progress
- [ ] 13. Shared CLI options and the confirmation prompts
- [ ] 14. Text stage rebuilt on the new pieces, removing the old runner and
  flags
- [ ] 15. `dia sources check` and `dia status`

### Milestone D onwards (to be planned in detail)

Chunk (reusing the `graph-chunking` work, split into several PRs), propositions
and topics (batch with padding, plus the cost estimate), validate (porting the
old repo's cleaning code), embed, load, purge, and the agent change to query
current versions only. SR bids 2025 and the other sources follow.
