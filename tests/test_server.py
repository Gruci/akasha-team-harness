import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha.core.workcopy import git
from akasha.infra import server

SHA = "a" * 40


def answer(stdout: object = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout if isinstance(stdout, str) else json.dumps(stdout), "")


class FakeGitHub:
    """Answers the gh calls of the server helpers and records them."""

    def __init__(self, protected: bool = False, pulls: dict | None = None, behind: int = 0, label: bool = True):
        self.protected, self.pulls, self.behind, self.label = protected, pulls or {}, behind, label
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, root, *args, payload=None):
        self.calls.append(args)
        if args[:1] == ("api",):
            path = args[1]
            if path.endswith("/branches/main"):
                return answer({"protected": self.protected})
            if "/compare/" in path:
                return answer({"behind_by": self.behind})
            if path.endswith("/pulls") and "/commits/" in path:
                return answer(self.pulls.get(path.split("/commits/")[1].split("/")[0], []))
            if "/check-runs" in path:
                return answer({"check_runs": [{"conclusion": "success"}]})
            if path.endswith("/reviews"):
                return answer([])
            if "/pulls/" in path:
                return answer({"number": 5, "head": {"sha": SHA}, "merged_by": {"login": "dev-a"}})
        return answer("")

    def did(self, *words: str) -> bool:
        return any(call[:len(words)] == words for call in self.calls)


class MergeTests(unittest.TestCase):
    def pull(self, labeled: bool = True) -> dict:
        return {SHA: [{"state": "open", "number": 7, "title": "Add a date filter", "head": {"sha": SHA},
                       "base": {"ref": "main"}, "labels": [{"name": server.MERGE_LABEL}] if labeled else [],
                       "body": "## Why\n\nA reason.\n\nCloses #3\n\n<!-- akasha-task: t-1 -->\n"}]}

    def test_merges_a_marked_pull_request_on_the_latest_branch(self):
        fake = FakeGitHub(pulls=self.pull())
        with patch("akasha.infra.server.gh", fake):
            self.assertEqual(server.merge(Path("."), "team/app", SHA), "merged #7")
        merged = next(call for call in fake.calls if call[:2] == ("pr", "merge"))
        self.assertIn("--match-head-commit", merged)
        self.assertEqual(merged[merged.index("--subject") + 1], "Add a date filter (#7)")
        self.assertEqual(merged[merged.index("--body") + 1], "## Why\n\nA reason.\n")
        self.assertTrue(fake.did("issue", "close", "3"))             # the workflow token does not close it

    def test_steps_aside_or_waits(self):
        cases = {"has no akasha-merge label": FakeGitHub(pulls=self.pull(labeled=False)),
                 "GitHub protects main": FakeGitHub(protected=True, pulls=self.pull()),
                 "is behind main": FakeGitHub(behind=2, pulls=self.pull())}
        for expected, fake in cases.items():
            with self.subTest(expected=expected), patch("akasha.infra.server.gh", fake):
                self.assertIn(expected, server.merge(Path("."), "team/app", SHA))
                self.assertFalse(fake.did("pr", "merge"))
        self.assertTrue(cases["is behind main"].did("pr", "comment"))


class WatchTests(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-watch-"))
        self.remote, self.root = folder / "remote.git", folder / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.root)], check=True, capture_output=True)
        for key, value in (("user.email", "dev@example.com"), ("user.name", "Dev")):
            git(self.root, "config", key, value)
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["admin-a"]\n', encoding="utf-8")
        self.before = self.commit("first")
        (self.root / "app.py").write_text("x = 1\n", encoding="utf-8")
        self.after = self.commit("a direct change")

    def commit(self, message: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)
        git(self.root, "push", "-q", "origin", "HEAD:main")
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def watch(self, fake: FakeGitHub, pusher: str = "dev-b", forced: bool = False) -> str:
        with patch("akasha.infra.server.gh", fake):
            return server.watch(self.root, "team/app", "main", self.before, self.after, forced, pusher)

    def test_a_direct_change_is_undone(self):
        fake = FakeGitHub()
        self.assertEqual(self.watch(fake), "undid 1 change(s)")
        self.assertTrue(git(self.remote, "log", "-1", "--format=%s", "main").stdout.startswith(server.UNDO_MARK))
        self.assertFalse((self.root / "app.py").exists())
        self.assertTrue(fake.did("issue", "create"))
        undo = git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(server._reason(self.root, "team/app", server._team_at(self.root, self.before), undo), "")

    def test_reported_but_not_undone(self):
        for name, fake, pusher, forced in (("administrator", FakeGitHub(), "admin-a", False),
                                           ("force push", FakeGitHub(), "dev-b", True)):
            with self.subTest(name=name):
                self.assertIn("reported", self.watch(fake, pusher, forced))
                self.assertTrue(fake.did("issue", "create"))
                self.assertEqual(git(self.remote, "rev-parse", "main").stdout.strip(), self.after)

    def test_a_change_in_order_or_under_github_protection_stays(self):
        merged = FakeGitHub(pulls={self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]})
        self.assertEqual(self.watch(merged), "all changes are in order")
        protected = FakeGitHub(protected=True)
        self.assertIn("GitHub protects main", self.watch(protected))
        self.assertFalse(protected.did("issue", "create"))

    def test_a_rules_file_needs_its_owner(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "x.yml").write_text("on: push\n", encoding="utf-8")
        self.after = self.commit("change a rule")
        fake = FakeGitHub(pulls={self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]})
        with patch("akasha.infra.server.gh", fake):
            reason = server._reason(self.root, "team/app", server._team_at(self.root, self.before), self.after)
        self.assertIn("without the approval of its owner", reason)


if __name__ == "__main__":
    unittest.main()
