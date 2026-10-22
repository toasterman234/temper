"""GitHub integration tests use a deterministic fake transport. Live reads run in CI separately."""
import os
import json
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import quote
from threading import Thread
from http.server import ThreadingHTTPServer

from api import credentials, handler_for
from control import WorkControl, Denied
from github_source import GitHubSource, repository_list
from native_guard import NativeGate

REPO = "toasterman234/master-repo-0.1"


class FakeGitHub:
    def __init__(self):
        self.issue_status="open"
        self.pr_status="open"
        self.pr_merged=False
        self.calls=[]
    def __call__(self, repo, endpoint, params=None):
        self.calls.append((repo,endpoint,params))
        if repo!=REPO: raise AssertionError("unconfigured repo escaped allowlist")
        issue={
            "number":76,"title":"Agent task sprawl and evidence checks",
            "state":self.issue_status,"updated_at":"2026-10-21T12:00:00Z",
            "created_at":"2026-10-15T12:00:00Z","closed_at":None,
            "html_url":f"https://github.com/{REPO}/issues/76",
            "assignee":{"login":"maintainer"},"labels":[{"name":"governance"}],
        }
        pr={
            "number":358,"title":"Agent closure and verification controls",
            "state":self.pr_status,"merged":self.pr_merged,
            "merged_at":"2026-10-22T04:00:00Z" if self.pr_merged else None,
            "draft":False,"updated_at":"2026-10-21T15:00:00Z",
            "created_at":"2026-10-19T12:00:00Z","closed_at":None,
            "html_url":f"https://github.com/{REPO}/pull/358",
            "assignee":None,
        }
        if endpoint=="issues/76":return issue
        if endpoint=="pulls/358":return pr
        if endpoint=="issues":return [issue,{**pr,"pull_request":{"url":"api.github.com/pr"}}]
        if endpoint=="pulls":return [pr]
        raise Denied("GitHub resource not found",404)


class GitHubSourceTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeGitHub()
        self.github=GitHubSource(REPO, get_json=self.fake)
        self.tmp=tempfile.TemporaryDirectory()
        guard=NativeGate(os.environ["WORK_GUARD_BIN"]) if os.getenv("WORK_GUARD_BIN") else None
        self.app=WorkControl(Path(self.tmp.name)/"work.sqlite3",gate=guard,github=self.github)
    def tearDown(self):self.tmp.cleanup()
    def test_allowlist_and_live_source_refs(self):
        self.assertEqual(repository_list(REPO+","+REPO),(REPO,))
        self.assertEqual(self.github.source(f"github:{REPO}/issues/76")["state"],"open")
        self.assertEqual(self.github.source(f"github:{REPO}/pulls/358")["kind"],"pull_request")
        with self.assertRaises(Denied):self.github.source("github:someone/other/issues/1")
        with self.assertRaises(Denied):self.github.source(f"github:{REPO}/issues/77")
        with self.assertRaises(Denied):self.github.source(f"github:{REPO}/issues/../76")
    def test_real_source_is_reused_without_local_duplicate(self):
        result=self.app.propose_work(
            title="Improve agent evidence",intent_key="evidence",source_ref=f"github:{REPO}/issues/76",
            parent_ref="project:gov",owner="agent",request_key="demo:1")
        self.assertEqual(result["disposition"],"EXISTING_GITHUB")
        self.assertIsNone(result["work"])
        self.assertEqual(self.app.portfolio()["count"],0)
    def test_portfolio_and_related_candidates_only(self):
        portfolio=self.github.portfolio()
        self.assertEqual(portfolio["count"],2)
        self.assertTrue(portfolio["incomplete"])
        self.assertEqual({x["kind"] for x in portfolio["items"]},{"issue","pull_request"})
        matches=self.github.related("Agent task sprawl and evidence checks")
        self.assertTrue(matches["candidates"])
        self.assertEqual(matches["candidates"][0]["disposition"],"REVIEW_SIMILARITY_ONLY")
        self.assertEqual(self.app.portfolio()["count"],0)
    def test_github_independent_readback_denies_false_done(self):
        w=self.app.propose_work(title="Evidence",intent_key="abc",
            source_ref="local:demo",parent_ref="local:project",owner="agent",
            request_key="demo:2")["work"]
        w=self.app.approve(work_id=w["id"],reviewer="human",expected_version=w["version"])
        w=self.app.advance_work(work_id=w["id"],actor="agent",expected_version=w["version"],
                                target="active",next_action="verify GitHub")
        ev=self.app.add_evidence(work_id=w["id"],actor="agent",artifact_ref=f"https://github.com/{REPO}/pull/358",
                 artifact_sha256="a"*64,target_key=f"github:{REPO}/pulls/358",expected_value="merged")
        bad=self.app.verify_and_close(work_id=w["id"],verifier="verifier",
                            expected_version=w["version"],evidence_id=ev["evidence_id"])
        self.assertFalse(bad["closed"])
        self.assertEqual(self.app.portfolio()["work"][0]["state"],"active")
        self.fake.pr_merged=True
        self.fake.pr_status="closed"
        good=self.app.verify_and_close(work_id=w["id"],verifier="verifier",
                             expected_version=w["version"],evidence_id=ev["evidence_id"])
        self.assertTrue(good["closed"])
        self.assertEqual(good["work"]["state"],"completed")
        self.assertTrue(any(evt["operation"]=="close" for evt in self.app.history(w["id"])))
    def test_unavailable_github_cannot_be_faked_with_fixture(self):
        self.app.github=None
        with self.assertRaisesRegex(Denied,"unavailable"):
            self.app.propose_work(title="X",intent_key="X",source_ref=f"github:{REPO}/issues/76",
                                  parent_ref="p",owner="agent",request_key="x")
        self.assertEqual(self.app.portfolio()["count"],0)


class GitHubHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.fake=FakeGitHub()
        self.github=GitHubSource(REPO,get_json=self.fake)
        db=WorkControl(Path(self.tmp.name)/"db.sqlite3",github=self.github)
        tokens={"agent":"A"*32,"approver":"P"*32,"verifier":"V"*32}
        self.tokens=tokens
        creds=credentials({
            "WORK_AGENT_TOKEN":tokens["agent"],"WORK_AGENT_ID":"agent",
            "WORK_APPROVER_TOKEN":tokens["approver"],"WORK_APPROVER_ID":"human",
            "WORK_VERIFIER_TOKEN":tokens["verifier"],"WORK_VERIFIER_ID":"verifier",
        })
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(db,creds))
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.thread.join(timeout=5);self.tmp.cleanup()
    def req(self,path,role=None):
        h={"Authorization":"Bearer "+self.tokens[role]} if role else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url+path,headers=h),timeout=4) as resp:
                return resp.status,json.load(resp)
        except urllib.error.HTTPError as err:
            return err.code,json.load(err)
    def test_github_routes_need_auth_and_are_read_only(self):
        self.assertEqual(self.req("/github/portfolio")[0],401)
        code,res=self.req("/github/portfolio","agent")
        self.assertEqual(code,200)
        self.assertEqual(res["count"],2)
        ref=quote(f"github:{REPO}/issues/76",safe="")
        code,res=self.req("/github/source?ref="+ref,"agent")
        self.assertEqual(code,200)
        self.assertEqual(res["source"]["number"],76)
        code,res=self.req("/github/related?title=agent%20task%20sprawl","agent")
        self.assertEqual(code,200)
        self.assertTrue(res["candidates"])

if __name__=="__main__":unittest.main()
