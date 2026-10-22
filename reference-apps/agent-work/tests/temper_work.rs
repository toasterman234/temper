//! Temper-native state-machine verification for sandbox-only work pilot.
use std::sync::Arc;
use temper_jit::table::TransitionTable;
use temper_runtime::scheduler::{SimActorSystem, SimActorSystemConfig};
use temper_server::entity_actor::sim_handler::EntityActorHandler;
use temper_spec::csdl::parse_csdl;
use temper_verify::cascade::VerificationCascade;

const SPEC: &str = agent_work_reference::WORK_IOA;

fn simulation(seed: u64) -> SimActorSystem {
    let mut sim = SimActorSystem::new(SimActorSystemConfig {
        seed,
        ..Default::default()
    });
    let table = Arc::new(TransitionTable::from_ioa_source(SPEC));
    sim.register_actor(
        "work-1",
        Box::new(EntityActorHandler::new("WorkController", "work-1", table).with_ioa_invariants(SPEC)),
    );
    sim
}

#[test]
fn temper_cascade_checks_work_contract() {
    let report = VerificationCascade::from_ioa(SPEC)
        .with_sim_seeds(5)
        .with_prop_test_cases(100)
        .run();
    assert!(report.all_passed, "{report:#?}");
}

#[test]
fn model_rejects_false_completion_until_evidence_and_verification() {
    let mut sim = simulation(42);
    sim.assert_status("work-1", "Proposed");
    assert!(sim.step("work-1", "Close", "{}").is_err());
    assert!(sim.step("work-1", "Activate", "{}").is_err());
    sim.step("work-1", "Approve", "{}").unwrap();
    sim.step("work-1", "Activate", "{}").unwrap();
    assert!(sim.step("work-1", "Close", "{}").is_err());
    assert!(sim.step("work-1", "AcceptIndependentVerification", "{}").is_err());
    sim.step("work-1", "AttachEvidence", "{}").unwrap();
    assert!(sim.step("work-1", "Close", "{}").is_err());
    sim.step("work-1", "AcceptIndependentVerification", "{}").unwrap();
    sim.step("work-1", "Close", "{}").unwrap();
    sim.assert_status("work-1", "Completed");
    assert!(sim.step("work-1", "AttachEvidence", "{}").is_err());
    assert!(!sim.has_violations());
}

#[test]
fn model_resumes_blocked_work_by_legal_transition() {
    let mut sim = simulation(1);
    sim.step("work-1", "Approve", "{}").unwrap();
    sim.step("work-1", "Activate", "{}").unwrap();
    sim.step("work-1", "Block", "{}").unwrap();
    sim.assert_status("work-1", "Blocked");
    assert!(sim.step("work-1", "Close", "{}").is_err());
    sim.step("work-1", "ResumeBlocked", "{}").unwrap();
    sim.assert_status("work-1", "Active");
    assert!(!sim.has_violations());
}

#[test]
fn csdl_model_is_parseable() {
    let model = parse_csdl(agent_work_reference::MODEL_CSDL).expect("CSDL must parse");
    assert!(model.schemas.iter().any(|x| x.namespace == "Temper.AgentWork"));
}
