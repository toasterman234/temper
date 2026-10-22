# Agent Work pilot, not the root Dockerfile (which builds the Temper platform).
# Northflank build context: repository root; Dockerfile: /reference-apps/agent-work/Dockerfile.
FROM rust:1.92-bookworm AS guard-builder
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends \
      libz3-dev pkg-config clang libclang-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Match the repository's pinned toolchain, so this builds the same guard as CI.
RUN rustup toolchain install nightly-2026-02-08 --profile minimal
ENV RUSTUP_TOOLCHAIN=nightly-2026-02-08 \
    CARGO_BUILD_JOBS=2 \
    CARGO_PROFILE_RELEASE_DEBUG=0 \
    CARGO_PROFILE_RELEASE_LTO=off \
    CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
# The new workspace member is not yet recorded in root Cargo.lock.
# Cargo resolves that local member while retaining existing locked dependencies.
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    cargo build --release -p agent-work-reference --bin work_guard

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends libz3-4 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 agentwork \
    && useradd --uid 10001 --gid 10001 --home-dir /app --no-create-home agentwork \
    && mkdir -p /app /data \
    && chown -R 10001:10001 /app /data
COPY --from=guard-builder /src/target/release/work_guard /usr/local/bin/work_guard
COPY --chown=10001:10001 reference-apps/agent-work/api.py reference-apps/agent-work/control.py reference-apps/agent-work/github_source.py reference-apps/agent-work/native_guard.py /app/
WORKDIR /app
USER 10001:10001
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORK_DEPLOYMENT_MODE=northflank \
    WORK_DB=/data/agent-work.sqlite3 \
    WORK_GUARD_BIN=/usr/local/bin/work_guard
EXPOSE 8765
# /healthz checks the local DB; no GitHub network dependency for liveness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3).read()" || exit 1
CMD ["python3", "api.py", "serve", "--bind", "0.0.0.0", "--port", "8765"]
