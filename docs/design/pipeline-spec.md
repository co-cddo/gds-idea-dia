# DIA pipeline: specification (draft for feedback)

Status: draft. Nothing here is built yet. The aim of this document is to agree
the requirements and the main design decisions before we start rebuilding the
pipeline.

## 1. Purpose

Turn UK government documents into a knowledge graph in Neptune and OpenSearch
that the DIA agent can query. The documents are business cases and spending
review (SR) bids now, and contracts, NAO reports and others later.

The first goal is to get **GATS business cases** and **SR bids 2025** all the
way into the graph. Other sources follow, using the same approach.

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
change and be re-applied without new LLM spend.

### 3.2 Where things run

- **Remote** (`--remote`): the stage runs as an ECS Fargate task in our
  account, under an IAM role. It reads and writes the real S3 buckets, ledger
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

### 3.3 CLI behaviour

- There is one command per stage, plus `dia status`, `dia tasks` and
  `dia sources check`.
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
  specific to a source.
- **Adding a source:**
  1. Write the definition.
  2. Run `dia sources check`.
  3. Run a small trial with `--limit`.
  4. Run the full source.
- **Adding a document type:** implement the protocol, following a written guide.

### 3.5 Source locations and environments

- Each source has **one real location**: where an existing process already
  drops its files. We never copy or move source data in prod.
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

- Confirm that the prod cross-account role can read the GATS and SR25 locations
  (documents and metadata), and who manages that role.
- Confirm the prod locations for GATS metadata and SR25 documents. The current
  names end in `-dev`.
- Agree the change to the agent (current versions only) with whoever owns the
  agent.

## 6. Questions for reviewers

- **Testing:** how should stages be tested? Unit tests, plus a small end-to-end
  run in dev?
- **Cost:** a rough Bedrock cost per 1,000 documents would help people judge
  `--limit` and stale re-runs.
- **Permissions and ownership:** who may run `--remote` in prod, and who owns
  the pipeline day to day?
- **Batch minimum:** Bedrock batch jobs need at least 100 records. Small
  incremental updates need on-demand calls instead, as the chunking plan
  already notes. Should this be a stated rule?
- **Concurrency:** if a run finds the "already running" lock held, should it
  wait or fail?

## 7. Proposed build order (not yet agreed)

1. Foundation: naming, source protocols and the S3 file reader, metadata
   strategies, cross-account reads, the new ledger, logging, the CLI shape, and
   deleting the old code.
2. The text stage, plus `sources check` and `status`.
3. Remote running: Docker image, ECS task, IAM, `--remote` and `dia tasks`.
4. Chunk, reusing the `graph-chunking` work.
5. Propositions and topics, including batch job tracking and recovery after a
   crash.
6. Validate, porting the old repo's cleaning code.
7. Embed.
8. Load and purge.
9. The agent change to query current versions only.

Two points in particular need agreement: whether remote running (step 3) comes
early or after load, and whether the CSV reader is built after load or earlier.
