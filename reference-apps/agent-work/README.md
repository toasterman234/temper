# Agent Work & Anti-Sprawl — executable local pilot

This is a **working, isolated HTTP/SQLite service** with Temper IOA/CSDL/Cedar reference specifications and native verification tests. The Python service enforces its own concrete local lifecycle/role checks; **it does not yet run inside Temper or evaluate the Cedar file**. It does not connect to, mutate or claim authority over Pi, Muse, GitHub, master-repo PostgreSQL, or other services.

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
cargo test -p agent-work-reference --test temper_work
# Once a compatible Temper executable is built:
temper verify --specs-dir reference-apps/agent-work/specs
```

Python tests execute real HTTP authorization, concurrency/idempotency, SQLite, false-Done denial and restart durability. Rust tests use Temper's verification cascade and deterministic simulated actor path (separate from the Python effect boundary). The Cedar file is **candidate policy, not effective enforcement**.

## Boundaries / work remaining

This is a local pilot, **not** the complete Temper-based governance application. Integration of the Temper actor/Cedar decision with the actual local mutation path, trustworthy GitHub/Pi/Muse source retrieval, semantic duplication/history detection, real independent external readback, distributed liveness, and bypass coverage are still needed. Retain master-repo-0.1's canonical schema, Progress Controller and Transition Controller ownership until any migration is explicitly decided. Nothing has been deployed.

Design and ownership: [Exploration PR #1](https://github.com/toasterman234/temper/pull/1), [master-repo issue #27](https://github.com/toasterman234/master-repo-0.1/issues/27), [#76](https://github.com/toasterman234/master-repo-0.1/issues/76).
