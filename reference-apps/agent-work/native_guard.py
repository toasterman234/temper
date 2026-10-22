"""Fail-closed bridge to the Temper Rust Cedar + IOA guard.

All identities and resource facts passed here must be resolved by the trusted
gateway and current DB transaction, never from caller-supplied JSON.
"""
import json
import os
import subprocess
from pathlib import Path
from control import Denied


class NativeGate:
    def __init__(self, executable):
        self.executable = str(Path(executable).resolve())
        if not Path(self.executable).is_file() or not os.access(self.executable, os.X_OK):
            raise RuntimeError("WORK_GUARD_BIN must name an executable compiled Temper work_guard")

    def check(self, *, role, identity, owner_ref, status, action,
              model_action=None, approved=False, evidence_present=False,
              independent_verification_passed=False):
        request = dict(
            role=role,
            identity=identity,
            owner_ref=owner_ref,
            status=status,
            action=action,
            model_action=model_action,
            approved=bool(approved),
            evidence_present=bool(evidence_present),
            independent_verification_passed=bool(independent_verification_passed),
        )
        try:
            process = subprocess.run(
                [self.executable],
                input=json.dumps(request), text=True, capture_output=True,
                timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise Denied("Temper guard unavailable; fail-closed", 503)
        if process.returncode != 0:
            raise Denied("Temper Cedar/IOA authorization denied", 403)
        try:
            response = json.loads(process.stdout)
        except json.JSONDecodeError:
            raise Denied("Temper guard returned invalid output", 503)
        if response != {"allowed": True}:
            raise Denied("Temper guard returned non-allow", 403)
