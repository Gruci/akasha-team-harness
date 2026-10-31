"""The landing with a GitHub that the tests play: the answers of `gh pr view` come from a list."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, flow, land, review
from akasha.task import load, save
from tests.helpers import TEAM, Repository


def done(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, stdout, "")


def view(checks: str = "SUCCESS", status: str = "COMPLETED", state: str = "OPEN", review_state: str = "",
         merge: str = "CLEAN") -> dict:
    return {"state": state, "isDraft": False, "mergeStateStatus": merge, "reviewDecision": review_state,
            "headRefOid": "abc", "baseRefName": "main", "url": "https://github.com/o/r/pull/7",
            "statusCheckRollup": [{"__typename": "CheckRun", "name": "akasha", "status": status,
                                   "conclusion": checks if status == "COMPLETED" else ""}]}


class LandTests(unittest.TestCase):
    rules = "akasha"

    def setUp(self):
        self.repo = Repository(TEAM + f'\n[server]\nrules = "{self.rules}"\n')
        self.root = self.repo.root
        for target, value in (("webbrowser.open", None), ("time.sleep", None)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.gh = patch("akasha.repo.gh", return_value=done()).start()
        patch("akasha.pr.gh", self.gh).start()
        patch("akasha.repo.me", return_value="me").start()
        patch("akasha.repo.origin", return_value="o/r").start()
        patch("akasha.board.available", return_value=True).start()
        self.addCleanup(patch.stopall)
        self.task = self.ready()

    def tearDown(self):
        self.repo.close()

    def ready(self):
        with patch("akasha.board.available", return_value=False):
            task, _notes = flow.start(self.root, "Date filter", name="date-filter")
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>p</html>", encoding="utf-8")
        flow.preview(self.root, task.id, show=False)
        approval.on_prompt(self.root, self.root, "승인")
        (records / "plan.md").write_text("plan", encoding="utf-8")
        task = load(self.root, task.id)
        review.note(self.root, task, "PASS", review.plan_digest(task), "reviewer")
        (records / "summary.md").write_text("## Why\nBecause.\n", encoding="utf-8")
        (Path(task.workcopy) / "app.py").write_text("print('x')\n", encoding="utf-8")
        task = load(self.root, task.id)
        task.number, task.pr = 7, "https://github.com/o/r/pull/7"
        save(self.root, task)
        result, _notes = flow.check(self.root, task.id)
        self.assertTrue(all(value == "PASS" for value in result.status.values()))
        return load(self.root, task.id)

    def calls(self, word: str) -> list:
        return [call.args for call in self.gh.call_args_list if word in call.args]

    def test_merges_when_the_checks_pass_and_the_branch_is_up_to_date(self):
        views = [view(status="IN_PROGRESS"), view()]
        with patch("akasha.pr.view", side_effect=views), patch("akasha.repo.gh_json", return_value={"behind_by": 0}):
            state, lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.MERGED)
        merge = self.calls("merge")[-1]
        self.assertIn("--match-head-commit", merge)
        self.assertFalse(Path(self.task.workcopy).exists())
        self.assertTrue(self.calls("ready"))

    def test_a_branch_that_is_behind_comes_up_to_date_first(self):
        views = [view(), view(state="MERGED")]
        with patch("akasha.pr.view", side_effect=views), patch("akasha.repo.gh_json", return_value={"behind_by": 2}):
            state, _lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.MERGED)
        self.assertTrue(self.calls("update-branch"))
        self.assertFalse([call for call in self.calls("merge") if "--match-head-commit" in call])

    def test_a_failed_check_sends_the_task_back_to_the_build(self):
        with patch("akasha.pr.view", return_value=view(checks="FAILURE")), \
                patch("akasha.repo.gh_json", return_value={"behind_by": 0}):
            state, lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.FAILED_CHECK)
        self.assertIn("akasha failed", lines[-1])
        self.assertEqual(load(self.root, self.task.id).status, "approved")

    def test_waits_while_the_checks_run(self):
        with patch("akasha.pr.view", return_value=view(status="QUEUED")), \
                patch("akasha.repo.gh_json", return_value={"behind_by": 0}):
            state, _lines = land.land(self.root, self.task.id, wait=0)
        self.assertEqual(state, land.WAITING)
        self.assertEqual(load(self.root, self.task.id).status, "landing")

    def test_a_risky_change_waits_for_a_reviewer(self):
        with patch("akasha.pr.view", return_value=view()), \
                patch("akasha.repo.gh_json", side_effect=lambda *args, **kwargs: {"files": [{"path": "db/x.sql"}]}
                      if "files" in args else {"behind_by": 0}):
            state, lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.REVIEW)
        self.assertIn("@rev-b", lines[-1])

    def test_the_landing_needs_the_checks_on_the_current_work(self):
        (Path(self.task.workcopy) / "app.py").write_text("print('changed')\n", encoding="utf-8")
        state, lines = land.land(self.root, self.task.id)
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("akasha check", lines[0])


class GitHubRulesTests(LandTests):
    rules = "github"

    def test_merges_when_the_checks_pass_and_the_branch_is_up_to_date(self):
        views = [view(), view(state="MERGED")]
        with patch("akasha.pr.view", side_effect=views), patch("akasha.repo.gh_json", return_value={"behind_by": 0}):
            state, _lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.MERGED)
        self.assertIn("--auto", self.calls("merge")[0])

    def test_a_risky_change_waits_for_a_reviewer(self):
        with patch("akasha.pr.view", return_value=view(review_state="REVIEW_REQUIRED")), \
                patch("akasha.repo.gh_json", return_value={"behind_by": 0}):
            state, _lines = land.land(self.root, self.task.id, wait=60)
        self.assertEqual(state, land.REVIEW)


if __name__ == "__main__":
    unittest.main()
