# Agent Work & Anti-Sprawl — executable local pilot

This is an **isolated HTTP/SQLite pilot** with a **required native Temper Rust authorization process** on all HTTP mutations. The process evaluates the live `work.cedar` policy using Temper's `temper-authz` library and legal model transitions using Temper's `temper-jit` I/O-automaton table. Python still owns the local SQLite write, idempotency and fixture verification checks. It does not connect to, mutate, or claim authority over Pi, Muse, GitHub, master-repo PostgreSQL, or other services.

## Current capabilities

- `propose_work`: durable proposed Work with source identity, intent key, parent and owner, exact idempotency, atomic duplicate reuse. No semantic or historical graph matching yet.
- `inspect_portfolio`: read work, state, owner, next action, wake condition, source ref, version and audit count.
- `advance_work`: require reviewer approval and assigned owner; enforce legal transitions, optimistic version check, and wake condition on blocked/waiting.
- `record_evidence`: persist artifact URI and SHA-256 claim separately from actual verification.
- `verify_and_close`: only a separate verifier may close, and only after a fresh matching **local test-fixture** readback. A green test, PR URL or agent statement is insufficient by itself.
- Durable SQLite events for decisions, transitions, verification passes/failures, authenticated rejected requests; isolated local fixture target setter.

## Run (Python 3.11+, standard library only)

```bash
cd reference-apps/agent-work
export WORK_DB="$PWD/pilot.sqlite3"
export WORK_AGENT_ID=pi WORK_APPROVER_ID=human WORK_VERIFIER_ID=independent-reviewer
export WORK_AGENT_TOKEN='<random 24+ character secret>'
export WORK_APPROVER_TOKEN='<different random 24+ character secret>'
export WORK_VERIFIER_TOKEN='<third different random 24+ character secret>'
# Compile Temper Cedar + state machine decision guard before starting the API.
cargo build -p agent-work-reference --bin work_guard
export WORK_GUARD_BIN="$(git rev-parse --show-toplevel)/target/debug/work_guard"
python3 api.py serve --bind 127.0.0.1 --port 8765
```

Keep it **localhost only**. It has no TLS, production identity federation, configurable multi-user permissions, external mutator or server-side scheduling. Never commit tokens.

| Method | Endpoint | Authorized role |
|---|---|---|
| GET | `/healthz` | public basic health only |
| GET | `/portfolio` | authenticated |
| GET | `/history/<work-id>` | authenticated |
| POST | `/propose_work` | agent |
| POST | `/approve` | approver |
| POST | `/advance_work` | agent owner |
| POST | `/record_evidence` | agent owner |
| POST | `/verify_and_close` | independent verifier |

The gateway derives the actor's identity from its configured bearer token; caller-supplied actor/owner/verifier identities are rejected.

First request:

```bash
curl -sS http://127.0.0.1:8765/propose_work \
  -H "Authorization: Bearer $WORK_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Stop false Done","intent_key":"closure-discipline","source_ref":"issue:demo-1","parent_ref":"project:pilot","request_key":"req:demo-1"}'
```

Returns a `NEW_PROPOSAL` with `state=proposed` and `version=1`. Repeating it returns `REUSE_EXISTING` without creating another Work. A different source with the same intent key is rejected as an identity conflict for review; similarity alone is **not** a trusted duplicate proof.

To approve, call POST `/approve` with `{"work_id":"<id>","expected_version":1}` under the approver bearer token. It increments the version. Activate by calling POST `/advance_work` with `{"work_id":"<id>","expected_version":2,"target":"active","next_action":"independently verify result"}` under the agent token. To block/await, supply a nonempty `wake_condition`.

Submit evidence using POST `/record_evidence` (agent role) with `work_id`, `artifact_ref`, lowercase 64-hex `artifact_sha256`, `target_key`, and `expected_value`. The verifier calls `/verify_and_close` with `work_id`, `expected_version` and returned `evidence_id`.

**The readback is a fixture, not a real GitHub query.** Populate it *locally only* after evidence submission:

```bash
python3 api.py fixture-target --db "$WORK_DB" --key 'repo:demo' --value merged
```

The target key and expected value must match the evidence. The fixture setter is intentionally absent from HTTP. This verifies local control logic only, not an external change.

## Tests

```bash
python3 -m unittest discover -s tests -v
cargo test -p agent-work-reference
cargo build -p agent-work-reference --bin work_guard
WORK_GUARD_BIN="$(git rev-parse --show-toplevel)/target/debug/work_guard" \
  python3 -m unittest discover -s tests -v
# Once a compatible Temper executable is built:
temper verify --specs-dir reference-apps/agent-work/specs
```

Python tests exercise HTTP authentication, idempotency, SQLite, false-Done denial, and restart durability; the second run executes those HTTP tests with the **compiled Temper Cedar + IOA guard actually required in each mutation transaction**. Rust tests separately run the Temper verification cascade, deterministic simulation, direct Cedar/IOA decision cases, and malformed-request fail-closed behavior.

There is no permissive HTTP fallback if `WORK_GUARD_BIN` is unset/unavailable. Fixture observations remain local and manually inserted; native policy enforcement **does not prove external GitHub state**.

## Boundaries / work remaining

This is a local pilot, **not** the complete Temper-based governance application. The local HTTP mutation path now invokes Temper Cedar and IOA, but **the runtime is not yet a Temper-hosted actor**, and a direct Python `WorkControl` instance without a native gate remains possible outside the supported HTTP entrypoint. Trusted GitHub/Pi/Muse source retrieval, semantic/history matching, external authoritative read-back, durable distributed liveness, network-grade authentication, and total mutation-path bypass coverage are still needed. Retain master-repo-0.1's canonical schema, Progress Controller and Transition Controller ownership until any migration is explicitly decided. Nothing has been deployed.

Design and ownership: [Exploration PR #1](https://github.com/toasterman234/temper/pull/1), [master-repo issue #27](https://github.com/toasterman234/master-repo-0.1/issues/27), [#76](https://github.com/toasterman234/master-repo-0.1/issues/76).
