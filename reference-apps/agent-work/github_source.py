"""Bounded, read-only GitHub REST source for agent-work pilot.

The connector never obtains token material from the HTTP caller and never
performs a GitHub mutation. Only configured repositories may be queried.
"""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from control import Denied

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
SOURCE_PATTERN = re.compile(
    r"^github:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/(issues|pulls)/([1-9][0-9]{0,9})$"
)
ITEM_LIMIT = 40


def repository_list(value: str):
    repos = []
    for raw in value.split(","):
        name = raw.strip()
        if not REPO_PATTERN.fullmatch(name):
            raise ValueError("WORK_GITHUB_REPOS must be comma-separated owner/repo names")
        if name.lower() not in {x.lower() for x in repos}:
            repos.append(name)
    if not repos or len(repos) > 5:
        raise ValueError("configure 1-5 GitHub repositories")
    return tuple(repos)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class GitHubSource:
    def __init__(self, repos, token="", get_json=None):
        self.repos = repository_list(repos) if isinstance(repos, str) else tuple(repos)
        if not self.repos or len(self.repos)>5 or any(not REPO_PATTERN.fullmatch(x) for x in self.repos):
            raise ValueError("invalid repository allowlist")
        self.token = token or ""
        self._get_json = get_json or self._http_json

    def configured(self, repo):
        if not isinstance(repo, str):
            raise Denied("invalid GitHub repo", 400)
        matches = [x for x in self.repos if x.lower()==repo.lower()]
        if not matches:
            raise Denied("repository outside configured GitHub scope", 403)
        return matches[0]

    def _http_json(self, repo, endpoint, params=None):
        # repo is checked against allowlist in get(); endpoint is constructed
        # only inside this module from fixed names and numeric IDs.
        url = f"https://api.github.com/repos/{repo}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "temper-agent-work-readonly/0.1",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                raw = response.read(512_001)
                if len(raw)>512_000:
                    raise Denied("GitHub response too large", 502)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 410 and endpoint == "issues":
                # Some repos (including this fork) have Issues disabled.
                return {"issues_disabled":True}
            if e.code == 404: raise Denied("GitHub resource not found or inaccessible", 404)
            if e.code in (401, 403): raise Denied("GitHub permission or rate-limit denied", 503)
            raise Denied(f"GitHub API returned HTTP {e.code}", 502)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError):
            raise Denied("GitHub read unavailable or malformed", 503)

    def get(self, repo, endpoint, params=None):
        return self._get_json(self.configured(repo), endpoint, params)

    @staticmethod
    def normalize_issue(repo, item):
        if not isinstance(item, dict) or not isinstance(item.get("number"),int):
            raise Denied("invalid GitHub issue payload",502)
        no=item["number"]
        is_pr=bool(item.get("pull_request"))
        return {
            "source_ref": f"github:{repo}/{'pulls' if is_pr else 'issues'}/{no}",
            "kind": "pull_request" if is_pr else "issue",
            "repo": repo, "number":no,
            "title": item.get("title"), "state":item.get("state"),
            "updated_at":item.get("updated_at"), "created_at":item.get("created_at"),
            "closed_at":item.get("closed_at"), "url":item.get("html_url"),
            "assignee": (item.get("assignee") or {}).get("login"),
            "labels": [i.get("name") for i in item.get("labels",[]) if isinstance(i,dict)][:20],
        }

    def issue(self,repo,number):
        repo=self.configured(repo)
        if not isinstance(number,int) or not (1<=number<=9999999999):
            raise Denied("invalid issue number",400)
        item=self.get(repo,f"issues/{number}")
        return self.normalize_issue(repo,item)

    def pull(self,repo,number):
        repo=self.configured(repo)
        if not isinstance(number,int) or not (1<=number<=9999999999):
            raise Denied("invalid PR number",400)
        item=self.get(repo,f"pulls/{number}")
        return {
            "source_ref":f"github:{repo}/pulls/{number}",
            "kind":"pull_request", "repo":repo,"number":number,
            "title":item.get("title"), "state":item.get("state"),
            "merged":bool(item.get("merged")), "draft":bool(item.get("draft")),
            "updated_at":item.get("updated_at"),"created_at":item.get("created_at"),
            "closed_at":item.get("closed_at"),"merged_at":item.get("merged_at"),
            "url":item.get("html_url"),
            "assignee":(item.get("assignee") or {}).get("login"),
        }

    def source(self,ref):
        if not isinstance(ref,str): return None
        match=SOURCE_PATTERN.fullmatch(ref)
        if not match:
            if ref.startswith("github:"):
                raise Denied("invalid GitHub source_ref; use github:owner/repo/issues/123 or /pulls/123",400)
            return None
        repo,kind,num=match.groups()
        repo=self.configured(repo)
        observed = self.issue(repo,int(num)) if kind=="issues" else self.pull(repo,int(num))
        if observed["kind"] != ("issue" if kind=="issues" else "pull_request"):
            raise Denied("GitHub source kind mismatch; issue endpoint refers to a pull request",400)
        return observed

    def portfolio(self):
        data=[]
        limitations=[]
        for repo in self.repos:
            # GitHub issues endpoint also returns PRs. De-duplicate those
            # against the dedicated PR endpoint by source_ref.
            issues=self.get(repo,"issues",{"state":"all","per_page":ITEM_LIMIT,"page":1})
            pulls=self.get(repo,"pulls",{"state":"all","per_page":ITEM_LIMIT,"page":1})
            if isinstance(issues,dict) and issues.get("issues_disabled") is True:
                limitations.append(f"{repo}: Issues disabled; only pull requests checked")
                issues=[]
            if not isinstance(issues,list) or not isinstance(pulls,list):
                raise Denied("invalid GitHub collection response",502)
            items=[self.normalize_issue(repo,x) for x in issues if not x.get("pull_request")]
            items += [self.pull_summary(repo,x) for x in pulls]
            data.extend(items)
        return {
            "observed_at":timestamp(), "repositories":list(self.repos), "count":len(data),
            "items":data, "incomplete":True, "limitations":limitations,
            "coverage_note":f"latest {ITEM_LIMIT} issues and {ITEM_LIMIT} PRs per repo, ordered by GitHub API default; not a complete historical inventory",
            "authority":"GitHub source observations, not canonical Issue lifecycle or approvals",
        }

    @staticmethod
    def pull_summary(repo,item):
        return {
            "source_ref":f"github:{repo}/pulls/{item['number']}",
            "kind":"pull_request", "repo":repo, "number":item["number"],
            "title":item.get("title"),"state":item.get("state"),
            "draft":bool(item.get("draft")),"merged":bool(item.get("merged_at")),
            "updated_at":item.get("updated_at"),"created_at":item.get("created_at"),
            "closed_at":item.get("closed_at"),"url":item.get("html_url"),
            "assignee":(item.get("assignee") or {}).get("login"),
        }

    def related(self,title):
        # Candidate discovery, not an authority or automatic dedupe verdict.
        if not isinstance(title,str) or not (3<=len(title)<=200):
            raise Denied("title must contain 3-200 characters",400)
        stop={"the","and","for","with","from","agent","work","issue","project","new","about","into","this","that","when","what","how"}
        def terms(value):
            return {w for w in re.findall(r"[a-z0-9]{3,}", (value or "").lower()) if w not in stop}
        wanted=terms(title)
        if not wanted: return {"title":title,"candidates":[],"method":"token_overlap","incomplete":True}
        portfolio=self.portfolio()
        ranked=[]
        for item in portfolio["items"]:
            found=terms(item["title"])
            intersection=wanted & found
            if not intersection:continue
            score=len(intersection)/max(len(wanted),len(found),1)
            if score>=0.25:
                ranked.append({"source":item,"overlap_score":round(score,3),
                               "matched_terms":sorted(intersection),"disposition":"REVIEW_SIMILARITY_ONLY"})
        ranked.sort(key=lambda x:(-x["overlap_score"],x["source"]["source_ref"]))
        return {"title":title,"candidates":ranked[:10],"method":"bounded_token_overlap",
                "incomplete":True,"coverage_note":portfolio["coverage_note"],
                "not_authority":"similarity cannot authorize merge, denial, or new project"}

    def observe_target(self,target_key):
        source=self.source(target_key)
        if source is None: raise Denied("not a configured GitHub target",400)
        if source["kind"]=="issue":
            value=source["state"]
        else:
            value="merged" if source["merged"] else source["state"]
        return {
            "target_key":target_key,"observed_value":value,
            "observed_at":timestamp(),"source_updated_at":source["updated_at"],
            "source_url":source["url"],"source_ref":source["source_ref"],
            "provider":"github_rest",
        }
