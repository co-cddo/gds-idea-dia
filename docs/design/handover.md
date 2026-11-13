# Handover

This is the working handover for the DIA pipeline, written when David Gillespie
handed the work over to Aakash. It is for whoever picks the work up next, human or
agent. It goes stale quickly: **update it at the end of every PR**, and keep section
1 accurate above all.

The agreed design is in [`pipeline-spec.md`](pipeline-spec.md), and its section 7 is
the build plan. This file covers where things stand, what to do next, and the
facts that are not obvious from the code.

## 1. Where things stand

State when this was written, with `dev` at #78. Check `gh pr list` and
`git log origin/dev` before relying on it.

**Built, and run for real in dev**

- **Remote running.** `dia pipeline preflight --remote` starts a task on the shared
  ECS cluster, follows its logs, and exits with the task's exit code. `dia pipeline
  tasks` (with `--mine`), `tasks logs <id> [--follow]` and `tasks stop <id>` work
  against real ECS. All six preflight checks pass in a task, including Neptune.
- **The task stack, image and runtime config.** The Fargate task definition, its
  roles, the log group, the task image (`task/Dockerfile`, `pipeline` extra only) and
  the SSM runtime config parameter are deployed. CI builds the image and deploys on
  every merge to `dev`. A CI job imports every task module inside the built image.
- **Naming.** One module, `dia.naming`, builds every deployed name from the phase.

**Built, but not run against real AWS**

- **Knowledge base stack (#77).** `stacks/knowledge_base.py` builds the Bedrock
  knowledge bases from the `SOURCES` that have a `knowledge_base` block and
  `deployed=True`: today the two DBR ones. One retained S3 Vectors bucket, and per KB
  a retained index, a role that reads only its own prefix, the KB and its data source.
  A dev KB that reads the GATS bucket (declared, not deployed) is cross-account, so
  the prod bucket's policy must allow the KB role first. Deploying creates empty KBs:
  upload the documents and sidecars, then start an ingestion job per data source. The
  `dia-kb-arns` secret is not written from CDK; its values are set by hand, so the KB
  IDs are stack outputs for now. Plan: `docs/knowledge-bases-plan.md`.

- **Shared source declarations (#78).** Every dataset is declared once in
  `src/dia/sources/definitions.py`, whichever pipeline uses it. Preflight and the
  task stack read them, and the four new knowledge base buckets exist in CDK.
  Preflight's source check is now called `source gats_business_cases` and reads the
  declarations. Run `uv run dia pipeline preflight` once to confirm it works against
  real AWS; nobody has yet.

**Agreed, not built**

- **Two pipes, kept separate.** *Graph*: our extraction into Neptune and OpenSearch.
  *Knowledge base* (KB): Bedrock reads the documents. They complement each other.
- **Metadata is its own step**, separate from both pipes. For every document in
  every source it writes a `<document>.metadata.json` sidecar next to the document,
  in Bedrock's format (`{"metadataAttributes": {...}}`), including in buckets we
  don't own, such as GATS. A typed model holds the field names, which match the keys
  the KBs already use. The KB reads the sidecar as it is. The graph's text stage reads
  it and adds the fields to the extracted text, and **skips and logs a document that
  has no sidecar**.
- **Who writes sidecars where.** A bucket of ours: either phase writes its own. A
  bucket we only consume, such as GATS: only prod writes, because dev reads it
  through the read-only cross-account role. A dev run of the metadata step warns that
  it cannot write there. So the GATS sidecars need a prod run first.
- **A minimal ledger from the start.** Proposed shape: a new table
  `dia-pipeline-ledger-{phase}`, partition key `source#stage`, sort key
  `document_key#version`, recording done or failed per document with the reason, the
  output location and the code version. Add the in-progress lock, stale settings,
  batch job state and graph version when a stage first needs them. The old
  `dia-ledger-{phase}` table stays until the code using it is deleted.
- **The trial run.** Take the **latest 10 GATS business cases** from scratch through
  every stage into the dev graph, and ask the agent about them. Each stage is a new
  `dia pipeline <stage>` command that runs locally and with `--remote`. What
  "latest" means is not decided (see section 2).

**Not started:** the metadata step, the ledger, and every stage after text.

**Old code still in the repo.** The rest of `src/dia` is the first build: `extract-text`
and its runner, `sources/known.py`, `DataSource`, the `metadata` package, the old
ledger and its CLI, writers, filters, and the agent. Only the old text stage ever ran
(see `docs/extract-text.md`). It is disposable: each PR removes what it replaces.

## 2. What to do next

Follow section 7 of the spec. In short, the order is:

1. **Metadata model and sidecar format.** Shared code, no AWS, lots of unit tests.
   Both the metadata step and the text stage depend on it.
2. **The GATS metadata step.** The first thing that reads real GATS data.
3. **The minimal ledger.**
4. **S3 reader and the text stage**, which delete `known.py`, `DataSource`,
   `extract-text` and the old metadata package.
5. **Chunk, propositions, topics, validate, embed, load**, then check the result with
   the agent.

Then harden the ledger and CLI, and scale up to all of GATS and the other sources.

**Decisions to make first**

- **What "latest" means** for the trial run. The GATS export has 198 columns. The
  candidate date columns are `CO_CaseSubmitDate`, `CO_FullCaseDecisionDate` and
  `CO_AssuranceRatingDate`, and `CO_CaseStatus` could limit it to decided cases.
  Look at the real values before choosing. `scripts/check_source_access.py` is a
  read-only starting point.
- **Whether `--limit` counts cases or documents.** A GATS case lists several files in
  `CO_CS_Files`, so 10 cases may be 20 to 40 documents.
- **Which GATS export is current.** The dev bucket's newest export is from 20 May 2026,
  but documents are still arriving (newest 20 Oct 2026). The prod bucket has its own
  `spend-controls-raw-data/` folder that nobody has looked inside. It is probably the
  live one.
- **How the ledger table is laid out**, using the proposal above.

**What we know about the GATS data** (from `scripts/check_source_access.py`, October 2026)

- Documents: `s3://c-af-get-approval-spend-service-business-cases/files/`, in the prod
  account, 26,187 objects. By type: 10,778 `.json`, 7,477 `.docx`, 4,190 `.pdf`,
  1,731 `.pptx`, 1,688 `.xlsx`, and a few `.png`, `.doc` and `.eml`. The `.json` files
  are old sidecars written by the previous repo's script, and will be replaced.
  Our extractors only read PDF and Word, so other types must be recorded as
  unsupported, not failed.
- The cross-account role can read this bucket. A dev session can read it directly too,
  so its bucket policy allows the dev account.
- Metadata today: a copy of the export and the historic CSVs are in
  `c-af-get-approval-spend-service-business-cases-dev`, a bucket in the **dev**
  account. A dev session reads it directly, and the cross-account role is denied.
  Its `spend-controls-raw-data/` has three `DataExport_*.csv` files and
  `department_files/` has `historic_cases_metadata.csv`.
- Export columns that matter: `CO_SpendID` (the case ID), `CO_CS_Files` (the case's
  files), `CO_OrganisationSubmitter` (department or ALB), and the dates above.
  Departments go through `department_mapping.py`. There are reportedly cases with more
  than one source schema; look at real documents before writing the strategy.

## 3. Open PRs, branches and issues

**Empty source buckets.** The four sources that were dev-account buckets (SR25, SR21,
NAO, the DIA documents) now point at new, **empty** buckets of ours. Their KBs aren't deployed, so nothing
breaks, but the documents must be copied in before they are (#64).

**#53, the chunking draft.** About 3,500 lines, untouched since September. The design
is on the `graph-chunking` branch: `docs/adr/0001-lower-level-graphrag-toolkit-usage.md`
and `docs/plans/graph-extraction-stage.md`. The ADR says to drive the toolkit's batch
extractors directly and persist chunks. The plan lists open questions, mainly where
batch job state lives. Use it as the reference when you reach the chunk stage; the
code is better rewritten small than merged as it is. Whether to split it up or close
it is your call. The `graph-extraction-runner` branch is abandoned.

**Issues**

- #64: move the KB source buckets we own into this repo, and copy the documents in.
- #67: set a maximum run time for pipeline tasks. Tasks only stop when the container
  exits or someone stops them.
- #68: let stages use different task sizes. Extraction is mostly batching and is fine
  on a small task; the build step runs several batch workers and needs more CPU.
- #48 to #52: chunking and semantic splitting (cost, chunk size, Cohere embeddings).

**Local branches.** Most are merged or abandoned history from the first build. Delete
what you don't need.

## 4. Open actions (not code)

- **`gds-idea-dia` cannot deploy to prod yet.** In `gds-idea-cdk-access`, add
  `"gds-idea-dia",` (no `@<repo-id>` suffix, matching its dev entry) to the list in
  `repositories_access_prod.tf`. That file controls who can assume `cdk-prod-deploy`;
  without it a merge to the `prod` branch fails at the AWS login. Prod changes need a
  reviewer from `@co-cddo/gds-idea-aws` or `@co-cddo/gds-idea-senior-ds`. The GATS
  sidecars can only be written from prod, so this is needed before the metadata step
  is useful.
- **Confirm the prod location of the GATS metadata.** The prod GATS documents bucket
  is confirmed. Only the dev copy of the export has been read.
- **The agent must query current versions only.** Graph loads are versioned, and the
  agent doesn't yet filter to the current one. Coordinate with whoever owns the agent.
  Also move the agent onto `RuntimeConfig` in place of its hand-filled Secrets Manager
  endpoints, which can drift (raised on #65).
- **Agree with the data owners that we add sidecar files** to the GATS bucket.
- **Questions on testing and ownership** in spec section 6: how stages are tested, and
  who may run `--remote` in prod.
- **The load stage needs** an `aoss` permission on the task role (the OpenSearch data
  access policy names the account root as principal), Bedrock access for the Bedrock
  stages, and an OpenSearch check in preflight.
- **The S3 reader needs** refreshable cross-account credentials and a narrowed session
  policy (see the cross-account role under "Key facts").
- **A post-deploy smoke test** that runs `dia pipeline preflight --remote` in dev and
  fails on a non-zero exit. The command supports it. The dev deploy role would need
  `ecs:RunTask` and `iam:PassRole`, and it needs its own `workflow_run` workflow,
  because `ci_cd_cdk_app.yml` belongs to `idea-app`.
- Run `idea-app update --dry-run` (adopted at 0.5.4; 0.6.0 is installed) and decide
  whether to update.
- Names still outside `dia.naming`: the agent's secret names (hardcoded to `-dev` in
  `agent/config.py`), the stack names in `scripts/neptune-tunnel.sh`, and the `phase`
  default in `clients/graph_rag_config.py`.
- Generic stack names such as `StorageStack` don't meet the CDK review standard. They
  are left alone, because renaming makes CloudFormation replace the resources.

## 5. How the repo works

- **Small, reviewable PRs.** One thing per PR, with tests, opened as a draft. Each PR
  removes the old code it replaces, rather than one large deletion at the end.
- **Scope is GATS business cases first.** Other sources follow with the same approach.
- **AI review.** Add the `ai-review` label for an advisory review from
  `gds-idea-ai-reviewer[bot]`. It is non-blocking, and no label means no run and no
  cost. It does not re-run on a push, so remove and re-add the label. Its job shows
  green even when skipped (for example when the App isn't installed), so read the job
  log. It reviews the commit current when the label was added. Reply to its findings
  by item number: what was fixed, and what was left and why. It needs the `ai-review`
  job in `ci_pr_cdk_app.yml`, the org secrets `GDS_IDEA_AI_REVIEWER_APP_ID` and
  `GDS_IDEA_AI_REVIEWER_APP_PRIVATE_KEY`, and the `gds-idea-ai-reviewer` GitHub App
  installed on the repo.
- **`ci_pr_cdk_app.yml` is managed by `idea-app` but edited by hand,** and should stay
  that way. The template sets `run-version-check: true`, which fails here because the
  version comes from git tags (hatch-vcs) and `pyproject.toml` has no `version =`
  line. We also differ from the template in other ways: the trigger includes
  `reopened`, and the jobs skip on any `labeled` event (the template skips only for
  the `ai-review` label, so any other label re-runs all of CI). There is no `branches:`
  filter, so a PR stacked on another branch still gets build, lint, tests and the AI
  review. The CDK diff is skipped for those, because the catalogue's `ci_cdk_diff.yml`
  only supports `dev` and `prod` as targets. If you run `idea-app update`, don't use
  `--force` on that file. The other workflows are `idea-app`'s, except
  `ci_task_image_smoke_test.yml`, which is ours.
- **CI deploys on merge:** the `dev` branch to the dev account, `prod` to prod.
- **The CDK diff comment warns `TaskDefinition ... WILL_REPLACE`** whenever a PR
  touches `src/`, `task/` or `pyproject.toml`. The image hash is part of the task
  definition, so each change registers a new revision. That is expected. Old revisions
  stay in ECS and nothing is deleted.
- **To prove a CDK change renames nothing,** build every stack for dev and prod with
  a fake VPC (`ec2.Vpc.from_vpc_attributes`, as `tests/test_pipeline_task_stack.py`
  does), dump `Template.from_stack(...).to_json()` before and after, and compare the
  files byte for byte. Stacks that should be unchanged must be identical. A script
  wired the way `app.py` wires the stacks, ending in `app.synth()`, also catches
  dependency cycles.
- **Task image.** It has no Node, no CDK and only the `pipeline` extra, so a module
  that needs anything else works on a laptop and fails when a task starts. Add a
  module to `TASK_MODULES` in `task/smoke_test.py` when a task command starts to use
  it; CI and `tests/test_runtime_imports.py` check the list. The image still contains
  `aws-cdk-lib` (about 220MB) because `gds-idea-cdk-constructs` depends on it. It is
  never loaded. Making it an optional extra upstream would remove it, but is a
  breaking change for every app that builds stacks.
- **CLI tests.** typer colours its errors in GitHub Actions, which splits text with
  ANSI codes. Strip them before matching, as `tests/test_cli.py` does.

## 6. Key facts

**Infrastructure**

- Pipeline tasks run on the **shared GDS IDEA ECS cluster**, from the `ecs_arn` in
  `DeploymentConfig` (SSM `/gds-idea-ecs`). Step Functions is deferred.
- **Phase** comes from the AWS account (`DeploymentEnvironment`). Dev is
  `992382722318`, prod is `588077357019`.
- **Names:** `dia.naming.Names` builds every deployed name. `names("ledger")` gives
  `dia-ledger-dev`, and `names(Bucket.TEXT_EXTRACTED)` gives
  `gds-idea-dia-text-extracted-dev`. A plain string that matches a bucket is rejected,
  so a bucket can't silently get the resource pattern. In CDK use `config.names`. In
  the CLI use `dia.cli_helpers.current_names()`.
- **Dependencies are split into extras:** the core is what the CLI and naming need.
  `pipeline` is the document pipeline, `agent` is the agent and its report output,
  and `cdk` is for CDK. CI uses `uv sync --all-extras`.
- **Pipeline task stack** (`stacks/pipeline_task.py`): one Fargate task definition,
  2 vCPU and 8GB, built for x86_64 with `dia` as the entrypoint. The task role is
  `dia-pipeline-task-{phase}` with the account's `DenyUserPermissionsPolicy` boundary
  (it removes nothing). It can use the ledger, our pipeline buckets, Neptune (read,
  write and delete via query, and engine status), the runtime config parameter, and
  read the buckets of the graph sources. It has **no Bedrock or OpenSearch access
  yet**. Logs go to `/dia-task-{phase}` for 90 days (kept in prod, deleted with the
  stack in dev). Tasks use the shared VPC's private subnets, which have outbound
  access, with no public IP. Their security group is in `NetworkingStack`, and
  `NeptuneStack` allows it in on 8182.
- **Buckets of ours** are the `Bucket` enum. The storage stack creates all of them in
  both phases. The pipeline ones are text-extracted, graph-raw, graph-validated,
  batch and agent-reports. The KB ones are dbr-reports, sr25-bids, sr21-bids,
  nao-reports and reports. **Preflight checks a named list**
  (`dia.preflight.PREFLIGHT_BUCKETS`), so KB buckets are not on it and the task role
  has no access to them. A new pipeline bucket must be added to the list and needs a
  read grant in `stacks/pipeline_task.py` (a test checks this). S3 Vectors buckets
  don't belong in the enum.
- **Runtime config:** CDK writes the Neptune endpoint and port, the OpenSearch
  endpoint, the cluster, task definition, subnets, security group, log group and (in
  dev) the cross-account role as one JSON parameter, `dia-runtime-config-{phase}`.
  `dia.runtime_config.RuntimeConfig.load` reads it and fails fast. The task sets
  `DIA_RUNTIME_CONFIG` to its name; locally the name is built from `Names`. To add a
  value, add the field to `RuntimeConfig` and to the stack; unknown fields are
  rejected, so the two can't drift. The OpenSearch endpoint arrives as
  `https://<id>.aoss.eu-west-2.on.aws`, and the model strips the scheme.

**Cross-account role** `assume_role_for_development_account` (production account)

- It trusts the whole dev account with no conditions, and has `ReadOnlyAccess` plus
  Lake Formation, Bedrock knowledge base, Athena and S3 Tables policies. The dev task
  role only needs `sts:AssumeRole` on it, which the stack grants.
- It can read all of production, not just GATS. The S3 reader should narrow a session
  to the source's bucket and prefix with a session policy on `AssumeRole`.
- A task's credentials are role credentials, so assuming the role is role chaining
  and sessions last **at most an hour**. A long run in dev needs refreshable
  credentials. Preflight needs only a moment, so isn't affected.
- It is **read-only**, and it **cannot read buckets in the dev account** (denied by
  the bucket's policy). Use it only for buckets with no dev equivalent.

**Sources** (`dia.sources.models`, `dia.sources.definitions`)

- `SOURCES` is the one table. Keys are snake_case and KB names derive from them. Each
  entry has a location, a document type, extra metadata keys, a `graph` flag and/or a
  `knowledge_base` block (`parsing_model`, `deployed`).
- A **location** is a `Bucket` member (ours: exists in dev and prod, we may write to
  it) or an `ExternalBucket` (another team's): the prod bucket plus exactly one of a
  dev bucket or `dev_via_cross_account=True`. Names are never derived or guessed.
  `resolve(location, environment)` gives the bucket, prefix, whether to read it
  through the role, and whether it is ours.
- GATS is the only external source. Only the two DBR KBs are `deployed=True`.
- `DocumentType` values match what the agent filters on (SR bids are `sr_bids_2025`
  and `sr_bids_2021`), and a test checks they agree. Each type's `id_field` is the
  identifying entity for graph extraction: Spend ID for business cases, Bid Name for
  SR bids, Contract ID for Contract Finder, Report Name for NAO and technology
  reports, Department Name for efficiency reports and DBR reports, and Readout Date
  for DBR letters. The KB-only types use placeholders; splitting `DocumentType` into
  plain values plus graph config is the cleaner fix, as its own PR.

**Remote running** (`src/dia/remote.py`; `cli.py` only wires it up)

- Later stage commands should reuse `_run_remote` in `cli.py` (launch, follow, exit
  code) and add their own confirmation and `--limit` rules. The confirmations in spec
  section 3.3 aren't built: the only remote command is read-only.
- Tasks run on Fargate with the subnets and security group from the runtime config.
  The command override goes on the container named `Pipeline`, whose entrypoint is
  `dia`. Log streams are `pipeline/Pipeline/<task-id>` in `/dia-task-{phase}`.
- `startedBy` is `dia-cli/<name>`, from the caller's role name up to its first hyphen
  (`david.gillespie-poweraccess` gives `dia-cli/david-gillespie`), or the whole role
  name if that part has no dot. It has no timestamp, because `list_tasks` can only
  filter by exact value and a per-run value would break `--mine`.
- The cluster is shared with web apps, so tasks are always listed by the task
  definition family `dia-pipeline-task-{phase}`. ECS forgets stopped tasks after about
  an hour; older runs are only in CloudWatch. A task ECS has been asked to stop shows
  as `STOPPING` (our label, not an ECS status).
- To launch tasks a developer's role needs `ecs:RunTask`, `iam:PassRole` on the task
  and execution roles, `ecs:DescribeTasks`/`ListTasks`/`StopTask`, `logs:GetLogEvents`
  and `ssm:GetParameter` on the runtime config. None of that is managed here. A dev
  poweraccess role has all of it; prod is unchecked.
- A stopped Neptune cluster looks like a connect timeout, and AWS starts it again
  after 7 days. Preflight says so.

**Other**

- **Local runs write only locally** (`./output/`). `--remote` is the only way to
  change real state.
- **Commands.** Pipeline commands live under `dia pipeline`, the agent under `dia
  agent`. `extract-text` and `ledger` are still at the top level and move under
  `pipeline` when rewritten. `dia agent status` is effectively the agent's own
  preflight.
- **Stages:** text, chunk, propositions, topics, validate, embed, load. Purge and prune
  are separate, and prune is deferred. Stages that call Bedrock always use batch jobs,
  padded to Bedrock's 100-record minimum.
- **Reference code for validate:** the old repo `gds-idea-assurance-knowledge-graphs`
  (`src/topic_reconciliation.py`, `src/post_processing.py`). Its reconciliation works
  per file.
- `retrieval_modes.py` in the agent filters on `document_type`, but nothing in the
  pipeline writes it yet.

## 7. Verified and unverified

**Verified by real runs in dev**

- The image builds and pulls, tasks start, logs are written, and the private subnets
  have outbound access.
- The task role reads the runtime config, the ledger table and the buckets.
- A task assumes the cross-account role and lists the GATS documents location.
- A task reaches Neptune on 8182, and `GetEngineStatus` works.
- CI builds the x86_64 image and deploys the stack on a merge to `dev`.
- Every `dia pipeline tasks` command, and `--remote --no-wait`.

**Unverified**

- `source gats_business_cases` in preflight, after #78 (see section 1).
- The Neptune read, write and delete action names in `stacks/pipeline_task.py`
  (`ReadDataViaQuery`, `WriteDataViaQuery`, `DeleteDataViaQuery`). Only
  `GetEngineStatus` has run.
- Whether the account requires the `DenyUserPermissionsPolicy` boundary on new roles.
  It is harmless; removing it means deleting the `permissions_boundary()` calls.
- That role chaining caps the cross-account session at an hour (documented, not seen).
- Whether the cross-account role can read the prod `spend-controls-raw-data/` folder.
  The extended check that would show it was designed but never run.

## 8. Upstream issues raised

- co-cddo/gds-idea-cdk-constructs-new#62: the library imported `aws_cdk` at module
  level, which needs Node and put about 420MB in the image. The import is now lazy
  (#64 there, released as 1.1.1), which fixes the crash but not the size.
- co-cddo/gds-idea-ai-reviewer#39: the `cdk-review` and `python-cleanliness` skills have
  invalid YAML frontmatter and are silently skipped.
- co-cddo/gds-idea-ai-reviewer#40: narrow the reviewer's token and the MCP tools it
  gives the model.
- co-cddo/gds-idea-app-kit#63: the `ci_pr_cdk_app.yml` template drops `reopened`,
  re-runs CI on any label, and probably fails the version check for hatch-vcs
  projects.

## 9. Useful commands

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .

uv run dia pipeline preflight                 # local checks (needs AWS credentials)
uv run dia pipeline preflight --remote        # the same, as a task in the cloud
uv run dia pipeline tasks --mine              # your recent tasks
uv run python scripts/check_source_access.py  # what each session can read, per source
```

Live AWS tests, and the Neptune tunnel, are described in the README.
