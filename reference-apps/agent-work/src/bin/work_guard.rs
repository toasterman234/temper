//! Trusted local pilot decision gate: actual Temper Cedar + IOA checks.
//!
//! Input is JSON from the localhost HTTP gateway, never directly model-authored
//! authority. This process must return success before any governed SQLite write.
use std::collections::HashMap;
use std::io::{self, Read};

use serde::Deserialize;
use serde_json::json;
use temper_authz::{AuthzEngine, Principal, PrincipalKind, SecurityContext};
use temper_jit::{EvalContext, TransitionTable};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GateRequest {
    identity: String,
    role: String,
    owner_ref: String,
    status: String,
    action: String,
    model_action: Option<String>,
    approved: bool,
    evidence_present: bool,
    independent_verification_passed: bool,
}

fn decide(request: GateRequest) -> Result<(), String> {
    if request.identity.is_empty() || request.owner_ref.is_empty() {
        return Err("missing trusted identity/owner".into());
    }
    if !matches!(request.role.as_str(), "agent" | "approver" | "verifier") {
        return Err("unknown configured role".into());
    }
    if !matches!(
        request.status.as_str(),
        "Proposed" | "Approved" | "Active" | "Blocked" | "Awaiting" | "Completed" | "Rejected"
    ) {
        return Err("unknown modeled state".into());
    }

    let engine = AuthzEngine::new(agent_work_reference::WORK_CEDAR)
        .map_err(|_| "Cedar policy failed to load".to_string())?;
    let principal = Principal {
        id: request.identity,
        kind: PrincipalKind::Agent,
        role: Some(request.role),
        acting_for: None,
        agent_type: Some("agent-work-pilot".to_string()),
        attributes: HashMap::new(),
    };
    let context = SecurityContext {
        principal,
        context_attrs: HashMap::new(),
        correlation_id: "local-gate".to_string(),
    };
    let attrs = HashMap::from([
        ("id".to_string(), json!("work")),
        ("status".to_string(), json!(request.status)),
        ("ownerRef".to_string(), json!(request.owner_ref)),
    ]);
    if !engine
        .authorize(&context, &request.action, "WorkController", &attrs)
        .is_allowed()
    {
        return Err("Cedar denied actor/action/resource".into());
    }

    if let Some(model_action) = request.model_action {
        let model = TransitionTable::from_ioa_source(agent_work_reference::WORK_IOA);
        let mut vars = EvalContext::default();
        vars.booleans.insert("approved".into(), request.approved);
        vars.booleans
            .insert("evidence_present".into(), request.evidence_present);
        vars.booleans.insert(
            "independent_verification_passed".into(),
            request.independent_verification_passed,
        );
        if !model
            .evaluate_ctx(&request.status, &vars, &model_action)
            .is_some_and(|result| result.success)
        {
            return Err("Temper state-machine transition denied".into());
        }
    } else if request.action != "ProposeWork" {
        return Err("missing state-machine action".into());
    }
    Ok(())
}

fn main() {
    let result: Result<(), String> = (|| {
        let mut input = String::new();
        io::stdin()
            .take(8193)
            .read_to_string(&mut input)
            .map_err(|_| "could not read request".to_string())?;
        if input.len() > 8192 {
            return Err("oversized request".into());
        }
        let request: GateRequest = serde_json::from_str(&input)
            .map_err(|_| "malformed trusted request".to_string())?;
        decide(request)
    })();
    match result {
        Ok(()) => println!("{}", json!({"allowed": true})),
        Err(reason) => {
            eprintln!("{}", json!({"allowed": false, "reason": reason}));
            std::process::exit(2);
        }
    }
}
