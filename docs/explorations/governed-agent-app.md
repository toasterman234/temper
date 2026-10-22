# Explore: Temper for a governed multi-agent application

Status: **Explore / unapproved for implementation or deployment**  
Date: 2026-10-22  
Fork: https://github.com/toasterman234/temper  
Upstream: https://github.com/nerdsane/temper

## Objective

Evaluate Temper as a portable governed application runtime for Pi, Muse, and other agents: entities and relationships, explicit lifecycles, policy, approvals, external actions, evidence, evaluation feedback, and audit history.

This document records *candidate* scope and investigation. It is not a decision to replace an existing canonical store, agent configuration, or governance system.

## Verified starting state

- Fork exists and write access is available; `main` was the only branch found before exploration. A search found no fork-specific issues.
- GitHub Issues are disabled on the fork: an attempt to create the exploration issue returned **HTTP 410**. This document in an isolated branch is the durable record instead. Do not enable Issues implicitly or claim an issue was opened.
- [Temper Agent Guide](../AGENT_GUIDE.md) exists at `docs/AGENT_GUIDE.md`, and specifies CSDL XML data contracts, I/O Automata TOML behavior, Cedar authorization, code generation, and a verification cascade.
- Existing [oncall reference app](../../reference-apps/oncall/) contains specs, tests, integration settings, and Docker Compose. Reuse patterns before creating a new application.
- The guide describes a single-node current runtime with a PostgreSQL event journal. It states Redis-backed mailboxes are for possible future distributed actor messaging rather than today's synchronous request handling. Treat this as documented behavior, not independently runtime-verified.
- No build, automated verification, workload benchmark, Northflank deployment, or external agent integration has been run for this fork yet.

## Candidate narrow first application

**Governed Work + Evidence + Approval**, not the entire control plane.

Candidate entities: `Work`, `Actor`, `ActionRequest`, `Decision`, `Evidence`, `Run`, and `ExternalReference`. Preserve links to existing projects and evaluations without duplicating their source-of-truth records.

Candidate lifecycle:
`Proposed -> Investigating -> ReadyForValidation -> Validated -> AwaitingApproval -> Approved -> Executing -> Verifying -> Closed`; include `Blocked`, `Rejected`, and `Failed` paths.

Invariants to specify and verify:
- No transition to `Approved` without the required authorized decision.
- No transition to `Closed` without independently verified outcome evidence.
- An exploratory record cannot execute changes without explicit promotion and approval.
- External actions cannot claim enforced governance unless all relevant mutation paths pass through the authoritative control.
- Superseded/rejected decisions and previous failures remain linked and visible.

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
