# DIA - Department Intelligence Agent

![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/co-cddo/gds-idea-dia/badges/coverage.json)

Knowledge graph extraction pipeline for UK government documents. Extracts structured knowledge graphs from government document types (business cases, spending review bids, contracts) and loads them into Amazon Neptune and OpenSearch.

## Setup

```bash
uv sync --all-extras
uv run dia --version
```

## Usage

- [`dia extract-text`](docs/extract-text.md) — Stage 1: extract text from documents in a source
- `dia pipeline preflight` — check that this process can do what the pipeline needs (see below)
- `dia pipeline metadata` — label the GATS documents from the exports: a dry run, or with `--write` the real thing (see below)
- `dia pipeline ledger list` and `status` — see what each stage has done to each document (see below)

### Metadata labels

`dia pipeline metadata` works out what label each document in the GATS (Get Approval to
Spend, run by the Government Assurance Service) bucket should have, and prints counts. By
default it is a dry run and never writes to S3. Run it with valid AWS credentials (in dev it
reads through the cross-account role):

```bash
uv run dia pipeline metadata                                  # every document, from the two default exports
uv run dia pipeline metadata --export latest --limit 10       # a trial: the newest 10 listed documents
uv run dia pipeline metadata --export <file>.csv --export latest   # choose the exports (replaces the defaults)
uv run dia pipeline metadata --report output/metadata/dry-run.csv  # also list every document, on this machine
```

With no `--export` it reads the last export of the older layout (`DataExport_08032026052712.csv`,
since those stopped) and the newest in `gas/`. If another file appears in the older folder
it warns. A bare file name is looked for in `spend-controls-raw-data/`. When two exports list
the same file, the later one wins.

Every document in the bucket gets one of these:

| It gets | When |
|---|---|
| A label from the export | An export lists the file, whatever its type |
| A label rebuilt from its case | No export lists it, but its old label names a case (spend ID) that an export has |
| Its old label, kept | Its case is not in the exports, and the old label is already in the right format |
| Its old label, fixed | The same, but in the old script's format (`department`, `file_reference`) |
| A label with only `document_type` | No export, no old label, and it is a PDF or Word file |
| Nothing yet | No export, no old label, and any other type (waits for a step that reads them) |

An existing label is only replaced if what it would get is different, so a second run changes
nothing. `--limit` counts documents, not cases, and `--departments` is applied before it. With
either, only the chosen listed documents are in the run and the rest are left alone.

"Newest" is by the label's `date`: the spend start date in the older export
(`CO_SpendStartDate`, then `CO_DT_SpendStartDate`, then `CO_CaseSubmitDate`) and the case submit date in
the newer one. Rows from test submitters (a name ending in `test` or `testing`) are ignored and
counted. A file name with a comma in it ("Business Case, v2.pdf") is kept whole. The screen
names only unrecognised submitters, departments that matched nothing and unreadable dates;
`--report` has the document names. Other `.json` files in the bucket are ignored.

#### Writing the labels

`--write` adds the labels to the bucket. It is the one place a local run writes to real
state, and it writes only `.metadata.json` files next to the documents. It works only in
production, run locally with production credentials: in dev it stops, because the role is
read-only.

```bash
uv run dia pipeline metadata --export latest --limit 10 --write            # a trial: 10 new labels
uv run dia pipeline metadata --write --overwrite                           # also replace labels that differ
uv run dia pipeline metadata --write --yes                                 # skip the confirmation
```

- It prints the counts, then asks before writing (the default is no). `--yes` skips this.
- Without `--overwrite` it writes only labels that do not exist yet (a label that appears
  while it runs is never replaced). Labels that differ are counted and left alone.
- With `--overwrite` each label it replaces is first saved, as it was, under
  `./output/metadata/<time>/` at the same key. The bucket has no versioning, so this is the
  only copy. If a save fails nothing is written. Those files hold real case data and
  `output/` is git-ignored.
- It writes 16 labels at a time. A label that fails (for example over Bedrock's 10 KB limit)
  is counted and the rest go on; the exit code is 1 if any failed.
- `./output/metadata/<time>.csv` lists the keys written, skipped and failed, with no label content.

### Preflight

`dia pipeline preflight` is read-only. It reports one line for each check and
exits with an error if any check fails. Run it with valid AWS credentials:

```bash
export AWS_PROFILE=<your-profile>
uv run dia pipeline preflight
```

It checks your identity (account and phase), the runtime config, the ledger
table, our buckets, and read access to the source data (in dev, through the
cross-account role). Inside an ECS task it also checks Neptune, which only tasks
can reach.

The runtime config is read from the parameter named in the `DIA_RUNTIME_CONFIG`
environment variable. A task definition sets it. When it isn't set, as on a
laptop, the name is built from the environment: `dia-runtime-config-<phase>`.

The parameter is written by the pipeline task stack (`stacks/pipeline_task.py`),
so the "runtime config" check fails in an account until that stack has been
deployed there. Your own role also needs `ssm:GetParameter` on it.

### The pipeline ledger

The ledger records what each stage did to each version of each document, so a run only
does what is new or changed. These commands read it (they never change it) with your
credentials, from the table for your account's phase:

```bash
uv run dia pipeline ledger status --source gats_business_cases                 # done and failed per stage
uv run dia pipeline ledger list --source gats_business_cases --stage text      # every record of a stage
uv run dia pipeline ledger list --source gats_business_cases --stage text --failed   # with the reasons
```

Stages open their ledger with `dia.pipeline_ledger.open_ledger`. A `--remote` run uses the real
table. A local run works on a copy in `./output/ledger/`, so it never changes the real one, or
on an empty one with `--ignore-ledger`. (The older `dia ledger` commands belong to
`extract-text` and go with it.)

### Running in the cloud

Add `--remote` to run the command as an ECS task, where it can reach Neptune:

```bash
uv run dia pipeline preflight --remote             # start a task and follow its logs
uv run dia pipeline preflight --remote --no-wait   # start it and return
```

It prints the task ID, follows the logs, and exits with the task's exit code.
Ctrl-C stops following but leaves the task running. To look at tasks:

```bash
uv run dia pipeline tasks                          # running and recently stopped tasks
uv run dia pipeline tasks --mine                   # only the ones you started
uv run dia pipeline tasks logs <task-id> --follow  # read (and follow) a task's logs
uv run dia pipeline tasks stop <task-id>           # stop a running task
```

`--remote` needs the pipeline task stack deployed in the account (it reads the
runtime config that stack writes: see Preflight above).

Only this pipeline's tasks are listed, because the ECS cluster is shared with other
applications. Each task is started as `dia-cli/<your name>`, taken from your AWS role
name. ECS forgets stopped tasks after about an hour. Your role needs permission to run
tasks, pass the task's roles, and read logs; those permissions are not managed here.
Nothing limits how long a task runs (see #67), so stop one that hangs.

## Task image

Pipeline commands run in the cloud as ECS tasks, from the image defined in
[`task/Dockerfile`](task/Dockerfile). It installs only the `pipeline` extra: no
agent dependencies, dev dependencies or Zscaler fix. A task supplies the command,
because the entrypoint is `dia`.

To build and try it locally (from the repository root):

```bash
docker build -f task/Dockerfile -t dia-task .
docker run --rm dia-task --version
```

CDK builds and deploys this image as part of the pipeline task stack
(`stacks/pipeline_task.py`) when changes merge to `dev`. The stack also defines
the task's size (2 vCPU, 8GB), its roles, its log group and the runtime config
parameter. **Prod cannot deploy yet:** the repository is not in
`repositories_access_prod.tf` in `gds-idea-cdk-access`, so a merge to `prod`
would fail at the AWS login step (see `docs/design/handover.md`).

The version normally comes from git tags, which are not in the image, so pass
it with `--build-arg DIA_VERSION=<version>`. Without it the image reports
`0.0.0.dev0`. On a Mac, this builds for the Mac's own architecture. The deployed
image is x86_64, and `--platform linux/amd64` builds that (slowly, under
emulation).

The image has no Node, no CDK and no dev tools, so a module that needs one of them
works on a laptop and fails only when a task starts. The `CI Task Image Smoke Test`
workflow builds the image on pull requests and imports every module a task runs
(`TASK_MODULES` in [`task/smoke_test.py`](task/smoke_test.py)). Add a module to that
list when a task command starts to use it. To run the same check locally, after
building the image as above:

```bash
docker run --rm -i --entrypoint python dia-task - < task/smoke_test.py
```

## Running tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Live AWS integration tests

`tests/test_lexical_graph_integration.py` exercises real Neptune + OpenSearch
Serverless infrastructure and is skipped by default (no AWS access required
for a normal `uv run pytest`). To run it for real:

```bash
# If on a Zscaler-managed corporate device, install the TLS fix first —
# needed for the OpenSearch Serverless (AOSS) connection, which goes over
# the public internet (Neptune's connection tunnels via SSH and is unaffected):
uv sync --group zscaler

./scripts/neptune-tunnel.sh dev   # in a separate terminal

export RUN_LIVE_AWS_TESTS=1
export AWS_PROFILE=<your-profile>
uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v
```

Only those two exports are required — Neptune/AOSS endpoints are looked up
automatically via CloudFormation (override with `export NEPTUNE_ENDPOINT=...`
/ `export AOSS_ENDPOINT=...` if needed). `AWS_REGION` and model choices can
be set the same way, or persisted locally in a git-ignored `.env` file — see
`src/dia/clients/graph_rag_config.py`.

### Connecting to a different Neptune cluster (temporary)

By default the tunnel and the agent connect to the DIA Neptune cluster for
your phase (`dev` or `prod`). To point them at another Neptune cluster in the
same account and VPC, set `NEPTUNE_ENDPOINT` to that cluster's hostname.

**One-off setup:** let the bastion reach the other cluster. Add an inbound rule
to the other cluster's security group allowing TCP `8182` from the bastion's
security group. You can do this in the console, or:

```bash
BASTION_ID=$(aws cloudformation describe-stacks --stack-name dia-bastion-dev \
  --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" --output text)
BASTION_SG=$(aws ec2 describe-instances --instance-ids "$BASTION_ID" \
  --query "Reservations[0].Instances[0].SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id <other-cluster-sg-id> \
  --protocol tcp --port 8182 --source-group "$BASTION_SG"
```

Your AWS profile also needs Neptune data access (`neptune-db:*`) on that cluster.

**Each time you use it:**

1. Close any tunnel that's already running (Ctrl+C in its terminal). If one is
   still open, the agent reuses it, and it will still point at the old cluster.
2. Set the endpoint (hostname only, no `https://` and no port):
   ```bash
   export NEPTUNE_ENDPOINT=<other-cluster-hostname>
   ```
3. Use things as normal. Everything below picks the endpoint up:
   ```bash
   uv run dia agent ask --query "..."     # opens its own tunnel to the other cluster
   ```
   ```bash
   ./scripts/neptune-tunnel.sh dev        # manual tunnel, e.g. for notebooks or `dia agent status`
   ```
   The script prints `(NEPTUNE_ENDPOINT override)` next to the endpoint so you
   can confirm which cluster you're on. In a notebook, pass the same hostname
   to `LocalNeptuneClient(endpoint=...)`.

**Going back to the default cluster:** close the tunnel, run
`unset NEPTUNE_ENDPOINT` (and remove it from `.env` if you put it there), then
remove the security group rule you added.

## CDK

Infrastructure is deployed automatically via CI/CD:
- Merge to `dev` → deploys to development account
- Merge to `prod` → deploys to production account

For local CDK operations:

```bash
cdk diff
cdk synth
```
