//! Temper reference specs for the sandbox-only agent-work prototype.
//! The Python HTTP gateway is an independent effect boundary; Cedar and IOA
//! are not yet connected to its authorization path or a canonical mutator.

pub const WORK_IOA: &str = include_str!("../specs/work.ioa.toml");
pub const MODEL_CSDL: &str = include_str!("../specs/model.csdl.xml");
pub const WORK_CEDAR: &str = include_str!("../specs/policies/work.cedar");
