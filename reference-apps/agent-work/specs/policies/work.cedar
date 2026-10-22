// Proposed Temper Cedar policy. NOT loaded or enforced by the Python pilot.
// Caller identities and permissions must originate at a trusted effect boundary.
permit(
    principal is Agent,
    action in [Action::"InspectPortfolio", Action::"ProposeWork", Action::"AdvanceWork", Action::"AttachEvidence"],
    resource is WorkController
) when {
    resource.ownerRef == principal.id || action == Action::"InspectPortfolio" || action == Action::"ProposeWork"
};

permit(
    principal is Reviewer,
    action == Action::"Approve",
    resource is WorkController
) when { resource.status == "Proposed" };

permit(
    principal is Verifier,
    action == Action::"VerifyAndClose",
    resource is WorkController
) when {
    resource.status == "Active" && principal.id != resource.ownerRef
};

forbid(
    principal,
    action in [Action::"AdvanceWork", Action::"VerifyAndClose"],
    resource is WorkController
) when { resource.status == "Completed" || resource.status == "Rejected" };
