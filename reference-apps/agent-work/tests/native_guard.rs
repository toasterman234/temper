//! End-to-end process-level tests for native Temper Cedar + IOA work guard.
use std::io::Write;
use std::process::{Command, Stdio};

use serde_json::{Value, json};

fn probe(role: &str, identity: &str, owner: &str, state: &str, action: &str,
         model_action: Option<&str>, approved: bool, evidence: bool, verified: bool) -> (bool, String) {
    let req = json!({
        "role": role, "identity": identity, "owner_ref": owner, "status": state,
        "action": action, "model_action": model_action,
        "approved": approved, "evidence_present": evidence,
        "independent_verification_passed": verified
    });
    let mut child = Command::new(env!("CARGO_BIN_EXE_work_guard"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().expect("work_guard binary");
    child.stdin.take().expect("stdin").write_all(req.to_string().as_bytes()).expect("write");
    let output = child.wait_with_output().expect("response");
    let text = String::from_utf8_lossy(if output.status.success() { &output.stdout } else { &output.stderr }).into_owned();
    (output.status.success(), text)
}

#[test]
fn policy_allows_agent_proposal_and_denies_other_roles() {
    assert!(probe("agent","pi","pi","Proposed","ProposeWork",None,false,false,false).0);
    assert!(!probe("verifier","reviewer","pi","Proposed","ProposeWork",None,false,false,false).0);
}

#[test]
fn approval_requires_proper_role_and_source_state() {
    assert!(probe("approver","human","pi","Proposed","Approve",Some("Approve"),false,false,false).0);
    assert!(!probe("agent","pi","pi","Proposed","Approve",Some("Approve"),false,false,false).0);
    assert!(!probe("approver","human","pi","Active","Approve",Some("Approve"),true,false,false).0);
}

#[test]
fn owner_and_valid_state_required_for_progression() {
    assert!(probe("agent","pi","pi","Approved","AdvanceWork",Some("Activate"),true,false,false).0);
    assert!(!probe("agent","muse","pi","Approved","AdvanceWork",Some("Activate"),true,false,false).0);
    assert!(!probe("agent","pi","pi","Approved","AdvanceWork",Some("Activate"),false,false,false).0);
    assert!(!probe("agent","pi","pi","Blocked","AdvanceWork",Some("Activate"),true,false,false).0);
    assert!(probe("agent","pi","pi","Blocked","AdvanceWork",Some("ResumeBlocked"),true,false,false).0);
}

#[test]
fn independent_verifier_cannot_skip_evidence_or_gate() {
    assert!(!probe("verifier","reviewer","pi","Active","VerifyAndClose",Some("Close"),true,false,false).0);
    assert!(!probe("verifier","reviewer","pi","Active","VerifyAndClose",Some("Close"),true,true,false).0);
    assert!(!probe("verifier","pi","pi","Active","VerifyAndClose",Some("Close"),true,true,true).0);
    assert!(!probe("agent","pi","pi","Active","VerifyAndClose",Some("Close"),true,true,true).0);
    let (allowed, reason)=probe("verifier","reviewer","pi","Active","VerifyAndClose",Some("Close"),true,true,true);
    assert!(allowed, "{reason}");
}

#[test]
fn verification_outcome_record_is_guarded_even_when_not_closed() {
    assert!(probe("verifier","reviewer","pi","Active","RecordVerification",
                  Some("RecordVerification"),true,true,false).0);
    assert!(!probe("agent","pi","pi","Active","RecordVerification",
                   Some("RecordVerification"),true,true,false).0);
    assert!(!probe("verifier","reviewer","pi","Active","RecordVerification",
                   Some("RecordVerification"),true,false,false).0);
}

#[test]
fn complete_and_invalid_model_actions_fail_closed() {
    assert!(!probe("agent","pi","pi","Completed","AdvanceWork",Some("Activate"),true,true,true).0);
    assert!(!probe("agent","pi","pi","Active","AdvanceWork",Some("Unknown"),true,false,false).0);
    assert!(!probe("approver","human","pi","Proposed","Approve",None,false,false,false).0);
    assert!(!probe("admin","human","pi","Proposed","Approve",Some("Approve"),false,false,false).0);
}

#[test]
fn malformed_json_is_rejected_without_panic() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_work_guard"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().expect("spawn");
    child.stdin.take().expect("stdin").write_all(b"{").expect("write");
    assert!(!child.wait_with_output().expect("finish").status.success());
}

#[test]
fn work_cedar_parses_using_temper_authz() {
    let engine = temper_authz::AuthzEngine::new(agent_work_reference::WORK_CEDAR);
    assert!(engine.is_ok(), "Cedar policy must load in Temper");
    assert!(engine.unwrap().policy_count() >= 5);
}
