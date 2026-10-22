import hashlib, json, tempfile, threading, unittest, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sys import path as sys_path
import tomllib
ROOT=Path(__file__).resolve().parents[1]
sys_path.insert(0,str(ROOT))
from control import WorkControl, Denied
from api import credentials, handler_for
from http.server import ThreadingHTTPServer

DIGEST=hashlib.sha256(b"artifact").hexdigest()

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.file=str(Path(self.tmp.name)/"pilot.sqlite3")
        self.app=WorkControl(self.file)
    def tearDown(self):
        self.tmp.cleanup()
    def propose(self, **kwargs):
        data=dict(title="Stop false Done",intent_key="false-done",source_ref="issue:1",
                  parent_ref="project:governance",owner="pi",request_key="request:1")
        data.update(kwargs)
        return self.app.propose_work(**data)
    def active(self):
        p=self.propose()["work"]
        p=self.app.approve(work_id=p["id"],reviewer="human",expected_version=p["version"])
        return self.app.advance_work(work_id=p["id"],actor="pi",expected_version=p["version"],target="active",next_action="check state")

    def test_no_duplicate_under_concurrency(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            out=list(pool.map(lambda i:self.propose(request_key=f"request:{i}"),range(20)))
        self.assertEqual(len({x["work"]["id"] for x in out}),1)
        self.assertEqual(self.app.portfolio()["count"],1)
        self.assertEqual(self.propose()["disposition"],"REUSE_EXISTING")

    def test_conflicting_reuse_and_request_key_are_denied(self):
        self.propose()
        with self.assertRaises(Denied):self.propose(source_ref="issue:2",request_key="request:2")
        with self.assertRaises(Denied):self.propose(title="changed title")
        self.assertEqual(self.app.portfolio()["count"],1)

    def test_unapproved_or_unauthorized_cannot_advance(self):
        w=self.propose()["work"]
        with self.assertRaisesRegex(Denied,"approval"):
            self.app.advance_work(work_id=w["id"],actor="pi",expected_version=1,target="active",next_action="go")
        w=self.app.approve(work_id=w["id"],reviewer="human",expected_version=1)
        with self.assertRaisesRegex(Denied,"not awaiting approval"):
            self.app.approve(work_id=w["id"],reviewer="human",expected_version=w["version"])
        with self.assertRaisesRegex(Denied,"owner"):
            self.app.advance_work(work_id=w["id"],actor="muse",expected_version=w["version"],target="active",next_action="go")

    def test_versions_and_liveness_fields(self):
        w=self.active()
        with self.assertRaisesRegex(Denied,"stale"):
            self.app.advance_work(work_id=w["id"],actor="pi",expected_version=2,target="blocked",next_action="await",wake_condition="comment")
        with self.assertRaisesRegex(Denied,"wake_condition"):
            self.app.advance_work(work_id=w["id"],actor="pi",expected_version=w["version"],target="blocked",next_action="await")
        w=self.app.advance_work(work_id=w["id"],actor="pi",expected_version=w["version"],target="blocked",next_action="await",wake_condition="human comment")
        self.assertEqual(w["state"],"blocked")
        w=self.app.advance_work(work_id=w["id"],actor="pi",expected_version=w["version"],target="active",next_action="resume")
        self.assertEqual(w["state"],"active")

    def test_false_done_fails_until_fresh_independent_observation(self):
        w=self.active()
        evidence=self.app.add_evidence(work_id=w["id"],actor="pi",artifact_ref="git:abc",
            artifact_sha256=DIGEST,target_key="github:pr",expected_value="merged")
        self.assertFalse(self.app.verify_and_close(work_id=w["id"],verifier="reviewer",
            expected_version=w["version"],evidence_id=evidence["evidence_id"])["closed"])
        self.app.set_fixture_target("github:pr","draft")
        self.assertFalse(self.app.verify_and_close(work_id=w["id"],verifier="reviewer",
            expected_version=w["version"],evidence_id=evidence["evidence_id"])["closed"])
        self.app.set_fixture_target("github:pr","merged")
        with self.assertRaisesRegex(Denied,"independent verifier"):
            self.app.verify_and_close(work_id=w["id"],verifier="pi",expected_version=w["version"],evidence_id=evidence["evidence_id"])
        result=self.app.verify_and_close(work_id=w["id"],verifier="reviewer",expected_version=w["version"],evidence_id=evidence["evidence_id"])
        self.assertTrue(result["closed"])
        self.assertEqual(result["work"]["state"],"completed")
        with self.assertRaises(Denied):
            self.app.verify_and_close(work_id=w["id"],verifier="reviewer",expected_version=w["version"],evidence_id=evidence["evidence_id"])
        self.assertGreater(len(self.app.history(w["id"])),5)

    def test_restart_and_idempotent_replay(self):
        p=self.propose()["work"]
        again=WorkControl(self.file).propose_work(title="Stop false Done",intent_key="false-done",source_ref="issue:1",
            parent_ref="project:governance",owner="pi",request_key="request:1")
        self.assertEqual(p["id"],again["work"]["id"])
        self.assertEqual(WorkControl(self.file).portfolio()["count"],1)

    def test_native_spec_structure(self):
        t=tomllib.loads((ROOT/"specs/work.ioa.toml").read_text())
        self.assertEqual(t["automaton"]["name"],"WorkController")
        self.assertIn("independent_verification_passed",next(x["guard"] for x in t["action"] if x["name"]=="Close"))
        ET.parse(ROOT/"specs/model.csdl.xml")
        self.assertIn("principal is Verifier",(ROOT/"specs/policies/work.cedar").read_text())

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=WorkControl(str(Path(self.tmp.name)/"pilot.sqlite3"))
        self.tokens={"agent":"A"*32,"approver":"P"*32,"verifier":"V"*32}
        env={f"WORK_{k.upper()}_TOKEN":v for k,v in self.tokens.items()}
        env.update({"WORK_AGENT_ID":"pi","WORK_APPROVER_ID":"human","WORK_VERIFIER_ID":"reviewer"})
        self.http=ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.app,credentials(env)))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.host=f"http://127.0.0.1:{self.http.server_port}"
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join(timeout=5)
        self.tmp.cleanup()
    def call(self,path,role=None,body=None):
        headers={}
        if role:headers["Authorization"]="Bearer "+self.tokens[role]
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(self.host+path,headers=headers,data=data)
        try:
            with urllib.request.urlopen(req,timeout=5) as f:return f.status,json.load(f)
        except urllib.error.HTTPError as e:return e.code,json.load(e)

    def test_http_auth_approval_and_no_identity_spoof(self):
        self.assertEqual(self.call("/portfolio")[0],401)
        body={"title":"Agent work","intent_key":"i1","source_ref":"s1","parent_ref":"p1","request_key":"r1"}
        code,p=self.call("/propose_work",role="agent",body=body)
        self.assertEqual(code,200)
        self.assertEqual(p["work"]["owner"],"pi")
        self.assertEqual(self.call("/approve",role="agent",body={"work_id":p["work"]["id"],"expected_version":1})[0],403)
        self.assertEqual(self.call("/propose_work",role="agent",body={**body,"owner":"other"})[0],400)
        self.assertEqual(self.call("/fixture-target",role="verifier",body={"key":"s1","value":"done"})[0],404)
        self.assertEqual(self.app.portfolio()["count"],1)

    def test_http_verify_never_trusts_agent_claim(self):
        _,p=self.call("/propose_work",role="agent",body={"title":"Task","intent_key":"k","source_ref":"s","parent_ref":"p","request_key":"r"})
        w=p["work"]
        code,w=self.call("/approve",role="approver",body={"work_id":w["id"],"expected_version":w["version"]})
        self.assertEqual(code,200)
        code,w=self.call("/advance_work",role="agent",body={"work_id":w["id"],"expected_version":w["version"],"target":"active","next_action":"test"})
        self.assertEqual(code,200)
        code,e=self.call("/record_evidence",role="agent",body={"work_id":w["id"],"artifact_ref":"git:abc","artifact_sha256":DIGEST,"target_key":"repo:status","expected_value":"merged"})
        self.assertEqual(code,200)
        inp={"work_id":w["id"],"expected_version":w["version"],"evidence_id":e["evidence_id"]}
        self.assertEqual(self.call("/verify_and_close",role="agent",body=inp)[0],403)
        code,v=self.call("/verify_and_close",role="verifier",body=inp)
        self.assertEqual(code,200)
        self.assertFalse(v["closed"])
        self.assertEqual(self.app.portfolio()["work"][0]["state"],"active")

if __name__=="__main__":
    unittest.main()
