"""Local authenticated HTTP gateway for isolated agent-work pilot. Not a production policy engine."""
from __future__ import annotations
import argparse
import hmac
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from control import Denied, WorkControl
from github_source import GitHubSource
from native_guard import NativeGate

def credentials(env: dict[str, str]) -> dict[str, tuple[str, str]]:
    items = [(name, env.get(f"WORK_{name.upper()}_TOKEN", ""), env.get(f"WORK_{name.upper()}_ID", name))
             for name in ("agent", "approver", "verifier")]
    if any(len(token) < 24 for _, token, _ in items) or len({t for _, t, _ in items}) != 3:
        raise RuntimeError("Set three distinct WORK_AGENT_TOKEN, WORK_APPROVER_TOKEN and WORK_VERIFIER_TOKEN (24+ characters each)")
    return {name: (token, identity) for name, token, identity in items}

def verify_network_and_storage(*, args, env, identities):
    """Refuse a public bind or Northflank boot without durable storage and secrets.

    Northflank terminates HTTPS at ingress; this container only serves HTTP
    inside its network. Do not publish its container port directly on the host.
    """
    mode = env.get("WORK_DEPLOYMENT_MODE", "")
    if mode not in ("", "northflank"):
        raise RuntimeError("Unsupported WORK_DEPLOYMENT_MODE")
    if mode != "northflank":
        if args.bind not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError("Outside Northflank the pilot must bind localhost")
        return
    if args.bind != "0.0.0.0":
        raise RuntimeError("Northflank mode must bind 0.0.0.0 (behind its ingress)")
    if args.port != 8765:
        raise RuntimeError("Northflank mode requires container HTTP port 8765")
    db_path = Path(args.db).resolve()
    if db_path.parent != Path("/data"):
        raise RuntimeError("Northflank SQLite WORK_DB must be directly under /data")
    if not os.path.ismount("/data"):
        raise RuntimeError("Northflank requires a persistent volume mounted at /data")
    if not os.access("/data", os.W_OK):
        raise RuntimeError("Northflank /data volume is not writable by the app user")
    if any(len(token) < 32 for token, _ in identities.values()):
        raise RuntimeError("Northflank role tokens must each be at least 32 characters")
    if len({identity for _, identity in identities.values()}) != 3:
        raise RuntimeError("Northflank agent/approver/verifier IDs must be distinct")
    if not env.get("WORK_GITHUB_REPOS"):
        raise RuntimeError("Set WORK_GITHUB_REPOS in Northflank")
    if not env.get("WORK_GITHUB_READ_TOKEN"):
        raise RuntimeError("Set WORK_GITHUB_READ_TOKEN in Northflank secrets")


def handler_for(control: WorkControl, auth: dict[str, tuple[str, str]]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentWorkPilot/0.1"
        def log_message(self, format, *args):
            return  # do not log bearer headers or work descriptions

        def respond(self, code, body):
            value=json.dumps(body, sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(value)))
            self.end_headers()
            self.wfile.write(value)

        def authenticate(self):
            bearer=self.headers.get("Authorization", "")
            for name, (token, identity) in auth.items():
                if hmac.compare_digest(bearer, "Bearer " + token):
                    return name, identity
            raise Denied("unauthorized", 401)

        def do_GET(self):
            try:
                if self.path == "/healthz":
                    try:
                        with control.connect() as db:
                            db.execute("SELECT 1").fetchone()
                    except (sqlite3.Error, OSError):
                        return self.respond(503, {"ok": False})
                    return self.respond(200, {"ok": True, "scope": "agent-work-pilot"})
                self.authenticate()
                if self.path == "/portfolio":
                    return self.respond(200, control.portfolio())
                if self.path == "/github/portfolio":
                    if control.github is None:
                        raise Denied("GitHub not configured",503)
                    return self.respond(200, control.github.portfolio())
                if self.path.startswith("/github/related?"):
                    if control.github is None:
                        raise Denied("GitHub not configured",503)
                    params=parse_qs(urlsplit(self.path).query)
                    if set(params)!={"title"} or len(params["title"])!=1:
                        raise Denied("expected one title parameter",400)
                    return self.respond(200,control.github.related(params["title"][0]))
                if self.path.startswith("/github/source?"):
                    if control.github is None:
                        raise Denied("GitHub not configured",503)
                    params=parse_qs(urlsplit(self.path).query)
                    if set(params)!={"ref"} or len(params["ref"])!=1:
                        raise Denied("expected one ref parameter",400)
                    source=control.github.source(params["ref"][0])
                    if source is None:
                        raise Denied("not a GitHub source",400)
                    return self.respond(200, {"source":source,"observed_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
                if self.path.startswith("/history/"):
                    return self.respond(200, {"events": control.history(self.path.removeprefix("/history/"))})
                raise Denied("unknown endpoint",404)
            except Denied as error:
                self.respond(error.status,{"error":error.reason})

        def do_POST(self):
            role = identity = None
            payload = None
            try:
                role, identity=self.authenticate()
                n=self.headers.get("Content-Length", "")
                if not n.isdigit() or int(n)>16384 or int(n)==0:
                    raise Denied("invalid Content-Length",400)
                try:
                    payload=json.loads(self.rfile.read(int(n)))
                except (UnicodeDecodeError,json.JSONDecodeError):
                    raise Denied("invalid JSON",400)
                if not isinstance(payload,dict):raise Denied("expected JSON object",400)
                routes={
                    "/propose_work":("agent",{"title","intent_key","source_ref","parent_ref","request_key"},set()),
                    "/approve":("approver",{"work_id","expected_version"},set()),
                    "/advance_work":("agent",{"work_id","expected_version","target","next_action"},{"wake_condition"}),
                    "/record_evidence":("agent",{"work_id","artifact_ref","artifact_sha256","target_key","expected_value"},set()),
                    "/verify_and_close":("verifier",{"work_id","expected_version","evidence_id"},set()),
                }
                if self.path not in routes:raise Denied("unknown endpoint",404)
                required_role,required,optional=routes[self.path]
                if role != required_role:raise Denied("insufficient role",403)
                if not required.issubset(payload) or set(payload) - required - optional:
                    raise Denied("missing or unexpected fields",400)
                if self.path=="/propose_work":
                    result=control.propose_work(**payload,owner=identity)
                elif self.path=="/approve":
                    result=control.approve(**payload,reviewer=identity)
                elif self.path=="/advance_work":
                    result=control.advance_work(**payload,actor=identity)
                elif self.path=="/record_evidence":
                    result=control.add_evidence(**payload,actor=identity)
                else:
                    result=control.verify_and_close(**payload,verifier=identity)
                self.respond(200,result)
            except Denied as error:
                if identity is not None:
                    control.record_denial(payload.get("work_id") if isinstance(payload, dict) else None, identity, self.path, error.reason)
                self.respond(error.status,{"error":error.reason})
            except (TypeError,ValueError,OverflowError):
                self.respond(400,{"error":"invalid field type"})
    return Handler

def main():
    parser=argparse.ArgumentParser(description="Isolated agent-work pilot; does not mutate canonical records")
    parser.add_argument("command",choices=("serve","fixture-target"))
    parser.add_argument("--db",default=os.getenv("WORK_DB",str(Path.home()/".agent-work-pilot.sqlite3")))
    parser.add_argument("--bind",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--key")
    parser.add_argument("--value")
    args=parser.parse_args()
    if args.command=="serve":
        auth=credentials(os.environ)
        verify_network_and_storage(args=args, env=os.environ, identities=auth)
    control=WorkControl(args.db)
    if args.command=="fixture-target":
        if args.key is None or args.value is None:parser.error("fixture-target requires --key and --value")
        if args.key.startswith("github:"):
            parser.error("fixture setter cannot spoof GitHub source observations")
        control.set_fixture_target(args.key,args.value)
        print(json.dumps({"fixture_target":args.key,"value":args.value,"scope":"local-only"}))
        return
    # A running HTTP server always requires the compiled Temper gate.
    # Deliberately no permissive fallback: startup fails when missing.
    control.gate=NativeGate(os.environ.get("WORK_GUARD_BIN",""))
    if os.environ.get("WORK_GITHUB_REPOS"):
        control.github=GitHubSource(
            os.environ["WORK_GITHUB_REPOS"],
            token=os.environ.get("WORK_GITHUB_READ_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN",""))
    ThreadingHTTPServer((args.bind,args.port),handler_for(control,auth)).serve_forever()

if __name__=="__main__":
    main()
