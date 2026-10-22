# Deploy the Agent Work pilot to Northflank

Status: **deployment package, not a production-governed fleet**. This deploys a **local, stateful pilot API** with read-only access to selected GitHub repositories, a compiled Temper Cedar + IOA guard for its supported HTTP mutations, and SQLite persistence. It does not provide a graphical dashboard, active GitHub synchronization, Pi/Muse interception, or GitHub write access.

## Create the Northflank service

From the **Temper fork**: [toasterman234/temper](https://github.com/toasterman234/temper).

| Northflank field | Exact value |
| --- | --- |
| Service type | **Combined service**, Git repository (build and deploy from source) |
| Repository | `toasterman234/temper` |
| Branch | `work/agent-work-pilot` |
| Build type | **Dockerfile** (not Buildpack) |
| Dockerfile location | `/reference-apps/agent-work/Dockerfile` |
| Build context | `/` (repository root; workspace Cargo crates must be available) |
| Runtime CMD override | **None** (use Dockerfile CMD) |
| Runtime port | **8765**, HTTP/1.1; initial accessibility **Private** |
| Instances | **1 only** (SQLite + single-read/write volume) |
| Persistent volume | Add **Single Read/Write** volume, mount inside container at **`/data`**, with sufficient capacity for your work records and backups |
| Health check | HTTP GET **`/healthz`**, port **8765**, initial delay about 15–30 seconds |
| Build resources | Rust native guard compile is much heavier than Python runtime; use sufficient build CPU/RAM and inspect build output before changing runtime sizing |
| Runtime resources | Start modest (e.g., 1 GB RAM), reassess actual metrics after the first successful boot |

**Do not use the repository-root `Dockerfile`.** It builds the broader Temper platform server, not the Agent Work pilot.

### Runtime environment and secrets

Set the following in **Northflank runtime environment**, marking tokens as **secrets**. These must *not* be Docker build arguments or committed files.

| Variable | Value |
| --- | --- |
| `WORK_AGENT_ID` | `pi` (or a dedicated trusted agent identity) |
| `WORK_APPROVER_ID` | `human-reviewer` (distinct from agent and verifier) |
| `WORK_VERIFIER_ID` | `independent-verifier` (distinct from the other two) |
| `WORK_AGENT_TOKEN` | Independently generated **32+ character** random secret |
| `WORK_APPROVER_TOKEN` | Different **32+ character** random secret |
| `WORK_VERIFIER_TOKEN` | Third distinct **32+ character** random secret |
| `WORK_GITHUB_REPOS` | `toasterman234/master-repo-0.1,toasterman234/temper` |
| `WORK_GITHUB_READ_TOKEN` | GitHub **fine-grained read-only token** for those repos, including Issues: Read and Pull requests: Read |

The Docker image already sets `WORK_DEPLOYMENT_MODE=northflank`, `WORK_DB=/data/agent-work.sqlite3`, and `WORK_GUARD_BIN=/usr/local/bin/work_guard`. **Do not overwrite** these unless you are explicitly changing the validated deployment contract.

You previously added the read token to **GitHub Actions** as `AGENT_WORK_GITHUB_READ_TOKEN`. That GitHub Actions secret **does not automatically transfer to Northflank**; enter the same credential separately as Northflank **`WORK_GITHUB_READ_TOKEN`**, or issue a separate scoped read-only token. Do not send a token through chat.

The service deliberately **refuses to start** if the persistent volume isn't mounted at `/data`, one of the role tokens is missing/too short, identities aren't distinct, or its GitHub configuration is absent. This prevents accidental temporary storage or an unintended public bind.

### Networking and access

**Start with a private port** within your Northflank project. The container listens on `0.0.0.0:8765` *inside the service network* only, not on an unauthenticated public listener by itself.

If you later need public access, change port 8765 to **Public HTTP** in Northflank's `Configure → Networking`. Northflank will terminate public HTTPS and forward internally; additionally enable Northflank IP/SSO/Basic Auth path security policies where available. Do **not** use the HTTP URL directly outside that managed ingress. The API itself requires per-role bearer tokens for every non-health path, but it is **not a hardened multi-user identity system**. Avoid publishing it until those network policies and your threat model are acceptable.

Use a Northflank port-forward or internal service caller for first verification, not a public endpoint. Avoid copying the agent/approver/verifier secrets into console logs or screenshots.

## First checks

When the service is running, inspect Northflank's build/run logs, then query from an authorized internal caller or permitted HTTPS ingress:

```bash
# Endpoint must be your actual Northflank forwarded/TLS URL, not http://0.0.0.0.
export APP_URL="https://<your-northflank-service-domain>"
curl -fsS "$APP_URL/healthz"

# Use the configured agent token for read-only inventory (do not echo secrets).
curl -fsS "$APP_URL/github/source?ref=github:toasterman234/master-repo-0.1/issues/76" \
  -H "Authorization: Bearer $WORK_AGENT_TOKEN"

curl -fsS "$APP_URL/github/portfolio" -H "Authorization: Bearer $WORK_AGENT_TOKEN"
```

The expected source observation is an independently fetched GitHub Issue with a source URL, current GitHub state and update timestamp. The portfolio is **bounded (40 issues + 40 PRs per repository)** and is not a complete history.

Verify the unauthenticated `/portfolio` returns **401**, the configured GitHub Issue is accessible, and the SQLite-backed local Work survives a restart of the single container. Do not re-create the volume when restarting; deleting it deletes the local pilot history. Back up `/data` before destructive deployments.

The health check intentionally validates only that the local database is queryable; it is **not** a proof of GitHub availability, Cedar authorization, or real-world side effects. GitHub outages produce unavailable reads, not a false "no duplicates" conclusion.

## Security and data limitations

- Keep a **single replica** on an attached Single Read/Write volume. SQLite concurrent replicas against shared storage are unsupported for this pilot.
- GitHub integration is read-only. It has no GitHub write credential; local Work does **not** replace canonical `master-repo-0.1` Issue or Decision state.
- Incoming proposal/verification requests may create local records **only through the authenticated HTTP interface**; direct database filesystem access is outside the guard.
- The local evidence check can verify an Issue's open/closed state or PR's merged/open/closed state via GitHub API. A PR being merged does **not** prove every acceptance criterion was fulfilled.
- Runtime services do not inherit GitHub Actions secrets. Use independent runtime secrets; do not bake credentials into images.
- The endpoint lacks per-user tenancy, broad abuse protection, password rotation UI, token recovery, and full audit of host-level bypass. Prefer private networking until better controls exist.
- Cost: container build of Temper's Rust libraries is substantially heavier than the steady-state Python API. Avoid rebuilding repeatedly and use the Northflank build cache where practical. Inspect Northflank's volume and compute pricing for your plan before final service creation.

### Useful Northflank documentation

- [Build with a Dockerfile](https://northflank.com/docs/v1/application/build/build-with-a-dockerfile)
- [Configure ports and private/public accessibility](https://northflank.com/docs/v1/application/network/configure-ports)
- [Add a persistent volume](https://northflank.com/docs/v1/application/databases-and-persistence/add-a-volume)
- [Configure health checks](https://northflank.com/docs/v1/application/observe/configure-health-checks)
