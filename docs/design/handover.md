# Handover

This is the working handover for the DIA pipeline, written when David Gillespie
handed the work over to Aakash. It is for whoever picks the work up next, human or
agent. It goes stale quickly: **update it at the end of every PR**, and keep section
1 accurate above all.

The agreed design is in [`pipeline-spec.md`](pipeline-spec.md), and its section 7 is
the build plan. This file covers where things stand, what to do next, and the
facts that are not obvious from the code.

## 1. Where things stand

State when this was written, with `dev` at #87 (the writing step, 8c). Check `gh pr list` and
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
  knowledge bases for the sources in `deployed_knowledge_base_sources()`, which are the
  `SOURCES` whose `knowledge_base` block has `deployed=True`: today the two DBR ones.
  To deploy another, set `deployed=True` on its entry. One retained S3 Vectors bucket,
  and per KB a retained index, a role that reads only its own prefix, the KB and its
  data source. A dev KB that reads the GATS bucket (declared, not deployed) is
  cross-account, so the prod bucket's policy must allow the KB role first. Deploying
  creates empty KBs: upload the documents and sidecars, then start an ingestion job
  per data source. The `dia-kb-arns` secret is not written from CDK; its values are
  set by hand, so the KB IDs are stack outputs for now. Plan:
  `docs/knowledge-bases-plan.md`.
  **A source key is permanent.** It sets the KB's name, its index and data source
  names, and the construct IDs. Renaming one replaces the KB, role and data source
  (the KB ID changes, and every document is ingested again) and leaves the old index
  and its vectors behind. **Deleting the stack and deploying it again fails**, because
  the retained vector bucket and indexes still hold their fixed names: delete or
  import them first.

- **Shared source declarations (#78).** Every dataset is declared once in
  `src/dia/sources/definitions.py`, whichever pipeline uses it. Preflight and the
  task stack read them, and the four new knowledge base buckets exist in CDK.
  Preflight's source check is now called `source gats_business_cases` and reads the
  declarations. Run `uv run dia pipeline preflight` once to confirm it works against
  real AWS; nobody has yet.
- **The sidecar model (`dia.sources.sidecar`).** `Sidecar` holds the metadata fields
  (only `document_type` is required; `is_latest` is a boolean and everything else is
  text, except `date`). `date` is a common key every source may carry. It is a real
  date in Python and a `YYYYMMDD` number in the file, so Bedrock can filter ranges.
  The model is strict: it does not accept text dates. Each source's metadata step
  parses its own date format with `parse_date`, which turns `2025`, `202606` or
  `20260901` (or `2026-06-01`) into a date, using the first month and day when they
  are missing. The dashes are all or nothing: `2026-0601` is rejected. A source with
  `MMYYYY` dates, such as the DBR report filenames (`062026`), converts them to
  `YYYYMM` first. There is no `year`, `assurance_date` or `file_reference` key.
  **Every field except `document_type` can be missing.** A missing value is left out of the
  file, never written as `null`, so whatever reads a label (the text stage first) must treat each
  of them as possibly absent. `date` is missing for about 3% of the older export's documents,
  13% of the newer one's, and the basic labels; `alb` is missing for any submitter that is not
  an ALB. A filter on a field never matches a document that lacks it.
  `sidecar_key`, `is_sidecar_key`, `to_json` and `from_json` write and read Bedrock's
  simple `{"metadataAttributes": {...}}` format, and `to_json` raises `SidecarError`
  for a file over Bedrock's 10 KB limit. `check` compares a sidecar with the keys its
  source declares. Pure code, with tests; no AWS. Not yet used by anything, so it is
  not in `TASK_MODULES`: add it when a task command imports it. A test fails if a
  source declares a key that `Sidecar` lacks, or the reverse.
- **GATS sidecar mapping (`dia.sources.gats_sidecars`).** `documents_for_row` turns one
  export row into a `{file name: Sidecar}` dict, one entry per document the row lists
  (pass it the row's `row_sidecar` if you already have it, to avoid building it twice),
  for both export layouts. `choose_documents` takes and returns such a dict. It picks which to label: it
  filters by department, orders newest first by `Sidecar.date` (no date last), then
  takes the first `limit`, so `--limit` counts documents. A department matches on
  `department_name`, ignoring case, so it includes its ALBs. The submitter is matched
  ignoring case and extra spaces. A known ALB (in `PARENT_MAP`) gives its parent as the
  department and is the ALB. A known department is written in its canonical spelling,
  with no ALB. Any other submitter is kept as written, with no ALB. Names are compared
  ignoring case, extra spaces and a leading `The`, with `&` read as `and`. The date is the first of `CO_SpendStartDate`,
  `CO_DT_SpendStartDate` and `CO_CaseSubmitDate` that has text (only the last is in the
  newer export). It is read as ISO, `01 April 2025` or `30-Mar-26`. A date that is empty,
  unreadable or before 1990 (such as `0001-01-01` or `1970-01-01`) leaves `date` out and
  keeps the documents; an unreadable value does not fall back to the next column.
  `unreadable_date` returns the text of such a date, so the dry run can count it apart
  from an empty one. `is_test_row` finds rows from test submitters, and `_file_names`
  keeps a file name with a comma whole. It also
  reads the export from S3: `export_key` turns `latest`, a bare file name or a key into
  the key to read (`latest` is the newest CSV in `spend-controls-raw-data/gas/`, a bare
  name is looked for in `spend-controls-raw-data/`), and `read_export` returns its rows,
  reading `utf-8-sig`, and `list_bucket_keys` lists a prefix. `unrecognised_submitter`
  and `unmatched_departments` give the dry run two more of its counts. Its date and file-list parsing were checked against local
  copies of the 8 March 2026 older export and the 19 November 2026 newer export (counts
  only: 2.8% of the older export's documents and 13% of the newer one's have no date),
  but it has not been run against the bucket.
  **Accepted risk:** a document listed by two rows (a resubmitted case) keeps the
  sidecar of the row merged in last, and counts once towards `--limit`.
- **The metadata dry run (`dia pipeline metadata`, `dia.sources.sidecar_plan`).**
  `dia pipeline metadata [--export ...] [--limit N] [--departments "A,B"] [--report FILE]`
  reads the exports, lists the documents bucket and reads the labels already in it, and
  prints counts. It never writes to S3: a test checks that it makes only `GetObject` and
  `ListObjectsV2` calls (`--report` writes a CSV on this machine, only when asked). In dev
  it reads through the cross-account role (session name `dia-metadata`).
  With no `--export` it reads `OLD_EXPORT_KEY` (the last older-layout export, 8 March 2026,
  as those exports stopped) and `latest`, and warns if a newer file appears in the older
  folder. `--export` can be repeated and replaces the defaults; the later export wins for a
  shared file. The two exports do not overlap today.
  `sidecar_plan.plan` is pure (it is given a function that reads labels). Every document in
  the bucket gets one `Outcome`: **from_export** (an export lists the file, any type),
  **rebuilt_from_case** (not listed, but its old label's spend ID is a case in the exports),
  **old_label_kept** or **old_label_fixed** (not listed, case not in the exports: the old
  label as it is, or with `department` renamed and `file_reference` dropped),
  **old_label_unfixable** (left alone), **basic_label** (no export, no label, a PDF or
  `.docx`: only `document_type`), or **waiting_for_new_step** (no export, no label, any other
  type: nothing yet, see #85). A label is only replaced if what it would get differs
  (`new`, `replacements`, `unchanged`), so a run can be repeated. With `--limit` or
  `--departments` only the chosen listed files are in the run. Rows from test submitters are
  skipped and counted. A bucket key ending `.metadata.json` is a label and any other `.json`
  file is ignored. Run in prod on 8 March 2026 older export plus the 20 November newer one,
  the dry run gives: 8,257 from the export (2,496 new, 5,761 replacing an old label), 4,187
  rebuilt from their case, 818 kept, 12 fixed, 640 basic, 1,958 waiting, nothing unfixable.
  That is 3,136 new labels and 9,960 replaced.
- **Writing the labels (8c, `dia.sources.sidecar_writer`).** `dia pipeline metadata --write
  [--overwrite] [--yes]` writes what the dry run planned. **Run in prod on 26 November 2026:**
  a trial of 10 new labels (`--export latest --limit 10`), then the full run (`--write
  --overwrite`): 3,190 new and 9,960 replaced, no failures (54 more new than the 20 November
  dry run). The 9,960 old labels, as they were, are in `./output/metadata/20261126T130700Z/` on
  the machine that ran it. That is the **only copy**, with each label's `file_reference`, so
  keep it. It asks first (default no; `--yes` skips). A new label is
  written with `IfNoneMatch="*"`, so a label that appeared since the plan is skipped and never
  replaced. `--overwrite` also replaces labels that differ, after saving each old one, as it was,
  under `./output/metadata/<time>/<key>`; if a save fails nothing is written (`SidecarPlan.replaced_text`
  holds the old text for this). 16 writes at a time (the client's pool is sized to match). A label
  that fails, such as one over 10 KB, is counted and the run continues; the exit code is 1.
  `select(plan, overwrite=...)` is the one place that says which labels a write touches: the
  CLI's counts and prompt and `write_plan` both use it, and `WriteResult.backup_dir` says where
  old labels were saved, so the CLI reports what the writer did. A 409 from a racing conditional
  write counts as `skipped_exists`.
  `./output/metadata/<time>.csv` lists keys and `new`, `replaced`, `skipped_exists` or `failed`.
  `--write` in dev exits 1 before any S3 call, because the role is read-only; `--overwrite` or
  `--yes` without `--write` is a usage error. Spec 3.5 records this as the one exception to "local
  runs write only locally". The prod role could write to `files/`.

- **The pipeline ledger (`dia.pipeline_ledger`, step 9).** Records what each stage did to each
  version of each document, so a run over a whole department only does the new and changed
  ones. Table `dia-pipeline-ledger-{phase}` (CDK, `stacks/storage.py`; the old `dia-ledger-{phase}`
  stays until the old code goes): partition key `source#stage`, sort key `document_key#version`.
  Example: `gats_business_cases#text` / `files/HMRC case.pdf#2026-11-24T10:15:00Z`. The version is
  the document's S3 `LastModified` (`document_version`), so a re-uploaded file is done again and
  records of older versions stay. `DynamoLedger` and `LocalLedger` (JSON files) share one
  interface, `records(source, stage)` and `record(records)`, and one set of tests. A stage calls
  `pending(versions, records, retry_failed=...)` for what is left. **Rule: record a document as done
  only after its output is written.** If the run stops first there is no record and it is done
  again; a record written ahead of the work would make it skipped for good. A failed record keeps
  its reason and is skipped until the document changes or `retry_failed` is set.
  `open_ledger(source, stage, names=, remote=, ignore_ledger=)` gives a stage its ledger: the real
  table for a remote run; for a local run a `LocalLedger` in `./output/ledger/` holding a copy of the
  real records for that source and stage (replacing any earlier copy), or empty with `ignore_ledger`
  (refused for a remote run). A local run never writes to the real table. Read-only commands
  `dia pipeline ledger list --source S --stage T [--failed]` and `status --source S` show the real
  table. **Not built:** the `--ignore-ledger` and `--retry-failed` options themselves, because they only
  mean something to a stage; the text stage declares them and calls `open_ledger` and `pending`.
  `dia.pipeline_ledger` is not in `TASK_MODULES` yet: add it when a task command imports it.
  Preflight checks the new table. Built and tested with moto, **not
  run against the real table until this is deployed.**
- **Legacy ledger import (`scripts/import_legacy_ledger.py`, one-time, dev only).** The old code
  ingested documents into the dev graph and kept `file_reference_mapping_new_v2.json`, a map of
  `file_reference` to file name (6,072 entries; 5,888 are in the prod bucket, and the labels
  replaced in step 8 agree with it for all 5,888; 184 are not in the bucket and are skipped).
  The script records each found document as done for **every** stage, at its current
  `LastModified`, with `code_version` `legacy-import`, so the new pipeline keeps the old graph
  data and does not ingest those again. That assumes they have not changed since. About 41,000
  records. Dry run by default; `--write` asks first; records that already exist are left alone,
  so it can be run again. To run it, after this is merged and CI has deployed the table to dev:
  with dev credentials, `uv run dia pipeline preflight` (the ledger table should be ok), then
  `uv run python scripts/import_legacy_ledger.py <map file>`, check the counts, then add `--write`,
  then run the dry run again (it should find nothing to write). Delete the script afterwards.

**Agreed, not built**

- **Two pipes, kept separate.** *Graph*: our extraction into Neptune and OpenSearch.
  *Knowledge base* (KB): Bedrock reads the documents. They complement each other.
- **Metadata is its own step**, separate from both pipes. For every document in
  every source it writes a `<document>.metadata.json` sidecar next to the document,
  in Bedrock's format (`{"metadataAttributes": {...}}`), including in buckets we
  don't own, such as GATS. The typed model (`Sidecar`, built) holds the field names,
  which match the keys the KBs already use. The KB reads the sidecar as it is. The
  graph's text stage reads it and adds the fields to the extracted text, and **skips
  and logs a document that has no sidecar**.
- **Who writes sidecars where.** A bucket of ours: either phase writes its own. A
  bucket we only consume, such as GATS: only prod writes, because dev reads it
  through the read-only cross-account role. A dev run of the metadata step warns that
  it cannot write there. So the GATS sidecars need a prod run first.
- **The trial run.** Take the **latest 10 GATS business cases** from scratch through
  every stage into the dev graph, and ask the agent about them. Each stage is a new
  `dia pipeline <stage>` command that runs locally and with `--remote`. What
  "latest" means is not decided (see section 2).

**Not started:** every stage after the labels.

**Old code still in the repo.** The rest of `src/dia` is the first build: `extract-text`
and its runner, `sources/known.py`, `DataSource`, the `metadata` package, the old
ledger and its CLI, writers, filters, and the agent. Only the old text stage ever ran
(see `docs/extract-text.md`). It is disposable: each PR removes what it replaces.

## 2. What to do next

Follow section 7 of the spec. In short, the order is:

1. **Metadata model and sidecar format.** Done (`dia.sources.sidecar`).
2. **The GATS metadata step.** Done: the mapping, the dry run and the writing. The labels
   are in the prod bucket (see section 1).
3. **The minimal ledger.** Built (`dia.pipeline_ledger`), with `open_ledger` and the `dia pipeline ledger`
   commands. Run the legacy import once it is deployed.
4. **S3 reader and the text stage**, which delete `known.py`, `DataSource`,
   `extract-text` and the old metadata package.
5. **Chunk, propositions, topics, validate, embed, load**, then check the result with
   the agent.

Then harden the ledger and CLI, and scale up to all of GATS and the other sources.

**Decided for the GATS metadata step**

- **"Latest"** is newest by the sidecar's `date`. In the older export that is the spend
  start date (`CO_SpendStartDate`, then `CO_DT_SpendStartDate`, then `CO_CaseSubmitDate`);
  in the newer export it is the case submit date (`CO_CaseSubmitDate`). So `date` does
  not mean the same thing in the two, and many documents share a date (often 1 April),
  so `--limit N` is not strictly the N most recent: ties are broken by spend ID.
- **`--limit N` counts documents, not cases.** Documents are taken newest first until
  `N` is reached, so a case can be cut part-way (`choose_documents`). It can also be
  limited to some departments, which is applied before the limit.
- **Two export layouts.** The older export (`spend-controls-raw-data/`, about weekly;
  the newest in prod is `DataExport_08032026052712.csv`, 8 March 2026) lists a case's
  files in `CO_CS_Files` and names it in `CO_CS_CaseName`. The newer one
  (`spend-controls-raw-data/gas/`, daily, 35 columns) uses `CO_I_Documents` and
  `CO_I_Name`. The key's date is day-month-year, so keys do not sort by date. The first
  run uses the 8 March file; later runs use the newest in `gas/`.
  The mapping accepts both. The trial of 10 documents is taken from `gas/`.
- **Every document a case lists gets a sidecar,** whatever its type.
- **Overwriting:** off by default, so a repeat run does not replace an existing sidecar;
  an `--overwrite` option replaces it.
- **Writing:** the command is run locally with prod credentials, and writes into the
  GATS bucket. The data owners have agreed to our adding sidecar files. This is an
  exception to "local runs write only locally", recorded in spec 3.5.

**Still to settle**

- **Dates of the documents.** The formats are known (see above), but 2.8% of the older
  export's documents and 13% of the newer one's have no date. In the older export a
  `1970` placeholder was found, and is left out. The dry run reports documents with no
  date, and unreadable dates apart from empty ones: check both after each new export.
  `date` for the older export is the spend start date, not a submit date; whether that
  is what users want to filter on is worth confirming with them.
- **The file list.** `CO_I_Documents` and `CO_CS_Files` use only commas (no `;`, `|` or
  newlines) in the two exports checked. A name can contain a comma, so the mapping joins
  a piece with no file extension to the pieces after it ("Business Case, v2.pdf"). On the
  8 March older export this took the names not in the bucket from 163 to 11, and on the
  19 November newer export from 40 to 0. A name with no extension, or one whose first
  piece looks like an extension (`Version 2.1, final.pdf`), would still be split wrongly.
- **File names against bucket keys.** The names a case lists are assumed to match keys
  under `files/`. The dry run counts the ones that do not ("not in the bucket"), and
  they are skipped. The 11 left in the older export are not in the bucket at all.
- **Documents with no label.** The bucket has about 15,900 documents and 10,778 old labels
  (all `.metadata.json`). The two default exports do not overlap and list 8,257 of the
  documents. 148 exports exist (55 older, 93 newer), but reading all of them adds only 396
  more, so the two defaults are enough. 2,597 documents have no export row and no old
  label. The PDF and Word ones (639) get a label with only `document_type`; the rest
  (1,958, mostly PowerPoint and Excel) wait for a step that reads those types (#85). Where
  better metadata for these could come from is #84. The old code merged
  `department_files/historic_cases_metadata.csv`, which is only in the dev bucket and was
  not readable from prod.
- **Overwriting the old labels loses information.** The old labels use `department`
  (ours is `department_name`), have no `date`, and many (23 of 40 sampled) have a
  `file_reference`, which `Sidecar` does not have (the knowledge-bases plan already drops
  it). The bucket has never had versioning enabled, so an overwrite cannot be undone.
  Decided, and built in 8c: it saves each label it replaces on the machine running it, before replacing it.
  Decided: every old label is replaced with the new format, from the export where there is
  one, from the case by spend ID, or fixed from its own content. `spend_id` stays a label key.
- **Bodies not in `PARENT_MAP`.** These are unrecognised in the two exports, and are
  written as given: the Charity Commission, the Prime Minister's Office (10 Downing
  Street), UK Shared Business Services, the National Infrastructure and Service
  Transformation Authority and the London Procurement Partnership. Bodies added with
  less certainty, which are worth checking: the Government Legal Department (Attorney
  General's Office), UK Export Finance (Department of Business and Trade), the National
  Cyber Security Centre (FCDO) and the National Protective Security Agency (Home Office).
- **Test data.** Rows whose submitter ends in `test` or `testing` (`GATS_test`,
  `00_Test`) are ignored and counted: 73 rows in the older export and 24 in the newer.
- **The export's location in prod.** Verified: the dry run reads the export and lists the
  bucket with prod credentials (the 8 March older export and the newest in `gas/`). Not
  verified: reading both through the cross-account role from dev. If that is denied, the
  command says it could not read from the bucket.

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
NAO, the DIA documents) now point at new, **empty** buckets of ours. Their KBs aren't
deployed, so nothing breaks, but the documents must be copied in before they are
(#64).

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
  sidecars are written by a local run with prod credentials, so this is not needed for
  them, but it is needed before CI can deploy to prod.
- **Confirm the prod location of the GATS metadata.** The prod GATS documents bucket
  is confirmed. Only the dev copy of the export has been read.
- **The agent must query current versions only.** Graph loads are versioned, and the
  agent doesn't yet filter to the current one. Coordinate with whoever owns the agent.
  Also move the agent onto `RuntimeConfig` in place of its hand-filled Secrets Manager
  endpoints, which can drift (raised on #65).
- **Data owners have agreed** that we add sidecar files to the GATS bucket (done).
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
- **The `gds-idea` package index is `explicit = true`.** Only the packages named in
  `[tool.uv.sources]` come from it. Without this, uv asked it first for everything,
  including the build tools (`hatchling`, `hatch-vcs`) that `uv sync` fetches fresh
  each time to build `dia` itself, because they are not in `uv.lock`. The index is
  GitHub Pages, and its occasional 503 failed CI and the Dependabot runs. A package
  that should come from the index needs a `[tool.uv.sources]` entry. `package =
  false` (used by the app repos) is not an option here, because `dia` has to be
  installed to provide the `dia` command.

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
  change real state, except `dia pipeline metadata --write`, which a local run with prod
  credentials uses to add sidecars to the GATS bucket (spec 3.5).
- **Commands.** Pipeline commands live under `dia pipeline`, the agent under `dia
  agent`. `extract-text` and the old `ledger` commands (`list`, `clear`, `clone`; `extract-text`
  tells you to use `clone`) are still at the top level and go with the text stage. The new ledger's commands
  are `dia pipeline ledger`. `dia agent status` is effectively the agent's own
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
