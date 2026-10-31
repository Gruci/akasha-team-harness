"""The landing with a GitHub that the tests play: the answers of `gh pr view` come from a list, the JSON answers of
gh from `answers`, and the other calls of gh from `Landing.github`."""

import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, flow, land, review
from akasha.task import load, save
from tests.helpers import TEAM, Repository, run


def done(stdout: str = "", code: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def view(head: str, checks: str = "SUCCESS", status: str = "COMPLETED", state: str = "OPEN", review_state: str = "",
         merge: str = "CLEAN", draft: bool = False, name: str = "akasha") -> dict:
    return {"state": state, "isDraft": draft, "mergeStateStatus": merge, "reviewDecision": review_state,
            "headRefOid": head, "baseRefName": "main", "url": "https://github.com/o/r/pull/7",
            "author": {"login": "me"}, "mergeCommit": {"oid": "m1"} if state == "MERGED" else None,
            "statusCheckRollup": [{"__typename": "CheckRun", "name": name, "status": status,
                                   "conclusion": checks if status == "COMPLETED" else "",
                                   "detailsUrl": "https://github.com/o/r/actions/runs/55/job/1"}]}


def answers(behind=0, reviews=(), protected=False, assignees=()):
    """The JSON answers of gh. `protected` is None for no answer about the branch."""
    def gh_json(_root, *args, **_kwargs):
        path = next((arg for arg in args if arg.startswith("repos/")), "")
        if "/compare/" in path:
            return {"behind_by": behind} if behind is not None else None
        if "/reviews" in path:
            return list(reviews)
        if "/branches/" in path:
            return None if protected is None else {
                "protected": protected, "protection": {"required_status_checks": {"contexts": ["akasha"]}}}
        if "assignees" in args:
            return {"assignees": [{"login": name} for name in assignees]}
        return None
    return gh_json


class CheckStateTests(unittest.TestCase):
    """A real run on GitHub: the run that the draft skipped stays on the head next to the real run (2026-10-31)."""

    @staticmethod
    def rollup(*runs):
        return {"statusCheckRollup": [{"name": "akasha", "status": status, "conclusion": conclusion,
                                       "startedAt": started} for status, conclusion, started in runs]}

    def test_the_latest_run_that_did_not_skip_decides(self):
        cases = {(("COMPLETED", "SKIPPED", "1"),): "WAIT",
                 (("COMPLETED", "SKIPPED", "1"), ("IN_PROGRESS", "", "2")): "WAIT",
                 (("COMPLETED", "SKIPPED", "1"), ("COMPLETED", "SUCCESS", "2")): "PASS",
                 (("COMPLETED", "SUCCESS", "1"), ("COMPLETED", "FAILURE", "2")): "FAIL",
                 (("COMPLETED", "CANCELLED", "1"), ("COMPLETED", "SUCCESS", "2")): "PASS",
                 (("COMPLETED", "SUCCESS", "1"), ("COMPLETED", "CANCELLED", "2")): "CANCELLED",
                 (): "MISSING"}
        for runs, expected in cases.items():
            with self.subTest(runs=runs):
                self.assertEqual(land._states(self.rollup(*runs), ("akasha",)), {"akasha": expected})


class Landing(unittest.TestCase):
    """A task that is ready to land, and the GitHub of the tests."""
    rules = "akasha"
    protected = False
    team = TEAM

    def setUp(self):
        self.repo = Repository(self.team + f'\n[server]\nrules = "{self.rules}"\n')
        self.root = self.repo.root
        for target, value in (("webbrowser.open", None), ("time.sleep", None)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.files, self.runs, self.branch_runs, self.merge_error = ["app.py"], None, None, ""
        self.gh = patch("akasha.repo.gh", side_effect=self.github).start()
        patch("akasha.pr.gh", self.gh).start()
        patch("akasha.repo.me", return_value="me").start()
        patch("akasha.repo.origin", return_value="o/r").start()
        patch("akasha.board.available", return_value=True).start()
        self.addCleanup(patch.stopall)
        self.task = self.ready()
        self.head = self.task.checks["commit"]

    def tearDown(self):
        self.repo.close()

    def ready(self, path: str = "app.py"):
        with patch("akasha.board.available", return_value=False):
            task, _notes = flow.start(self.root, "Date filter", name="date-filter")
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>p</html>", encoding="utf-8")
        flow.preview(self.root, task.id, show=False)
        approval.on_prompt(self.root, self.root, "approve")
        flow.approve(self.root, task.id)
        (records / "plan.md").write_text("plan", encoding="utf-8")
        task = load(self.root, task.id)
        review.note(self.root, task, "PASS", review.plan_digest(task), "reviewer")
        (records / "summary.md").write_text("## Why\nBecause.\n", encoding="utf-8")
        (Path(task.workcopy) / path).parent.mkdir(parents=True, exist_ok=True)
        (Path(task.workcopy) / path).write_text("print('x')\n", encoding="utf-8")
        task = load(self.root, task.id)
        task.number, task.pr = 7, "https://github.com/o/r/pull/7"
        save(self.root, task)
        with patch("akasha.repo.gh_json", side_effect=answers()):
            result, _notes = flow.check(self.root, task.id)
        self.assertTrue(all(value == "PASS" for value in result.status.values()))
        return load(self.root, task.id)

    def land(self, views, wait=60, **kwargs):
        many = isinstance(views, list)
        with patch("akasha.pr.view", **({"side_effect": views} if many else {"return_value": views})), \
                patch("akasha.repo.gh_json", side_effect=answers(protected=self.protected, **kwargs)):
            return land.land(self.root, self.task.id, wait=wait)

    def github(self, _root, *args, **_kwargs) -> subprocess.CompletedProcess:
        """The other calls of gh: the files of the pull request, the runs of the deployment, and the merge."""
        if "--paginate" in args:
            return done("\n".join(self.files))
        if args[:2] == ("run", "list"):
            runs = self.branch_runs if "--branch" in args else self.runs
            return done(json.dumps(runs)) if runs is not None else done("", 1, "could not find any workflows")
        if args[:2] == ("pr", "merge") and "--match-head-commit" in args and self.merge_error:
            return done("", 1, self.merge_error)
        return done()

    def calls(self, word: str) -> list:
        return [call.args for call in self.gh.call_args_list if word in call.args]

    def own_merges(self) -> list:
        return [call for call in self.calls("merge") if "--match-head-commit" in call]


class LandTests(Landing):
    def test_merges_when_the_checks_pass_and_the_branch_is_up_to_date(self):
        state, _lines = self.land([view(self.head), view(self.head, status="IN_PROGRESS"), view(self.head),
                                   view(self.head, state="MERGED")])
        self.assertEqual(state, land.MERGED)
        self.assertIn("--match-head-commit", self.calls("merge")[-1])
        self.assertFalse(Path(self.task.workcopy).exists())
        self.assertTrue(self.calls("ready"))

    def test_a_branch_that_is_behind_comes_up_to_date_first(self):
        state, _lines = self.land([view(self.head), view(self.head), view(self.head, state="MERGED")], behind=2)
        self.assertEqual(state, land.MERGED)
        self.assertTrue(self.calls("update-branch"))
        self.assertFalse(self.own_merges())

    def test_no_answer_on_the_branch_is_no_merge(self):
        """The examination fails closed: a missing compare answer of GitHub never merges (audit F37)."""
        state, _lines = self.land(view(self.head), wait=0, behind=None)
        self.assertEqual(state, land.WAITING)
        self.assertFalse(self.own_merges())

    def test_a_failed_check_sends_the_task_back_to_the_build(self):
        state, lines = self.land(view(self.head, checks="FAILURE"))
        self.assertEqual(state, land.FAILED_CHECK)
        self.assertIn("akasha failed", lines[-1])
        task = load(self.root, self.task.id)
        self.assertEqual((task.status, task.stats["server_check_failures"]), ("approved", {"akasha": 1}))

    def test_a_cancelled_check_runs_again_once(self):
        state, _lines = self.land(view(self.head, checks="CANCELLED"), wait=0)
        self.assertEqual(state, land.WAITING)
        self.assertIn(("run", "rerun", "55"), [call[1:4] for call in self.calls("rerun")])
        state, lines = self.land(view(self.head, checks="CANCELLED"), wait=0)
        self.assertEqual(state, land.FAILED_CHECK)
        self.assertIn("cancelled on GitHub again", lines[-1])

    def test_a_check_that_never_ran_is_named(self):
        state, lines = self.land(view(self.head, name="PR checks"), wait=0)
        self.assertEqual(state, land.WAITING)
        self.assertIn("no check named akasha", lines[-1])

    def test_waits_while_the_checks_run(self):
        state, _lines = self.land(view(self.head, status="QUEUED"), wait=0)
        self.assertEqual(state, land.WAITING)
        self.assertEqual(load(self.root, self.task.id).status, "landing")

    def test_a_draft_gets_ready_again(self):
        self.land(view(self.head, draft=True, status="QUEUED"), wait=0)
        self.assertGreaterEqual(len(self.calls("ready")), 2)

    def test_a_conflict_sends_the_task_back_to_the_hand_over(self):
        state, _lines = self.land(view(self.head, merge="DIRTY"))
        self.assertEqual(state, land.CONFLICT)
        self.assertEqual(load(self.root, self.task.id).status, "approved")

    def test_a_risky_change_waits_for_a_reviewer(self):
        self.files = [f"app/{number:03}.py" for number in range(150)] + ["db/x.sql"]     # beyond the first 100 files
        state, lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.REVIEW)
        self.assertIn("@rev-b", lines[-1])
        self.assertFalse(self.own_merges())
        state, _lines = self.land(view(self.head), reviews=[{"user": {"login": "rev-b"}, "state": "APPROVED"}])
        self.assertEqual(state, land.MERGED)

    def test_another_collaborator_does_not_approve_a_risky_change(self):
        """On GitHub Free nothing enforces CODEOWNERS: Akasha asks for a reviewer itself (audit F11)."""
        self.files = ["db/x.sql"]
        state, _lines = self.land(view(self.head), wait=0, reviews=[{"user": {"login": "someone"}, "state": "APPROVED"}])
        self.assertEqual(state, land.REVIEW)
        self.assertFalse(self.own_merges())

    def test_a_change_of_the_rules_waits_for_an_administrator(self):
        self.files = ["akasha.toml"]
        state, lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.REVIEW)
        self.assertIn("@admin-a", lines[-1])

    def test_a_merge_that_github_refuses_is_named_or_tried_again(self):
        self.merge_error = "GraphQL: Head branch was modified. Review and try the merge again."
        state, _lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.WAITING)
        self.merge_error = "GraphQL: Resource not accessible by integration"
        state, lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("not accessible", lines[-1])

    def test_the_landing_goes_on_after_the_default_branch_moved(self):
        """The hand-over merges the newer default branch: that commit is the landed work, not a change (review)."""
        other = Path(self.repo.folder.name) / "other"
        run(Path(self.repo.folder.name), "git", "clone", "-q", str(self.repo.origin), str(other))
        (other / "news.txt").write_text("news\n", encoding="utf-8")
        for args in (("add", "-A"), ("-c", "user.name=O", "-c", "user.email=o@x", "commit", "-q", "-m", "news"),
                     ("push", "-q", "origin", "main")):
            run(other, "git", *args)
        self.land(view(self.head, status="QUEUED"), wait=0)
        landed = load(self.root, self.task.id).checks["landed"]
        self.assertNotEqual(landed, self.head)
        state, _lines = self.land(view(landed), wait=0)
        self.assertEqual(state, land.WAITING if self.protected else land.MERGED)    # the auto-merge of GitHub merges
        if self.protected:
            self.assertEqual(load(self.root, self.task.id).status, "landing")

    def test_commits_that_github_lacks_are_pushed_first(self):
        self.land(view(self.head, status="QUEUED"), wait=0)
        with patch("akasha.work.contains", side_effect=[False, True, True]), patch("akasha.work.push") as push:
            self.land([view("old"), view(self.head, state="MERGED")])
        push.assert_called_once()

    def test_a_task_that_another_person_took_does_not_land_here(self):
        state, lines = self.land(view(self.head), assignees=("kim",))
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("@kim holds", lines[0])
        self.assertFalse(self.calls("ready"))

    def test_the_landing_needs_the_checks_on_the_current_work(self):
        (Path(self.task.workcopy) / "app.py").write_text("print('changed')\n", encoding="utf-8")
        state, lines = land.land(self.root, self.task.id)
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("akasha check", lines[0])

    def test_a_change_during_the_landing_stops_it(self):
        self.land(view(self.head, status="QUEUED"), wait=0)
        (Path(self.task.workcopy) / "app.py").write_text("print('later')\n", encoding="utf-8")
        state, lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("akasha check", lines[0])
        self.assertEqual(load(self.root, self.task.id).status, "approved")

    def test_a_merge_on_github_keeps_the_work_that_did_not_land(self):
        tree = Path(self.task.workcopy)
        self.land(view(self.head, status="QUEUED"), wait=0)
        (tree / "app.py").write_text("print('not landed')\n", encoding="utf-8")
        state, lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.MERGED)
        self.assertTrue(tree.is_dir())
        self.assertIn("not on GitHub", lines[-1])

    def test_a_commit_that_did_not_land_stays(self):
        """A commit that is only on this computer is work, as an edit is (review)."""
        tree = Path(self.task.workcopy)
        self.land(view(self.head, status="QUEUED"), wait=0)
        (tree / "app.py").write_text("print('committed here')\n", encoding="utf-8")
        run(tree, "git", "commit", "-q", "-am", "only here")
        state, lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.MERGED)
        self.assertTrue(tree.is_dir())
        self.assertIn("not on GitHub", lines[-1])

    def deploying(self):
        self.repo.close()
        self.repo = Repository(TEAM + f'\n[server]\nrules = "{self.rules}"\n[deploy]\nworkflow = "Deploy"\n')
        self.root = self.repo.root
        self.task = self.ready()
        self.head = self.task.checks["commit"]

    def test_the_deployment_decides_when_the_change_is_live(self):
        self.deploying()
        self.runs = [{"status": "in_progress"}]
        state, _lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.DEPLOYING)
        self.assertIn("deployment", flow.next_step(load(self.root, self.task.id)))
        with patch("akasha.repo.gh_json", return_value={"state": "MERGED", "headRefOid": self.head}):
            self.assertEqual(flow.tidy(self.root), [])               # a session start does not end the follow
        self.runs = [{"status": "completed", "conclusion": "failure", "url": "u"}]
        state, lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.DEPLOY_FAILED)
        with self.assertRaises(LookupError):
            load(self.root, self.task.id)

    def test_a_newer_deployment_takes_the_place_of_a_cancelled_one(self):
        """A deploy workflow with a concurrency group cancels a waiting run when a newer merge comes (review)."""
        self.deploying()
        self.runs = [{"status": "completed", "conclusion": "cancelled", "createdAt": "2026-11-01T10:00:00Z"}]
        self.branch_runs = [{"status": "in_progress", "createdAt": "2026-11-01T10:05:00Z"}] + self.runs
        state, _lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.DEPLOYING)
        self.branch_runs[0] = {"status": "completed", "conclusion": "success", "url": "u2",
                               "createdAt": "2026-11-01T10:05:00Z"}
        state, lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.DEPLOYED)
        self.assertIn("u2", lines[-1])

    def test_a_conflict_names_the_files(self):
        other = Path(self.repo.folder.name) / "other"
        run(Path(self.repo.folder.name), "git", "clone", "-q", str(self.repo.origin), str(other))
        (other / "app.py").write_text("print('another team')\n", encoding="utf-8")
        for args in (("-c", "user.name=O", "-c", "user.email=o@x", "commit", "-q", "-am", "other"),
                     ("push", "-q", "origin", "main")):
            run(other, "git", *args)
        state, lines = self.land(view(self.head))
        self.assertEqual(state, land.CONFLICT)
        self.assertIn("app.py", lines[0])

    def test_a_deployment_that_never_shows_ends_the_follow(self):
        self.deploying()
        state, _lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.DEPLOYING)
        task = load(self.root, self.task.id)
        task.checks["merged_at"] = time.time() - land.DEPLOY_GRACE - 1
        save(self.root, task)
        state, lines = self.land(view(self.head, state="MERGED"), wait=0)
        self.assertEqual(state, land.MERGED)
        self.assertIn("could not find any workflows", lines[-1])
        with self.assertRaises(LookupError):
            load(self.root, self.task.id)                                                    # the task ended


class OnlyReviewerTests(Landing):
    """The author is the only reviewer: an administrator reviews in place (audit F25)."""

    def setUp(self):
        super().setUp()
        patch("akasha.repo.me", return_value="rev-b").start()

    def test_a_risky_change_waits_for_a_reviewer(self):
        self.files = ["db/x.sql"]
        state, lines = self.land(view(self.head), wait=0)
        self.assertEqual(state, land.REVIEW)
        self.assertIn("@admin-a", lines[-1])


class GitHubRulesTests(LandTests):
    rules = "github"
    protected = True

    def test_merges_when_the_checks_pass_and_the_branch_is_up_to_date(self):
        state, _lines = self.land([view(self.head), view(self.head), view(self.head, state="MERGED")])
        self.assertEqual(state, land.MERGED)
        self.assertIn("--auto", self.calls("merge")[0])
        self.assertFalse(self.own_merges())

    def test_a_risky_change_waits_for_a_reviewer(self):
        self.files = ["db/x.sql"]
        state, _lines = self.land(view(self.head, review_state="REVIEW_REQUIRED"), wait=0)
        self.assertEqual(state, land.REVIEW)

    def test_another_collaborator_does_not_approve_a_risky_change(self):
        self.files = ["db/x.sql"]
        state, _lines = self.land(view(self.head, review_state="REVIEW_REQUIRED"), wait=0)
        self.assertEqual(state, land.REVIEW)

    def test_a_merge_that_github_refuses_is_named_or_tried_again(self):
        """GitHub merges with its auto-merge here: Akasha never merges itself."""
        self.land(view(self.head), wait=0)
        self.assertFalse(self.own_merges())

class UnprotectedTests(Landing):
    """[server] rules says github, but GitHub does not protect the branch: Akasha merges itself, after its examination,
    and never turns on an auto-merge that nothing stops (audit F06)."""
    rules = "github"

    def test_merges_when_the_checks_pass_and_the_branch_is_up_to_date(self):
        state, _lines = self.land([view(self.head), view(self.head), view(self.head, state="MERGED")])
        self.assertEqual(state, land.MERGED)
        self.assertFalse([call for call in self.calls("merge") if "--auto" in call])
        self.assertTrue(self.own_merges())

    def test_no_answer_about_the_protection_is_no_protection(self):
        self.protected = None
        state, _lines = self.land([view(self.head), view(self.head)])
        self.assertEqual(state, land.MERGED)
        self.assertTrue(self.own_merges())


if __name__ == "__main__":
    unittest.main()
