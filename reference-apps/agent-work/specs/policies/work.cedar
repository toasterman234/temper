// Active policy for agent-work pilot's native Temper guard.
// All principal IDs and roles originate from configured HTTP bearer credentials.
// There is NO wide admin permit, implicit auto-approval, or direct API bypass.
// External GitHub/agent/production operations are out of scope.
permit(
    principal is Agent,
    action == Action::"ProposeWork",
    resource is WorkController
) when { principal.role == "agent" };

permit(
    principal is Agent,
    action == Action::"Approve",
    resource is WorkController
) when {
    principal.role == "approver" &&
    resource.status == "Proposed"
};

permit(
    principal is Agent,
    action == Action::"AdvanceWork",
    resource is WorkController
) when {
    principal.role == "agent" &&
    resource.ownerRef == principal.id &&
    (
        resource.status == "Approved" ||
        resource.status == "Active" ||
        resource.status == "Blocked" ||
        resource.status == "Awaiting"
    )
};

permit(
    principal is Agent,
    action == Action::"AttachEvidence",
    resource is WorkController
) when {
    principal.role == "agent" &&
    resource.ownerRef == principal.id &&
    resource.status == "Active"
};

permit(
    principal is Agent,
    action in [Action::"RecordVerification", Action::"VerifyAndClose"],
    resource is WorkController
) when {
    principal.role == "verifier" &&
    principal.id != resource.ownerRef &&
    resource.status == "Active"
};

// Forged/unsupported transition destinations are separately rejected by the
// Temper IOA table. This policy alone does NOT validate a real target's state.
