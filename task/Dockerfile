# syntax=docker/dockerfile:1
# Pipeline task image: runs `dia <command>` (for example `dia pipeline preflight`).
#
# Build from the repository root:
#   docker build -f task/Dockerfile -t dia-task .
#   docker run --rm dia-task --version
#
# Only the `pipeline` extra is installed. The agent's dependencies are not in
# the image, and neither are dev dependencies (pytest, ruff) or the Zscaler fix.
#
# Follows uv's guidance for Docker:
#   https://docs.astral.sh/uv/guides/integration/docker/

# ── Pin the uv version (update deliberately) ──────────────────────────────
FROM ghcr.io/astral-sh/uv:0.11.17 AS uv

# ── Build stage: install dependencies, then the project, into /app/.venv ──
FROM python:3.12-slim AS builder

COPY --from=uv /uv /uvx /bin/

# Copy instead of hard-linking because the cache mount is on a different
# filesystem; use the image's Python so the venv works in the runtime stage.
# Bytecode is not precompiled: it saves about 500MB, and tasks run for minutes
# to hours, so the ~0.1s extra start-up does not matter.
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# The version comes from git tags (hatch-vcs), and there is no .git here, so the
# build is told the version instead.
ARG DIA_VERSION=0.0.0.dev0

WORKDIR /app

# Dependencies first: this layer is rebuilt only when uv.lock or pyproject.toml changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --extra pipeline

# Then the project itself, installed (not editable) so the source isn't needed at runtime.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    SETUPTOOLS_SCM_PRETEND_VERSION=${DIA_VERSION} \
    uv sync --locked --no-dev --no-editable --extra pipeline

# ── Runtime stage: Python and the virtual environment only (no uv) ────────
FROM python:3.12-slim

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

COPY --from=builder --chown=nonroot:nonroot /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER nonroot
WORKDIR /home/nonroot

# A task supplies the command: `["pipeline", "preflight"]`, `["extract-text", "--source", "..."]`, ...
ENTRYPOINT ["dia"]
