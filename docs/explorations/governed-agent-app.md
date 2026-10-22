# Explore: Agent Work & Project Control Center on Temper

Status: **Explore / unapproved for implementation or deployment**  
Date: 2026-10-22  
Fork: https://github.com/toasterman234/temper  
Upstream: https://github.com/nerdsane/temper

## Objective

Evaluate a **unified agent-work and project-sprawl control center**: know what exists, what is active, who owns the next step, what was actually verified, and whether new work overlaps, conflicts with, or supersedes prior work. Temper is a candidate policy/state/effect-boundary component, not the complete discovery, scheduling, memory, or agent-execution solution.

This document records *candidate* scope and investigation. It is not a decision to replace an existing canonical store, agent configuration, or governance system.

## Verified starting state

- Fork exists and write access is available; `main` was the only branch found before exploration. A search found no fork-specific issues.
- GitHub Issues are disabled on the fork: an attempt to create the exploration issue returned **HTTP 410**. This document in an isolated branch is the durable record instead. Do not enable Issues implicitly or claim an issue was opened.
- [Temper Agent Guide](../AGENT_GUIDE.md) exists at `docs/AGENT_GUIDE.md`, and specifies CSDL XML data contracts, I/O Automata TOML behavior, Cedar authorization, code generation, and a verification cascade.
- Existing [oncall reference app](../../reference-apps/oncall/) contains specs, tests, integration settings, and Docker Compose. Reuse patterns before creating a new application.
- The guide describes a single-node current runtime with a PostgreSQL event journal. It states Redis-backed mailboxes are for possible future distributed actor messaging rather than today's synchronous request handling. Treat this as documented behavior, not independently runtime-verified.
- No build, automated verification, workload benchmark, Northflank deployment, or external agent integration has been run for this fork yet.

## Candidate narrow first application

**Governed Work + Evidence + Approval + Intake/Sprawl + Liveness**, NOT an instant replacement for the entire control plane. Start with a **single vertical proof** that incorporates history lookup, one creation/transition boundary, and one independently verified close decision.

Candidate entities: `Work`, `Actor`, `ActionRequest`, `Decision`, `Evidence`, `Run`, and `ExternalReference`. Preserve links to existing projects and evaluations without duplicating their source-of-truth records.

Candidate lifecycle:
`Proposed -> Investigating -> ReadyForValidation -> Validated -> AwaitingApproval -> Approved -> Executing -> Verifying -> Closed`; include `Blocked`, `Rejected`, and `Failed` paths.

Invariants to specify and verify:
- No transition to `Approved` without the required authorized decision.
- No transition to `Closed` without independently verified outcome evidence.
- An exploratory record cannot execute changes without explicit promotion and approval.
- External actions cannot claim enforced governance unless all relevant mutation paths pass through the authoritative control.
- Superseded/rejected decisions and previous failures remain linked and visible.

## Expanded problem statement: why agent/project sprawl happens

The target failure is not merely a badly classified status: agents discover a possibility, start a new repository/branch/project, produce plans and reports without linking them, stop before verified completion, or repeat/supersede previous efforts without checking them. Project records, sessions, services and GitHub issues diverge. A dashboard may show plenty of objects while no one owns the next action.

This Explore should answer, with source-backed data:
- **Existing work:** What have we attempted before; where, by whom, and with what disposition (active, paused, rejected, retired, superseded, failed, completed)?
- **Portfolio:** What's open now; which explorations are only ideas, which work is approved and runnable, which runs are genuinely active vs stale, and what's waiting on whom?
- **Ownership:** For every nonterminal item, who owns its next action, what exactly must happen, when should it be rechecked, and what triggers an escalation?
- **Sprawl:** Are agents duplicating work, starting unapproved projects, redoing a rejected solution, or editing conflicting source paths?
- **Documentation/evidence:** Does every meaningful state change have a durable, provenance-carrying record and reproducible evidence, not merely a conversational claim?
- **Closeout:** Did the intended outcome occur in the authoritative target, and was it independently checked? A successful write, test, started run, or green build alone is insufficient.
- **Learning:** Are recurring faults connected to Cases/Evals/Controls rather than endlessly reintroduced as untracked preferences?

### Scope of control

Govern all *supported, mediated* lifecycle operations. Outside observations (raw session logs, GitHub webhooks, filesystem/host events, cloud provider metadata) are source facts or unverified claims until reconciled. **No design can prevent ungoverned external effects while agents retain unrestricted bypass paths.** Adopt read-only visibility before enforcing a given write path; show bypass coverage and enforcement strength explicitly.

## Candidate architecture: six cooperative capabilities

| Capability | Inputs / output | Proposed implementation and ownership |
|---|---|---|
| 1. **Intake, classification, history** | User idea, Event, Issue, failed eval, agent proposal -> exact matches, related work, conflicts, provenance, routing candidate | Deterministic IDs/source search first; optional semantic/graph discovery for suggestions only; ambiguous findings held for review. Reuse master-repo #76 rather than duplicate its approved Work. |
| 2. **Portfolio + lineage** | Project/Explore/Work/Task/Case/Decision/Plan and repo/branch/PR/file refs -> current state, relationships and timeline | Versioned cross-source projection; existing canonical LinkML/registry + PostgreSQL authority retained; derived edges stay noncanonical. |
| 3. **Governed actions** | Actor, object, current state/version, action, policy/decision and evidence refs -> allow/deny/propose transition | Temper IOA/Cedar candidate for a **bounded** transition gate; trusted host must intercept actual mutation. Evaluate interoperability with existing Transition Controller (#129/#139/#156). No silent replacement. |
| 4. **Work progression/liveness** | Active/blocked/awaiting state, assignee, dependencies, deadline/wake condition, last observation -> next eligible action/escalation | Reuse #27 Progress Controller / durable execution instances where already effective; add missing reconciliation and wake sources, not a new competing orchestrator. |
| 5. **Execution + evidence** | Agent run/tool action, execution receipt, artifacts, test/eval, real target read-back -> evidence-backed outcome | Capture immutable source IDs, versions, hashes, timestamps and affected objects; separate ActionRequest, Run, Result, Verification, Decision, Outcome. |
| 6. **Discovery + improvement** | Event/session/history diffs, stale/duplicate/conflict detection, failed verification -> Observation/Case/ChangeProposal | Deterministic checks where possible; embeddings/graph/LLM propose overlap/conflict only. Route learning to #76/#167/#360; never auto-adopt new policy. |

### Authority: do not create a second canonical truth by accident

- **Definitions:** master-repo-0.1's registry, LinkML, relationships and canonical contracts are forward semantic authority until explicitly changed.
- **Canonical state:** existing governed PostgreSQL write path remains authoritative. A GitHub Issue's open/closed state, Pi/Muse message, Hindsight memory, derived graph, and Temper process state each carry **separate source and freshness**; no silent overwrite.
- **Operational progression:** existing Progress Controller / ExecutionInstance machinery and related liveness Work (#27) have established ownership, with gaps remaining in front-door intake and routing (#76). Assess whether Temper can enforce at their boundaries instead of replacing them.
- **Temper's own data:** may persist engine state, policy decisions, and events for its authorized scope; it must not become an unapproved competing store for Project/Work canonical state.
- **History:** source facts and prior Decisions (including rejected/retired/superseded) are preserved, never erased by a revised projection. Derived context from Graphiti/Hindsight is evidence for discovery, not authorization.
- **Integration:** prefer read-only collection + keyed reconciliation -> candidate action -> existing approved mutator -> independent authoritative read-back. No automatic back-propagation into canonical Postgres, GitHub, agent profiles, or production execution without a specific approved contract.

## Object and relationship model (candidate views, not new canonical classes)

Use **existing entity types and IDs** wherever defined. These terms are functional roles until mapped against the current registry; do not append duplicate ontology classes merely because Temper uses CSDL.

| Object/view | Required relationships or fields | Why it matters |
|---|---|---|
| Project / Goal | Owner, approved Plan, status, scope, dependencies, related/competing Projects, success criteria | Discourage unapproved new projects; show what goal a project advances |
| Explore / Proposal | Question, alternatives, parent, sources, last decision, explicit promotion/retirement | Ideas stay Explore, not automatically implemented |
| Work / Case | Parent Project/Plan, issue/repo, assignee, owner, next action, due/wake condition, blocker, terminal criteria | Every open item is actionable or transparently waiting |
| Agent / Capability / Session | Identity, host/profile/config version, permissions, tools, linked Runs/Work, source timestamp | Know who actually did what with which effective config |
| Run / ActionRequest / ActionResult | Work, requested effect, approvals, agent identity, start/end, side effects, status, retry/idempotency refs | Started ≠ completed; correlate execution and effects |
| Artifact / Evidence / Verification | Work/Run/Decision, path/URL, commit/hash, original source, observed time, independent outcome/read-back | Document as work occurs; stop unsupported completion claims |
| Decision / Gate / Policy / Rule / Eval | Authority and scope, effective version, approval, enforcement location, evidence, supersedes/contradicts/derived-from | Show why actions are permitted and what rules are actually wired |
| Blocker / Dependency / Wake | Cause, responsible resolver, required input, next check time/event, escalation and clear condition | Prevent stranded work and indefinite 'waiting' |

Required lineage graph links to explore: \`parent_of\`, \`implements\`, \`explores\`, \`depends_on\`, \`owned_by\`, \`spawned_by\`, \`observed_in\`, \`produced\`, \`evidenced_by\`, \`verified_by\`, \`approved_by\`, \`blocked_by\`, \`duplicates\`, \`overlaps\`, \`conflicts_with\`, \`supersedes\`, \`rejected_by\`, \`forked_from\`, \`promoted_from\`. Each asserted relation needs \`source_ref\`, status (candidate/confirmed/rejected), last_checked, and canonical/external ID links; similarity never proves exact identity.

## Three different lifecycles, not one giant status enum

1. **Explore**: intake -> investigating -> assessed -> decision pending -> promoted / rejected / parked / superseded. Creating an Explore and proposing a design does not authorize implementation. Promotion creates a linked, approved Work/Plan/Decision path and preserves the originating Explore.
2. **Work**: proposed -> ready -> approved -> assigned -> executing -> verifying -> completed. Include blocked/awaiting/failed/cancelled and return-to-work transitions; lifecycle gate requires supported authority and linked parent/plan.
3. **Run**: queued -> started -> running -> succeeded/failed/timed-out/cancelled -> outcome-verified (separate status/evidence). One Run success cannot automatically close Work; one Work may have many Runs and independent Verifications.

For *every nonterminal state* require a disposition: \`owner\`, \`next_action\`, \`wake_condition\` (event or scheduled recheck), \`last_checked_at\`, \`escalation_target\` as appropriate. A paused/blocked state must show the actual blocker and next human or automated resolution path. Never invent a date, and do not label stale "running" as current.

## Anti-sprawl / duplication gate before new work

Proposed **pre-create resolution**, to run before a governed agent can create a Project/Explore/Work/Case/repository/branch:
1. Identify source event/ask, scope, objective, requirements, owner, parent and a stable idempotency key.
2. Search exact identities + existing open work, prior completed work, retired/superseded/rejected decisions, and related issues/PRs/branches.
3. Query derived graph/semantic similarity for **ranked suggestions** with evidence and freshness; bounded retrieval, not an always-on LLM required for every request.
4. Return disposition: **attach/resume existing**, **subtask/extend**, **related but distinct**, **conflict requires review**, or **new proposal**. Exact/known duplicate idempotency cases can deterministically reuse; semantic similarity alone must not auto-merge distinct work.
5. Before creation, check governed parent, approved scope/plan where required, permissions, conflict/retirement history and cap on concurrent active work. A hard deny needs a source-backed deterministic rule, not an LLM score.
6. Save the decision and linkage as part of the governed action; independently read back both new object and relationships.

Detect: same goal in multiple repos, abandoned PR/worktrees, duplicate agents doing same operation, reopened failures without referencing prior Case, unsponsored child project, superseded package recreated, and a new experiment started while related work remains open. **Detection is not automatically guilt**: show confidence, suggested resolution, and accountable reviewer.

## Documentation and evidence as part of the action

Treat significant steps as committed events, not a final report written after work is done:
\`Intent/Source -> HistoryCheck -> Decision/Gate -> ActionRequest -> Run/ActionResult -> Artifact/Evidence -> IndependentVerification -> Transition -> CurrentStateReadback\`.

Recommended minimum event envelope: \`event_id\`, \`source_system\`, \`native_object_id\`, \`canonical_ref?\`, \`actor_ref\`, \`session/run_ref\`, \`project/work_ref\`, \`cause_ref\`, \`action\`, \`expected_version\`, \`occurred_at\`, \`observed_at\`, \`ingested_at\`, \`status\`, \`artifact_uri/hash?\`, \`evidence_refs\`, \`policy/decision_ref?\`, \`correlation/idempotency_key\`, \`supersedes?\`. Segregate claims from independently observed outcomes; redact secrets/private transcripts.

Ask of each report: Is the linked issue updated? Did the Git branch/PR actually change? Are the artifact and receipt readable? Has the exact target state been re-queried? What is still incomplete, blocked or unverified? A receipt is not read-back; a server HTTP 200 is not necessarily the intended business result.

## Portfolio, liveness and UI

Candidate compact overview: **Needs attention**, **Active Work**, **Explores/Proposals**, **Blocked/Waiting**, **Agents & Runs**, **Decisions/Gates**, **Evidence/History**, **Overlap/Conflicts**. Prefer one-screen overview, one row of tabs, top-right filters (agent/project/source/freshness), expandable rows, and clickable lineage; do not build a separate graph-authoring app as a prerequisite.

Each row shows \`name/ID\`, \`semantic state\`, \`operational state\`, \`assignee/owner\`, \`last verified observation + source\`, \`next action\`, \`wake/escalation\`, \`blocker\`, \`evidence\`, and \`related/duplicate\`. Do not confuse snapshots with live synchronization. Optional node/edge views are projections, not editable canonical truth.

Liveness checks: missing owner/next-action, state past wake condition, in-flight run no heartbeat, stale source, repeated failed/no-op runs, PR abandoned without disposition, Work claimed complete but authoritative Issue open, agent mutating an Explore-only artifact, unresolved conflicting decisions, verification absent, and changes without linked Work. Triggers may be event-driven; polling is only a fallback/verifier where prior #310 decision requires event capture.

## Verification scenarios to define before implementation

| Scenario | Expected result |
|---|---|
| Agent proposes already-open equivalent work | Present exact linked existing work; no duplicate governed Work created |
| Similar but materially distinct idea | Proposed relationship with review; do not falsely merge |
| Agent restarts previously rejected/superseded project | Prior Decision shown; unauthorized resume blocked at actual creation/execution boundary |
| Agent tries \`Explore -> Execute\` | Fail-closed; requires separately approved promotion |
| Agent claims \`Done\` after opening a PR or starting a job | Closure denied until correct effect verified from authoritative target |
| Evidence URI saved but cannot be read | Verification remains missing; Work stays open |
| Blocked Work with no owner/wake/escalation | Classification as actionable gap; cannot silently disappear from attention |
| Concurrent agents act on same Work/version | Optimistic version/idempotency or conflict handling; no lost update |
| Runtime restarts during action | Replay/reconcile durable events; uncertain effects remain unverified and retries are bounded |
| Direct unmediated tool bypass exists | Coverage test identifies unenforced path; do not claim universal enforcement |
| Old issue marked closed while canonical Case remains active | Source divergence surfaced, not silently reconciled |
| New rule proposed from repeated agent failures | Separate versioned ChangeProposal + tests + approval, no self-promotion |

These are **proposed tests**, not tests run or guarantees by Temper.

## Efficiency and rollout boundary

Start by enumerating number of active items, event rate, peak simultaneous agents, retention, source-read frequency, and target action latency. Use webhook/event deltas, batched deterministic exact-ID checks, indexed SQL/current-state projection and selective graph/embedding search **before** LLM classification. Reassess after measuring false duplicate matches, stale coverage, cost and storage; avoid high-volume raw session replication into the governance DB.

A valid first technical proof (only **after approved promotion to implementation**) should use a handful of realistic fixtures and *one mediated Work transition*, on a pinned Temper commit. Measure correctness + denial + read-back + restart; do not build a full UI, custom graph store, universal collectors or reimplement #27/#76 first. Northflank can wait.

## Existing ownership and decisions: do not duplicate

- [#27](https://github.com/toasterman234/master-repo-0.1/issues/27) **liveness & progression** owns owner/next-action/wake/escalation, operational instances vs canonical semantics. Earlier stages were reported verified, but the whole operational control loop remains incomplete.
- [#76](https://github.com/toasterman234/master-repo-0.1/issues/76) **Case intake/history/routing** is an already authorized Work slice; read-first dedupe, route, idempotent ExecutionInstance. Reuse this, do not open a competing intake Work.
- [#156](https://github.com/toasterman234/master-repo-0.1/issues/156) **enforcement audit** documents that generalized typed requirements and all-mutation-path protection are partial, with narrower existing guarantees.
- [#139](https://github.com/toasterman234/master-repo-0.1/issues/139) **project activation/plan gate** remains an experiment-only evaluator, not a production-enforced rule.
- [#320](https://github.com/toasterman234/master-repo-0.1/issues/320) **governance inventory** distinguishes actual code gates, approved agent lanes, and prompt-only / not-yet-effective declarations.
- [#359](https://github.com/toasterman234/master-repo-0.1/issues/359) / [#360](https://github.com/toasterman234/master-repo-0.1/issues/360) **control taxonomy** separate requirement, mechanism, effect boundary, evaluation and authority; tests are not active rules.
- [#167](https://github.com/toasterman234/master-repo-0.1/issues/167) **cross-agent learning/conflicts** is an adjacent Explore; keep prompt/policy conflict lineage and proposals there.
- [#215](https://github.com/toasterman234/master-repo-0.1/issues/215) **agent audit and visuals** is read-only and noncanonical; never treat installed skills as effective without current trace.
- [#310](https://github.com/toasterman234/master-repo-0.1/issues/310) **event sync** selected Kestra event hub as a *design*, not evidence of completed CDC. Don't start duplicate polling-based collectors.
- [#315](https://github.com/toasterman234/master-repo-0.1/issues/315) **context hub/discovery/governance** explicitly studies the same catalog loops; attach Temper as an enforcement candidate, not another catalog authority.
- [#356](https://github.com/toasterman234/master-repo-0.1/issues/356) **LangChain + ASSERT + ACS** is a distinct sandbox behavioral-eval Explore; it is complementary to Temper's state/policy controls.
- [#363](https://github.com/toasterman234/master-repo-0.1/issues/363) **shared Hindsight memory** is separate derived context/agent-history work, not a canonical source of approval/state.

**No ownership or migration decision follows from these links.** Verify current branches, source, effective runtime, closed/rejected history and exact proofs before adoption.

## Open decision points (do not treat as approved)

1. Is Temper a **new governance authority**, a narrow *policy/state plugin* called by existing controllers, or a sidecar verification engine? Default candidate: **narrow plugin/adapter to existing governed paths**, not replacement.
2. Where is the interception boundary for Pi/Muse/GitHub and which tool aliases/bypass routes remain open? Never claim platform-wide protection without them.
3. What exact fields may Temper own vs reference vs derive? Resolve before persisting external state.
4. How do blocked/waiting cases wake and get accountable human follow-up using existing #27/#76?
5. Which 5–10 historical work items make a representative fixture set, including a known sprawl/false-Done failure? Use source-linked cases, not invented current states.
6. Is a compact portfolio UI needed for the first pilot or is an existing projection sufficient?
7. Who may promote this Explore to approved Work and authorize any runtime/deployment/effectful integrations?



## First vertical proof contract (proposal only)

This section is a **bounded acceptance contract for a future approved pilot**, not authorization to implement it. The objective is to demonstrate **one actually governed lifecycle** with **three outcomes**: reuse existing Work instead of creating a duplicate; keep unresolved Work visible with a responsible next move; deny completion without independent verification.

### Canonical-type-aware model

Read directly against the current LinkML Structural-v2 source rather than treating every product concept as a new schema class:

| Product concept | Existing authoritative shape / important nuance |
| --- | --- |
| Project | \`Project\` has \`ProjectLifecycle\`: proposed / active / paused / completed / cancelled |
| Work / Case / Explore / ChangeProposal | \`Issue\` + classifiers/profile, not separate root classes by default. \`Issue\` has \`IssueBaseLifecycle\`, \`WorkLifecycle\` (proposed / active / awaiting / blocked / completed / cancelled) and \`CaseLifecycle\`; don't put invented statuses into \`work_lifecycle\` |
| Agent | \`Actor\` + capabilities/roles/tools; native session traces are source-linked Run/Event evidence, not an automatic new Agent class |
| Plan / approval | \`Plan\`, \`Gate\`, \`Decision\`; an existing Decision must have correct subject, scope and authority, not just status='accepted' |
| Action and effect | \`ActionRequest\`, \`Run\`, \`Result\`, \`Event\` and \`Change\`; \`RunStatus\` is queued/running/succeeded/failed/cancelled, not a work lifecycle |
| Closure evidence | \`Evidence\`, \`Verification\`, \`Outcome\`; receipt URI, successful response, and passed verification are distinct |
| Dependencies and conflicts | Versioned \`Relationship\` instances with controlled relationship_type and provenance, plus native typed refs. Candidate semantic similarity edges remain provisional until accepted |

Sources (read from live default GitHub main, **not** assumed deployed): [LinkML Structural-v2](https://github.com/toasterman234/master-repo-0.1/blob/main/registry/model/schema.yaml), [semantic invariants](https://github.com/toasterman234/master-repo-0.1/blob/main/registry/meta/semantic-invariants.yaml), [progress contract](https://github.com/toasterman234/master-repo-0.1/blob/main/runtime/contracts/progress-controller-v0.1.yaml), [transition contract](https://github.com/toasterman234/master-repo-0.1/blob/main/runtime/contracts/transition-controller-v0.1.yaml).

Temper's own pilot automaton can model **request/decision states** such as \`Proposed\`, \`HistoryChecked\`, \`NeedsReview\`, \`Authorized\`, \`Applied\`, \`ReadbackVerified\`, \`Denied\` without changing canonical Issue statuses. Any allowed operation must still call the existing authoritative state mutation boundary and reconcile the results.

### Four proposed user-facing operations

| Operation | What the caller provides | Returned decision | Trusted boundary |
| --- | --- | --- | --- |
| \`inspect_portfolio\` | agent/session identity, scoped source selections | current/open/blocked work + freshness + next actions + exact source links | Read-only, no semantic transition; reports unknown/stale |
| \`propose_work\` | goal, scope, source event, parent, stable request key | reuse/link/extend/conflict-review/new-proposal with source-linked matches | Read-first history and exact-ID check; **no unreviewed direct creation** |
| \`advance_work\` | existing canonical work ref, expected version, action, decision/gate/evidence refs | allow/deny; on eligible command request *existing* canonical mutation path and read back | IOA transition + Cedar actor permissions + actual target CAS/idempotency + result witness |
| \`verify_and_close\` | work ID, criteria, committed artifact refs, independent verification ref, expected version | closed / still open / missing evidence / discrepancy / blocked | Do not close just because run succeeded or a receipt exists |

Operations above are **proposed APIs**, not names existing in Temper, the master repo, or any running service.

### Exact intake resolution and sprawl classifications

Prefer deterministic exact matching first, batch/indexed search over sources second, optional semantic similarity only for **suggestions**. Persist the resolution with who/what/how it was decided.

| History result | Proposed disposition | Side effect |
| --- | --- | --- |
| Exact stable ID or same idempotency key | \`REUSE_EXISTING\` | No duplicate object |
| Active linked work with identical governed intent, source-backed | \`ATTACH_OR_RESUME\` | Link source/request and owner only through approved path |
| Similar work with material scope differences | \`RELATED_DISTINCT\` | Suggest link; don't merge automatically |
| Conflicting implementation/Decision or ambiguous authority | \`HOLD_FOR_REVIEW\` | Block mutating this scoped action; create or link review Case through authorized intake |
| Prior rejected/retired/superseded work | \`HISTORY_REVIEW\` | Require new justification/Decision; never silently reactivate |
| No confirmed match, valid parent and governance prerequisites | \`NEW_PROPOSAL\` | Create **proposal**, not automatic active Project/implementation |
| Missing source or stale identity/provenance | \`UNKNOWN_SOURCE\` | No false 'no duplicate' assertion; bounded refresh/review |

Do not convert probabilistic similarity to a hard authorization rule. Fail-closed only at a real effect boundary when missing authoritative facts or a versioned rule actually requires them; read-only discovery may return incomplete results with warnings.

### The exact end-to-end demonstration

Synthetic fixture: Source GitHub Issue A is already open for "agent closure without read-back," classified Issue[Work]; a second agent proposes the same objective and another Run reports success with only a new PR URL. (Fixture is illustrative, **not** a statement about the current state of any real user issue.)

1. \`inspect_portfolio\` returns open A with owner, last observed state, source, next action or a visible liveness defect.
2. \`propose_work\` with the same native ID/idempotency key returns \`REUSE_EXISTING\`; verify **no new canonical Issue**. A similar-but-different request returns a *suggested* relationship with \`RELATED_DISTINCT\`.
3. Approved agent advances A through its authorized work transition; wrong actor, an Explore-only scope, missing accepted Decision, or stale expected version are rejected **before external mutation**.
4. A Run \`succeeded\` but the target's authoritative state has not been independently verified. \`verify_and_close\` must deny closure and leave A open, while recording the failed/unknown verification as appropriate.
5. A later independent verifier checks the target, supplies subject-correct \`Verification\` with passed verdict and evidence, and the authorized mutator commits the terminal transition. Read back exact stored state, history, linked evidence and source projection.
6. Simulate restart or a lost response after a write; replay with the **same idempotency key**, reconcile effect before retry and prevent second logical mutation.

**Acceptance:** The pilot isn't complete until (a) the duplicate denial has evidence of absent duplicate writes, (b) wrong actor/policy/transition is demonstrably stopped at effect boundary, (c) false-Done is rejected against authoritative source, (d) restart/replay works, and (e) an independent read-back confirms final state and lineage. Passing a Temper \`verify\` command alone cannot satisfy this.

### Control mechanism allocation

| Need | Temper-native candidate | Other component / exact boundary |
| --- | --- | --- |
| Legal lifecycle transition | IOA states, guards, invariants | Canonical Transition Controller for authoritative state mutation |
| Who may approve/execute | Cedar evaluation from **trusted host identity and context** | Actual tool/effect boundary; distinguish policy decision from execution |
| Entity/action model | CSDL/OData | Existing LinkML canonical types / versioned IDs; adapter must avoid schema drift |
| Repeated work and old decisions | Not a Temper-native knowledge retrieval capability | Existing Case intake (#76), source search, graph/semantic suggestions with human adjudication |
| Keep waiting work moving | Temper state alone insufficient | Progress Controller (#27): RUNNABLE/EXECUTING/WAITING/BLOCKED/GATED/TERMINAL; owner/wake/lease/escalation |
| Source change and recency | Event journal for Temper-owned events | Existing source collectors, source-specific webhook/event work (#310) and reconciliation; no new shadow event bus |
| Independent claim verification | Tests/invariants for modeled behavior | Live authoritative target read-back; separate persisted Verification |
| Agent improvement | Temper evolution mechanisms may propose changes | Existing Cases/ASSERT/eval taxonomies; human promotion and tests |

### Specific upstream caution to test

[Temper's oncall remediation example](https://github.com/toasterman234/temper/blob/main/reference-apps/oncall/specs/remediation.ioa.toml) contains \`AutoApprove\`, which sets \`human_approved = true\`. This is suitable as an **example of model behavior**, **not proof of a human-authorized Decision**. A boolean guard can be satisfied by the wrong event or actor if policy and trusted identity are not enforced separately. Pilot negative case: an unprivileged actor invoking any automated-approval route must *not* be able to manufacture human approval or bypass a rejected decision.

### Workload and design limits to measure before authorizing implementation

Start with 5–10 source-backed examples across existing Issues, one intentionally duplicate intake, one ambiguous similar-but-distinct item, one blocked/no-owner case, one stale run and one false-Done case. Record source timestamps and version hashes for every fixture.

Estimate/measure: full-source counts, open-issue counts, typical history lookup latency and candidate counts, peak agent concurrency, real workflow events/day, daily/weekly change frequency, baseline and peak Rust build/verification RSS, steady-state memory/CPU, DB storage growth and API latency. Prefer exact/indexed queries, batched read-back, incremental source deltas; use LLM only on ambiguous candidates and compare quality/latency/cost against deterministic-only intake. Reassess if similarity false-positives, event storage or work history search becomes the bottleneck.

### Decisions still required

- Does Temper sit **in front of** the canonical Transition Controller or operate only as a **shadow verifier** for the pilot? Either choice must name its true authority.
- Who can approve a new Project/Work vs an innocuous Explore? Define source-backed authority and exceptions, rather than using a broad \`Admin\` role.
- Which tool routes will be mediated, and which remain ungoverned? Enumerate every alias and count unprotected bypass routes.
- Is the first interface purely read-only + gated actions, or must the compact dashboard be built before pilot acceptance? Default: API/table first, no UI rebuild.
- What exact review evidence constitutes **promotion** of this Explore? Until a separate authorized Work/Decision exists, stop at this documented contract.


## Mechanism classification to investigate

| Concern | Candidate enforcement |
|---|---|
| Typed objects / lineage | CSDL plus event journal / external references |
| Legal action lifecycle | IOA transition model + guard |
| Who may act or approve | Cedar policies |
| Execute tool/side effect | Controlled integration boundary / WASM where suitable |
| Subjective agent behavior | Prompt/skill and evaluation, **not** falsely called deterministic enforcement |
| Behavior regression | ASSERT and behavioral tests as a separate complementary capability |
| Audit and completion | Persisted events plus independent evidence checks |

## Dependencies and related work to review before adoption

- [master-repo PR #358 — ASSERT](https://github.com/toasterman234/master-repo-0.1/pull/358)
- [master-repo issue #363 — shared memory bank](https://github.com/toasterman234/master-repo-0.1/issues/363)
- Existing canonical object/state/evidence and policy work in master-repo-0.1; determine current state, rejection history, superseded approaches, and overlap before design promotion.

Links are **context**, not migration approval.

## Evaluation questions / next actions

- [x] Identify related master-repo owners/issues and reconcile design-level non-duplication (2026-10-22); current runtime status and individual-source disposition remain unverified.
- [ ] Check existing projects and decisions for duplicates, conflicts, retirement, and ownership.
- [ ] Confirm whether the first scope is the Work/Evidence/Approval domain, and define example use cases and counterexamples.
- [ ] Trace Temper's reference apps and model limitations, including single-node persistence, recovery, authorization, and bounded verification.
- [ ] Test a pinned upstream baseline with reproducible commands; capture results and failure evidence.
- [ ] Create a mechanism matrix with exact spec, policy, test, and action boundaries for the chosen domain.
- [ ] Estimate Rust build memory, steady-state RAM/CPU, storage, and test latency; compare simplest execution and free hosting choices.
- [ ] Verify integration path for Pi/Muse/GitHub with *read-only first*, then gate any mutations.
- [ ] Record adopt / reject / narrow pilot decision explicitly; if promoted, create separate tracked implementation work with acceptance tests.

## Authority and completion conditions

This is a discovery record, not approved implementation. No runtime source modifications, production secrets, resource creation, or deployment are authorized here. A passing spec test is not proof of a real-world side effect. A successful API call is not by itself independently verified completion.

Exploration remains **open** until the evidence and formal adoption decision are recorded.
