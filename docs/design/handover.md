# Handover

Working notes for whoever picks this work up next, human or agent. This file
goes stale quickly: **update it at the end of every PR**, and keep the
"Current position" section accurate above all.

The agreed design is in [`pipeline-spec.md`](pipeline-spec.md). This file
covers where we are, how we work, and facts that are not obvious from the code.

## Current position

State when this was written (check `gh pr list` and `git log origin/dev` before
relying on it):

- Merged: the spec (#61), the spec update, handover and naming module (#62), the
  Docker image with the extras split (#63), `dia pipeline preflight` and the
  runtime config model (#65), the pipeline task stack (#66), and the fix that
  lets the task image import `dia` without Node, plus an image smoke test in CI
  (#69).
- The task stack is deployed to dev. Running `dia pipeline preflight` as a task
  there (started by hand) showed that the image, outbound access, the runtime
  config read, the ledger table, the buckets and the cross-account role all work
  from inside the VPC. The Neptune check failed because the dev Neptune cluster
  was **stopped**, not because of the network. See "Unverified assumptions" for
  what that run did and did not settle.
- PR 5 (#70): `dia pipeline preflight --remote` and `dia pipeline tasks`
  (`src/dia/remote.py`). See "Remote running" below. Run for real in dev, where
  `dia pipeline preflight --remote` passes all 6 checks including Neptune.
- PR 5a (#71): preflight says why the Neptune connect failed (timeout, refused,
  name not resolved). A timeout message mentions that a stopped cluster looks
  like this.
- **Next:** Milestone B (sources), starting with PR 6 (source protocols and the
  common metadata model). It needs a design conversation first.
- Only the foundations are built so far (naming, the extras split, the task
  image, preflight and the task stack). The rest of `src/dia` is work in
  progress that nobody uses, and may be deleted as the PR that replaces each part
  lands.

## How we work

**With the user (David, a repo owner and org admin)**

- Short messages, one decision at a time. Start from requirements in plain
  language and keep implementation detail until it is needed. Use the question
  tool for choices, with a recommended option first.
- Plan first, then build. For code, **stage the change and open VS Code
  (`code -r . <files>`) so he can review before you commit.** Small docs-only
  commits can go straight in.
- Do not commit, push or open PRs unless asked. When asked for a PR, open it as a
  draft, tag `@aakash-cddo`, and say what was and was not tested.
- He can do the admin steps you cannot (org secrets, GitHub App installs, prod
  AWS commands). Give him the exact commands and say what the output will tell
  you.
- Say what is unverified rather than guessing. Correct yourself when you find you
  were wrong.

**In the repo**

- **Small, reviewable PRs.** One thing per PR, with tests. Aakash reviews each.
- **Each PR removes the old code it replaces,** rather than one large deletion
  at the end.
- **Scope is GATS business cases first.** Other sources come after.
- **AI review:** add the `ai-review` label to a PR to get an advisory review
  from `gds-idea-ai-reviewer[bot]` (non-blocking; no label means no run and no
  cost). It does not re-run on a push; remove and re-add the label. Its job
  shows green even when it was skipped (for example when the App is not
  installed on the repo), so read the job log. It reviews the commit that was
  current when the label was added. Reply to its findings on the PR by item
  number: what was fixed, and what was left and why. It needs the `ai-review`
  job in `.github/workflows/ci_pr_cdk_app.yml`, the org secrets
  `GDS_IDEA_AI_REVIEWER_APP_ID` (shared with this repo, because it is public)
  and `GDS_IDEA_AI_REVIEWER_APP_PRIVATE_KEY`, and the `gds-idea-ai-reviewer`
  GitHub App installed on the repo.
- **`ci_pr_cdk_app.yml` is managed by `idea-app` but edited by hand,** and
  should stay that way. The template sets `run-version-check: true`, which fails
  here because the version comes from git tags (hatch-vcs) and there is no
  `version =` line in `pyproject.toml`. We also differ from the template in
  other ways: the trigger includes `reopened`, and the CI jobs skip on any
  `labeled` event (the template skips only for the `ai-review` label, so adding
  any other label, such as a release bump label, re-runs all of CI). The trigger
  also has no `branches:` filter, so a PR stacked on another branch still gets
  build, lint, tests and the AI review. The CDK diff is skipped for those PRs,
  because the catalogue's `ci_cdk_diff.yml` only supports `dev` and `prod` as
  targets and fails on anything else. If you run `idea-app update`, do not use
  `--force` on that file.

**Tooling constraints (permission rules in `~/.config/opencode/opencode.json`)**

- `rm -rf` is denied (even on temp files: use `rm` on single files and fresh
  directory names). `gh pr create` is only allowed as `--draft`. `git push`,
  `gh pr *` and `cdk deploy` ask for approval. `cdk destroy` and
  `gh pr merge` are denied.
- Plan mode can be switched on again at any time. In it, read and plan only.
- The skills in `~/.local/share/idea-oc/skills` are managed by `idea-oc`. I fixed
  the invalid YAML in `cdk-review` and `python-cleanliness` locally (issue
  co-cddo/gds-idea-ai-reviewer#39); a sync may overwrite that.

**How to prove a CDK change renames nothing**

Build every stack for dev and prod with a fake VPC (`ec2.Vpc.from_vpc_attributes`,
as `tests/test_pipeline_task_stack.py` does), dump `Template.from_stack(...)
.to_json()` before and after the change, and compare the files byte for byte.
Stacks that should be unchanged must be identical. The same script, wired the way
`app.py` wires the stacks and ending in `app.synth()`, also catches dependency
cycles. (The throwaway scripts were in a temp directory and are gone.)

## Key facts

- Pipeline tasks run on the **shared GDS IDEA ECS cluster**, using the
  `ecs_arn` from `DeploymentConfig` (SSM `/gds-idea-ecs`). Step Functions is
  deferred.
- **Local runs write only locally** (`./output/`). `--remote` is the only way to
  change real state.
- **Source locations:** each source has one real location. Prod reads it
  directly. Dev reads it through the cross-account role
  `assume_role_for_development_account` (`cross_account_role_arn` in
  `gds_idea_cdk_constructs`), unless the source names a dev override bucket.
- **Phase** comes from the AWS account (`DeploymentEnvironment`). Dev is
  `992382722318`, prod is `588077357019`.
- **Names:** every deployed name is built by `dia.naming.Names`, created from a
  `DeploymentEnvironment` (`Names(env)`). `names("ledger")` gives
  `dia-ledger-dev`, and `names(Bucket.TEXT_EXTRACTED)` gives
  `gds-idea-dia-text-extracted-dev`. In CDK use `config.names`. In the CLI use
  `dia.cli_helpers.current_names()`, which looks up the account.
- **Dependencies are split into extras:** the core is only what the CLI and
  naming need. `pipeline` is the document pipeline, `agent` is the agent and its
  report output, and `cdk` is for CDK. CI uses `uv sync --all-extras`.
- **Task image:** `task/Dockerfile` installs only the `pipeline` extra and runs
  `dia` as its entrypoint (see the README for how to build it). It is about
  1.44GB, and roughly 420MB of that is `aws-cdk-lib`, pulled in because
  `gds-idea-cdk-constructs` imports it at module level. The upstream issue is
  co-cddo/gds-idea-cdk-constructs-new#62. The image's build context is listed in
  the root `.dockerignore`, which both `docker build` and CDK read (a test checks
  what the stack actually stages).
- **Pipeline task stack:** one Fargate task definition, 2 vCPU and 8GB (to tune
  once real stages show what they need; it can also be overridden per run), with
  the image built for x86_64 and `dia` as the entrypoint. The task role is
  `dia-pipeline-task-{phase}` and carries the account's
  `DenyUserPermissionsPolicy` boundary (it allows everything except creating
  IAM users and access keys, so it removes nothing). It can use the ledger, our
  buckets, Neptune (read, write and delete via query, and engine status) and the
  runtime config parameter. It does **not** have Bedrock or OpenSearch access
  yet: later stages add what they need (the OpenSearch access policy names the
  account root as principal, so the load stage will need to add an `aoss`
  permission to the task role). The tasks' security group is in
  `NetworkingStack`, and `NeptuneStack` allows it in on 8182. Logs go to
  `/dia-task-{phase}` for 90 days (kept in prod, deleted with the stack in dev).
  The stack takes the shared `DeploymentConfig` (cluster, VPC id and the
  cross-account role) and looks the VPC up itself unless a test gives one. ARNs
  are written out literally with the `aws` partition, like the rest of the repo.
- **Cross-account role** `assume_role_for_development_account` (production
  account): it trusts the whole dev account with no conditions, and has
  `ReadOnlyAccess` plus Lake Formation, Bedrock knowledge base, Athena and S3
  Tables policies. So the dev task role only needs `sts:AssumeRole` on it, which
  the stack grants, and nothing needs adding to the role's trust policy.
  `ReadOnlyAccess` means an assumed session can read all of production, not just
  GATS. That is the existing pattern, but PR 7 should narrow it (see the build
  plan). A task's credentials are role credentials, so assuming the role from a
  task is role chaining and its sessions last at most an hour; PR 7 needs
  refreshable credentials. Preflight only needs a moment, so it is not affected.
- **Commands:** pipeline commands live under `dia pipeline` and the agent under
  `dia agent`. `extract-text` and `ledger` are still at the top level and move
  under `pipeline` when they are rewritten (PRs 11 to 14). `dia agent status`
  is effectively the agent's own preflight, and could be renamed to
  `dia agent preflight` for symmetry (a job for the agent's owner).
- **Runtime config:** CDK writes the Neptune endpoint and port, the OpenSearch
  endpoint, cluster, task definition, subnets, security group, log group and (in
  dev) the cross-account role as one JSON parameter,
  `dia-runtime-config-{phase}`. It is read through
  `dia.runtime_config.RuntimeConfig.load`, which fails fast. The task definition
  sets `DIA_RUNTIME_CONFIG` to the parameter name, and locally the name is built
  from `Names`. To add a value, add the field to `RuntimeConfig` and to the
  stack. Unknown fields are rejected, so the two cannot drift apart. The agent
  still reads its endpoints from Secrets Manager, which can drift from the real
  resources (the secrets are filled by hand); moving the agent onto the runtime
  config is planned for later and is a job for the agent's owner. The OpenSearch
  endpoint has any leading `https://` removed when it is loaded, because the
  collection's endpoint value has not been checked on a deployed collection and
  may include the scheme: check the value in the parameter after the first
  deploy.
- **Preflight:** `dia pipeline preflight` is read-only. It checks Neptune only
  inside an ECS task (it detects one through `ECS_CONTAINER_METADATA_URI_V4`),
  because only tasks reach the VPC. Its source check is limited to GATS and
  builds the cross-account client itself, using the role from the runtime
  config (so in dev that check is skipped if the config can't be read). PR 7
  should take that over, and PR 9 should make it read the new source
  definitions.
- **Stages:** text, chunk, propositions, topics, validate, embed, load. Purge
  and prune are separate steps, and prune is deferred.
- **Graph updates are versioned.** The agent does not yet query "current
  versions only" and must be changed (coordinate with whoever owns the agent).
- **Unmerged chunking work** is on the `graph-chunking` branch (`ChunkingRunner`,
  `ChunkStore`, ADR 0001 and the Stage 2b plan in `docs/plans/`). It is about
  3,500 lines, so it needs splitting into several PRs. The old
  `graph-extraction-runner` branch is abandoned.
- **Reference code for validate:** the old repo
  `gds-idea-assurance-knowledge-graphs` (`src/topic_reconciliation.py`,
  `src/post_processing.py`). Its reconciliation works per file.
- `retrieval_modes.py` in the agent filters on `document_type`, but nothing in
  the pipeline writes it yet. The canonical SR bids value is `sr_bids`.
- CI deploys on merge: `dev` branch to the dev account, `prod` branch to prod
  (prod cannot deploy yet: see the open actions). The CI workflows are managed by
  `idea-app`; the only one edited by hand is `ci_pr_cdk_app.yml`, for the reasons
  above.

## Remote running (PR 5)

`dia pipeline preflight --remote` launches the command as a task, prints the task
ID, follows the logs and exits with the container's exit code. `--no-wait` returns
after launching. Ctrl-C stops following but leaves the task running. It needs no
confirmation, because preflight only reads (spec section 3.3: confirmation is for
commands that change state).

- `dia pipeline tasks [--mine]` lists running and recently stopped tasks;
  `dia pipeline tasks logs <id> [--follow]` and `dia pipeline tasks stop <id>` do
  what they say. `stop` exists because nothing else stops a hung task (#67).
- All the AWS calls are in `src/dia/remote.py`; `cli.py` only wires them up. The
  later stage commands should reuse `_run_remote` in `cli.py` (launch, follow,
  exit code) and add their own confirmation and `--limit` rules.
- Tasks are launched with `run_task` on Fargate, with the subnets and security
  group from the runtime config and `assignPublicIp=DISABLED` (checked: the
  private subnets have outbound access). The command override goes on the
  container named `Pipeline`, whose entrypoint is `dia`.
- **`startedBy`** is `dia-cli/<name>`, so tasks on the shared cluster can be told
  apart. The name is the caller's role name up to its first hyphen
  (`david.gillespie-poweraccess` gives `david-gillespie`), or the whole role name
  if that part has no dot. ECS allows letters, numbers, `-`, `/` and `_`, up to
  128 characters. It has no timestamp: ECS records the time, and a per-run value
  would stop `--mine` working, because `list_tasks` can only filter by exact value.
- The cluster is shared with the web apps, so tasks are always listed by the
  task definition family `dia-pipeline-task-{phase}`. ECS forgets stopped tasks
  after about an hour; older runs are only in CloudWatch.
- Log streams are `pipeline/Pipeline/<task-id>` in `/dia-task-{phase}` (checked).
- **Who may launch:** the developer's role needs `ecs:RunTask`, `iam:PassRole` on
  `dia-pipeline-task-{phase}` and `dia-pipeline-task-execution-{phase}`,
  `ecs:DescribeTasks`/`ListTasks`/`StopTask`, `logs:GetLogEvents` and
  `ssm:GetParameter` on the runtime config. None of that is managed in this repo.
  A dev poweraccess role could already do all of it. Prod is not checked.
- **The CDK diff comment on a PR warns `TaskDefinition ... WILL_REPLACE`** whenever
  the PR touches `src/`, `task/` or `pyproject.toml`: the image hash is part of the
  task definition, so each change registers a new revision. That is expected. Old
  revisions stay in ECS and nothing is deleted.
- Not built yet: per-run CPU and memory (#68) and a maximum run time (#67). Both
  would be extra `run_task` arguments or a timeout in the entrypoint; `launch`
  takes only a command today.
- Not built yet: a post-deploy smoke test that runs `dia pipeline preflight
  --remote` in dev and fails on a non-zero exit. The command now supports it; the
  open question is that the dev deploy role would need `ecs:RunTask` and
  `iam:PassRole`, and a separate `workflow_run` workflow would be needed because
  `ci_cd_cdk_app.yml` belongs to `idea-app`.

## Task image

- The image has no Node, no CDK and only the `pipeline` extra. The first task
  crashed on `from gds_idea_cdk_constructs import DeploymentEnvironment`, because
  the library imported `aws_cdk` (which starts Node through jsii) at the top of
  the package. Fixed in the library (1.1.1) and guarded here.
- `task/smoke_test.py` imports every module in `TASK_MODULES` inside the built
  image, and `.github/workflows/ci_task_image_smoke_test.yml` runs it on PRs that
  touch the image. `tests/test_runtime_imports.py` does the same without Docker,
  from the same list. **Add a module to `TASK_MODULES` when a task command starts
  to use it.** The workflow is our own file, not managed by `idea-app`.
- The image is about 344MB compressed and still contains `aws-cdk-lib` (about
  220MB), because the library depends on it. It is never loaded now. Making the
  CDK an optional extra in the library would remove it, but is a breaking change
  for every app that builds stacks.

## Unverified assumptions

Settled by the first real task runs in dev:
- The OpenSearch collection endpoint does include `https://` (and uses the
  `<id>.aoss.eu-west-2.on.aws` form). The model strips the scheme, so the scheme
  stripping is needed. Nothing checks the domain.
- The private subnets have outbound access (image pull, logs, SSM, STS, S3).
- The task role can read the runtime config, the ledger table and the buckets.
- The cross-account role can be assumed from a task, and lists the GATS business
  cases location. The bucket is in the production account.
- CI builds the x86_64 image and deploys the stack on a merge to `dev`.
- A task reaches Neptune on 8182, and IAM auth with `GetEngineStatus` works
  (`dia pipeline preflight --remote` passes all 6 checks in dev). The first
  attempt failed only because the dev cluster was stopped. A stopped cluster looks
  like a connect timeout, and AWS starts it again after 7 days.

Still unverified:
- The Neptune read, write and delete action names in `stacks/pipeline_task.py`
  (`ReadDataViaQuery`, `WriteDataViaQuery`, `DeleteDataViaQuery`). Only
  `GetEngineStatus` has been exercised.
- Whether the account requires the `DenyUserPermissionsPolicy` boundary on new
  roles. It is harmless (`Allow *` with a deny on IAM user and access key
  actions), and removing it means deleting the `permissions_boundary()` calls.
- That role chaining caps the cross-account session at an hour. Preflight only
  needs a moment, so this has not been exercised; PR 7 needs refreshable
  credentials.
- Whether the cross-account role can read the SR25 locations and the GATS
  metadata (only the business cases location has been listed).

## Upstream issues raised

- co-cddo/gds-idea-cdk-constructs-new#62: `DeploymentEnvironment` imports
  `aws_cdk` at module level, which puts about 420MB of `aws-cdk-lib` in the task
  image. The import is now lazy (constructs-new#64, released as 1.1.1), which fixes
  the crash without Node but not the size.
- co-cddo/gds-idea-ai-reviewer#39: the `cdk-review` and `python-cleanliness`
  skills have invalid YAML frontmatter and are silently skipped.
- co-cddo/gds-idea-ai-reviewer#40: narrow the reviewer's token and the MCP tools
  it gives the model.
- co-cddo/gds-idea-app-kit#63: the `ci_pr_cdk_app.yml` template drops
  `reopened`, re-runs CI on any label, and probably fails the version check for
  hatch-vcs projects.

## Open actions

- **`gds-idea-dia` cannot deploy to prod yet.** It is in
  `gds-idea-cdk-access/repositories_access_dev.tf` but not in
  `repositories_access_prod.tf`, which controls who can assume `cdk-prod-deploy`.
  Merging to the `prod` branch would fail at the AWS login step. The fix is a
  one-line PR to that repo.
- Confirm where the GATS bucket lives. If it is in the production account, a
  prod task reads it with its own role; otherwise its owner has to allow our prod
  task role in the bucket policy. Running `dia pipeline preflight` in dev shows
  whether dev can read GATS through the cross-account role.
- Confirm the cross-account role can read the SR25 bucket and the GATS metadata
  bucket (the task role only reads the GATS documents bucket for now).
- Confirm the prod locations for GATS metadata and SR25 documents. The current
  names in `sources/known.py` and `metadata/registry.py` end in `-dev`.
- Look at real GATS documents before PR 8 (the GATS metadata strategy). There
  are reportedly business cases with more than one source schema.
- Agree the agent change (current versions only) with the agent owner.
- Run `idea-app update --dry-run` (the project was adopted at 0.5.4, and
  0.6.0 is installed) and decide whether to update.
- Known deviations from the CDK review standards, left alone because renaming
  would make CloudFormation replace resources: generic stack names such as
  `StorageStack`.
- Still outside `dia.naming`: the agent's secret names (hardcoded to `-dev` in
  `agent/config.py`), the stack names in `scripts/neptune-tunnel.sh`, and the
  `phase` default in `clients/graph_rag_config.py`.
- Open questions on testing and on permissions and ownership (spec section 6).
- Move the agent onto `RuntimeConfig` instead of the hand-filled Secrets Manager
  secrets (Aakash raised the drift on #65). A job for the agent's owner.
- The load stage needs: an `aoss` permission on the task role (the OpenSearch
  data access policy names the account root as principal), Bedrock access for the
  Bedrock stages, and an OpenSearch check in preflight.
- The S3 reader (PR 7) needs refreshable cross-account credentials and a
  narrowed session policy (see the build plan).

## Useful commands

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Live AWS tests, and the Neptune tunnel, are described in the README.
