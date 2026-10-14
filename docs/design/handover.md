# Handover

Working notes for whoever picks this work up next, human or agent. This file
goes stale quickly: **update it at the end of every PR**, and keep the
"Current position" section accurate above all.

The agreed design is in [`pipeline-spec.md`](pipeline-spec.md). This file
covers where we are, how we work, and facts that are not obvious from the code.

## Current position

- The spec has been reviewed and merged (#61). Aakash reviewed it and is
  reviewing each step of the build.
- PRs 1 and 2 of the build plan (spec section 7) are on the
  `docs/spec-review-and-plan` branch: the spec update and handover, then the
  naming module.
- **Next:** PR 3, the Docker image.
- Nothing in the build plan has been implemented yet. The existing code in
  `src/dia` is work in progress that nobody uses, and may be deleted as the PR
  that replaces each part lands.

## How we work

- **Small, reviewable PRs.** One thing per PR, with tests. Aakash reviews each.
- **Open every PR as a draft.** Permission rules block normal PR creation.
- **Each PR removes the old code it replaces,** rather than one large deletion
  at the end.
- **Scope is GATS business cases first.** Other sources come after.
- **Discuss decisions in short sections,** starting from requirements in plain
  language. Do not go into implementation detail until it is needed.
- Do not commit, push or open PRs unless asked.

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
  `dia-ledger-dev`, and `names.bucket(Bucket.TEXT_EXTRACTED)` gives
  `gds-idea-dia-text-extracted-dev`. In CDK use `config.names`. In the CLI use
  `dia.cli_helpers.current_names()`, which looks up the account.
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
  and who manages that role. It is probably outside this repo.
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
