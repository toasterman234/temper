"""Northflank boot hardening: network, durable volume and credential fail-closed."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api import credentials, verify_network_and_storage


def config(**overrides):
    value = {
        "WORK_DEPLOYMENT_MODE": "northflank",
        "WORK_GITHUB_REPOS": "toasterman234/master-repo-0.1,toasterman234/temper",
        "WORK_GITHUB_READ_TOKEN": "readonly-github-placeholder",
        "WORK_AGENT_TOKEN": "a"*40,
        "WORK_APPROVER_TOKEN": "b"*40,
        "WORK_VERIFIER_TOKEN": "c"*40,
        "WORK_AGENT_ID": "pi",
        "WORK_APPROVER_ID": "human",
        "WORK_VERIFIER_ID": "independent-reviewer",
    }
    value.update(overrides)
    return value


def args(**overrides):
    options={"db":"/data/agent-work.sqlite3", "bind":"0.0.0.0", "port":8765}
    options.update(overrides)
    return SimpleNamespace(**options)


class DeploymentChecks(unittest.TestCase):
    def verify(self, conf=None, **kwargs):
        conf = config() if conf is None else conf
        with patch("api.os.path.ismount", return_value=True), patch("api.os.access", return_value=True):
            return verify_network_and_storage(args=args(**kwargs), env=conf, identities=credentials(conf))

    def test_valid_northflank_configuration(self):
        self.assertIsNone(self.verify())

    def test_no_direct_external_binding_in_local_mode(self):
        conf=config(WORK_DEPLOYMENT_MODE="")
        with self.assertRaisesRegex(RuntimeError,"must bind localhost"):
            self.verify(conf,bind="0.0.0.0")
        self.verify(conf,bind="127.0.0.1")

    def test_requires_volume(self):
        conf=config()
        with patch("api.os.path.ismount",return_value=False):
            with self.assertRaisesRegex(RuntimeError,"persistent volume"):
                verify_network_and_storage(args=args(),env=conf,identities=credentials(conf))

    def test_rejects_wrong_database_path_or_port(self):
        with self.assertRaisesRegex(RuntimeError,"directly under /data"):
            self.verify(db="/tmp/work.sqlite3")
        with self.assertRaisesRegex(RuntimeError,"port 8765"):
            self.verify(port=8000)

    def test_missing_github_secret_is_fatal(self):
        with self.assertRaisesRegex(RuntimeError,"WORK_GITHUB_READ_TOKEN"):
            self.verify(config(WORK_GITHUB_READ_TOKEN=""))

    def test_token_and_identity_separation(self):
        with self.assertRaisesRegex(RuntimeError,"32 characters"):
            self.verify(config(WORK_AGENT_TOKEN="x"*24))
        with self.assertRaisesRegex(RuntimeError,"distinct"):
            self.verify(config(WORK_VERIFIER_ID="pi"))

    def test_requires_allowlisted_repository_configuration(self):
        with self.assertRaisesRegex(RuntimeError,"WORK_GITHUB_REPOS"):
            self.verify(config(WORK_GITHUB_REPOS=""))


if __name__=="__main__":
    unittest.main()
