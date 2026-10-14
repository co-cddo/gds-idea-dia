# Handover

Working notes for whoever picks this work up next, human or agent. This file
goes stale quickly: **update it at the end of every PR**, and keep the
"Current position" section accurate above all.

The agreed design is in [`pipeline-spec.md`](pipeline-spec.md). This file
covers where we are, how we work, and facts that are not obvious from the code.

## Current position

- The spec has been reviewed and merged (#61). Aakash reviewed it and is
  reviewing each step of the build.
- PRs 1 and 2 of the build plan (spec section 7) are merged (#62): the spec
  update and handover, then the naming module.
- PR 3, the Docker image, is merged (#63).
- PR 4a, the runtime config model and `dia pipeline preflight`, is open as a
  draft. **Known limitation:** it is CLI code only, and nothing writes the
  runtime config parameter yet, so the "runtime config" check fails (and the
  in-task Neptune check is skipped). This is expected. The parameter holds
  values from the ECS task stack (task definition, subnets, security group, log
  group), so it is written by PR 4b.
- **Next:** PR 4b, the ECS task definition and its IAM role in CDK, the
  security group that lets tasks reach Neptune, and the runtime config
  parameter.
- Only the foundations are built so far (naming, the extras split, the task
  image, preflight). The rest of `src/dia` is work in progress that nobody
  uses, and may be deleted as the PR that replaces each part lands.

## How we work

- **Small, reviewable PRs.** One thing per PR, with tests. Aakash reviews each.
- **Open every PR as a draft.** Permission rules block normal PR creation.
- **Each PR removes the old code it replaces,** rather than one large deletion
  at the end.
- **Scope is GATS business cases first.** Other sources come after.
- **Discuss decisions in short sections,** starting from requirements in plain
  language. Do not go into implementation detail until it is needed.
- Do not commit, push or open PRs unless asked.
- **AI review:** add the `ai-review` label to a PR to get an advisory review
  from `gds-idea-ai-reviewer[bot]` (it is non-blocking, and no label means no
  run and no cost). It needs the `ai-review` job in
  `.github/workflows/ci_pr_cdk_app.yml`, the org secret
  `GDS_IDEA_AI_REVIEWER_APP_ID` shared with this repo (it is public, and that
  secret is private to private repos unless the repo is added), and the
  `gds-idea-ai-reviewer` GitHub App installed on the repo.
- **`ci_pr_cdk_app.yml` is managed by `idea-app` but edited by hand,** and
  should stay that way. The template sets `run-version-check: true`, which fails
  here because the version comes from git tags (hatch-vcs) and there is no
  `version =` line in `pyproject.toml`. We also differ from the template in two
  other ways: the trigger includes `reopened`, and the CI jobs skip on any
  `labeled` event (the template skips only for the `ai-review` label, so adding
  any other label, such as a release bump label, re-runs all of CI). If you run
  `idea-app update`, do not use `--force` on that file.

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
  co-cddo/gds-idea-cdk-constructs-new#62. For PR 4b: CDK's Docker asset hashing
  does not read `task/Dockerfile.dockerignore`, so the asset needs an explicit
  exclude list.
- **Commands:** pipeline commands live under `dia pipeline` and the agent under
  `dia agent`. `extract-text` and `ledger` are still at the top level and move
  under `pipeline` when they are rewritten (PRs 11 to 14). `dia agent status`
  is effectively the agent's own preflight, and could be renamed to
  `dia agent preflight` for symmetry (a job for the agent's owner).
- **Runtime config:** CDK writes the Neptune endpoint and port, the OpenSearch
  endpoint, cluster, task definition, subnets, security group and log group as
  one JSON parameter, `dia-runtime-config-{phase}`. It is read through
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
  builds the cross-account client itself; PR 7 should take that over, and PR 9
  should make it read the new source definitions.
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
- CI deploys on merge: `dev` branch to the dev account, `prod` branch to prod.
  The CI workflows are managed by `idea-app` and should not be hand-edited.

## Open actions

- Confirm that the prod cross-account role can read the GATS and SR25 locations,
  and who manages that role. It is probably outside this repo. Running
  `dia pipeline preflight` in dev shows whether dev can assume the role and read
  GATS.
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

## Useful commands

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Live AWS tests, and the Neptune tunnel, are described in the README.
