"""Isolated agent-work pilot. NOT an adapter to canonical state or the Temper runtime."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

class Denied(Exception):
    def __init__(self, reason: str, status: int = 409):
        self.reason, self.status = reason, status
        super().__init__(reason)

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def require(value, name, limit=2048):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Denied(f"invalid {name}", 400)
    return value.strip()

def obj(row):
    return dict(row) if row else None

SCHEMA = """
CREATE TABLE IF NOT EXISTS work (
  id TEXT PRIMARY KEY, intent_key TEXT NOT NULL UNIQUE, source_ref TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL, parent_ref TEXT NOT NULL, state TEXT NOT NULL,
  owner TEXT NOT NULL, next_action TEXT NOT NULL, wake_condition TEXT,
  version INTEGER NOT NULL DEFAULT 1, approval_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
  request_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, work_id TEXT NOT NULL REFERENCES work(id)
);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES work(id), reviewer TEXT NOT NULL,
  outcome TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES work(id), artifact_ref TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL, target_key TEXT NOT NULL, expected_value TEXT NOT NULL,
  submitted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixture_targets (
  target_key TEXT PRIMARY KEY, observed_value TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verifications (
  id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES work(id), evidence_id TEXT NOT NULL REFERENCES evidence(id),
  verifier TEXT NOT NULL, verdict TEXT NOT NULL, observed_value TEXT, checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, work_id TEXT, operation TEXT NOT NULL,
  actor TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL, recorded_at TEXT NOT NULL
);
"""

class WorkControl:
    def __init__(self, file: str | Path):
        self.file = str(file)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.file, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except Exception:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def record(db, work_id, operation, actor, outcome, detail):
        db.execute("INSERT INTO events(work_id,operation,actor,outcome,detail,recorded_at) VALUES(?,?,?,?,?,?)",
                   (work_id, operation, actor, outcome, json.dumps(detail, sort_keys=True), now()))

    @staticmethod
    def get(db, work_id):
        require(work_id, "work_id")
        row = db.execute("SELECT * FROM work WHERE id=?", (work_id,)).fetchone()
        if row is None:
            raise Denied("work not found", 404)
        return row

    @staticmethod
    def check_version(row, version):
        if not isinstance(version, int) or type(version) is bool or version != row["version"]:
            raise Denied("stale expected_version")

    def portfolio(self):
        with self.connect() as db:
            works = [obj(x) for x in db.execute("SELECT * FROM work ORDER BY updated_at DESC,id")]
            for w in works:
                w["events"] = db.execute("SELECT COUNT(*) FROM events WHERE work_id=?", (w["id"],)).fetchone()[0]
            return {"count": len(works), "work": works, "warning": "local pilot state, not canonical or live GitHub"}

    def propose_work(self, *, title, intent_key, source_ref, parent_ref, owner, request_key):
        payload = {k: require(v, k) for k, v in locals().copy().items() if k != "self"}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.connect(write=True) as db:
            old_request = db.execute("SELECT * FROM requests WHERE request_key=?", (payload["request_key"],)).fetchone()
            if old_request:
                if old_request["fingerprint"] != fingerprint:
                    raise Denied("request_key reused with different intent")
                return {"disposition": "REUSE_EXISTING", "work": obj(self.get(db, old_request["work_id"]))}
            existing = db.execute("SELECT * FROM work WHERE intent_key=? OR source_ref=?",
                                  (payload["intent_key"], payload["source_ref"])).fetchone()
            if existing:
                if existing["intent_key"] != payload["intent_key"] or existing["source_ref"] != payload["source_ref"]:
                    raise Denied("source/intent identity conflict: human review needed")
                db.execute("INSERT INTO requests VALUES(?,?,?)", (payload["request_key"], fingerprint, existing["id"]))
                self.record(db, existing["id"], "propose", payload["owner"], "reuse", {"request_key": payload["request_key"]})
                return {"disposition": "REUSE_EXISTING", "work": obj(existing)}
            work_id = str(uuid.uuid4())
            stamp = now()
            db.execute("""INSERT INTO work(id,intent_key,source_ref,title,parent_ref,state,owner,next_action,created_at,updated_at)
                          VALUES(?,?,?,?,?,'proposed',?,'review proposal',?,?)""",
                       (work_id,payload["intent_key"],payload["source_ref"],payload["title"],payload["parent_ref"],payload["owner"],stamp,stamp))
            db.execute("INSERT INTO requests VALUES(?,?,?)", (payload["request_key"], fingerprint, work_id))
            self.record(db,work_id,"propose",payload["owner"],"created",payload)
            return {"disposition": "NEW_PROPOSAL", "work": obj(self.get(db,work_id))}

    def approve(self, *, work_id, reviewer, expected_version):
        reviewer = require(reviewer,"reviewer")
        with self.connect(write=True) as db:
            w=self.get(db,work_id);self.check_version(w,expected_version)
            if w["state"]!="proposed" or w["approval_id"]:raise Denied("work is not awaiting approval")
            decision_id=str(uuid.uuid4())
            db.execute("INSERT INTO decisions VALUES(?,?,?,?,?)",(decision_id,work_id,reviewer,"accepted",now()))
            db.execute("UPDATE work SET approval_id=?,version=version+1,updated_at=? WHERE id=?",(decision_id,now(),work_id))
            self.record(db,work_id,"approve",reviewer,"accepted",{"decision":decision_id})
            return obj(self.get(db,work_id))

    def advance_work(self, *, work_id, actor, expected_version, target, next_action, wake_condition=None):
        actor=require(actor,"actor");next_action=require(next_action,"next_action")
        if target not in {"active","blocked","awaiting"}:raise Denied("unsupported transition",400)
        if target in {"blocked","awaiting"}:require(wake_condition,"wake_condition")
        with self.connect(write=True) as db:
            w=self.get(db,work_id);self.check_version(w,expected_version)
            if w["owner"]!=actor:raise Denied("actor is not assigned owner",403)
            if w["approval_id"] is None:raise Denied("accepted approval required")
            allowed={"proposed":{"active"},"active":{"blocked","awaiting"},"blocked":{"active"},"awaiting":{"active"}}
            if target not in allowed.get(w["state"],set()):raise Denied("illegal state transition")
            db.execute("UPDATE work SET state=?,next_action=?,wake_condition=?,version=version+1,updated_at=? WHERE id=?",
                       (target,next_action,wake_condition,now(),work_id))
            self.record(db,work_id,"advance",actor,"accepted",{"from":w["state"],"to":target,"next_action":next_action,"wake_condition":wake_condition})
            return obj(self.get(db,work_id))

    def add_evidence(self, *, work_id, actor, artifact_ref, artifact_sha256, target_key, expected_value):
        actor=require(actor,"actor");artifact_ref=require(artifact_ref,"artifact_ref")
        target_key=require(target_key,"target_key");expected_value=require(expected_value,"expected_value")
        if not isinstance(artifact_sha256,str) or len(artifact_sha256)!=64 or any(c not in "0123456789abcdef" for c in artifact_sha256):
            raise Denied("artifact_sha256 must be 64 lowercase hex digits",400)
        with self.connect(write=True) as db:
            w=self.get(db,work_id)
            if w["owner"]!=actor:raise Denied("actor is not assigned owner",403)
            if w["state"]!="active":raise Denied("work not active")
            ev_id=str(uuid.uuid4())
            db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",(ev_id,work_id,artifact_ref,artifact_sha256,target_key,expected_value,now()))
            self.record(db,work_id,"evidence",actor,"submitted",{"evidence":ev_id,"artifact_ref":artifact_ref})
            return {"evidence_id":ev_id,"verified":False}

    def verify_and_close(self, *, work_id, verifier, expected_version, evidence_id):
        verifier=require(verifier,"verifier")
        with self.connect(write=True) as db:
            w=self.get(db,work_id);self.check_version(w,expected_version)
            if w["state"]!="active":raise Denied("work must be active")
            if verifier==w["owner"]:raise Denied("independent verifier required",403)
            ev=db.execute("SELECT * FROM evidence WHERE id=? AND work_id=?",(evidence_id,work_id)).fetchone()
            if ev is None:raise Denied("evidence missing or unrelated")
            target=db.execute("SELECT * FROM fixture_targets WHERE target_key=?",(ev["target_key"],)).fetchone()
            valid=bool(target and target["observed_value"]==ev["expected_value"] and target["observed_at"]>=ev["submitted_at"])
            verification_id=str(uuid.uuid4())
            db.execute("INSERT INTO verifications VALUES(?,?,?,?,?,?,?)",(verification_id,work_id,evidence_id,verifier,"passed" if valid else "failed",target["observed_value"] if target else None,now()))
            self.record(db,work_id,"verify",verifier,"passed" if valid else "failed",{"verification":verification_id,"evidence":evidence_id})
            if not valid:
                return {"closed":False,"reason":"no matching fresh independent fixture observation","verification_id":verification_id,"work":obj(w)}
            db.execute("UPDATE work SET state='completed',next_action='none',wake_condition=NULL,version=version+1,updated_at=? WHERE id=?",(now(),work_id))
            self.record(db,work_id,"close",verifier,"verified",{"verification":verification_id})
            return {"closed":True,"verification_id":verification_id,"work":obj(self.get(db,work_id))}

    def set_fixture_target(self, key, value):
        # Test adapter only. NEVER exposed over the HTTP server.
        key=require(key,"target_key");value=require(value,"target_value")
        with self.connect(write=True) as db:
            db.execute("INSERT INTO fixture_targets VALUES(?,?,?) ON CONFLICT(target_key) DO UPDATE SET observed_value=excluded.observed_value, observed_at=excluded.observed_at",(key,value,now()))

    def record_denial(self, work_id, actor, operation, reason):
        with self.connect(write=True) as db:
            if isinstance(work_id, str) and db.execute("SELECT 1 FROM work WHERE id=?", (work_id,)).fetchone():
                self.record(db, work_id, operation, actor, "denied", {"reason":reason})

    def history(self, work_id):
        with self.connect() as db:
            self.get(db,work_id)
            return [obj(x) for x in db.execute("SELECT * FROM events WHERE work_id=? ORDER BY seq",(work_id,))]
