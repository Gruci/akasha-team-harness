"""The whole way of a task on a computer without GitHub: start, preview, the approval of the person, the plan and its
review, the build, the checks, and the summary."""

import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, flow, land, review
from akasha.task import load, save
from tests.helpers import Repository, run


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        patcher = patch("webbrowser.open")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.repo.close()

    def started(self):
        task, notes = flow.start(self.root, "날짜 필터 넣기", name="date-filter", scope=("app.py",))
        self.assertEqual(notes, [])
        return task

    def approved(self):
        task = self.started()
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>날짜 필터</html>", encoding="utf-8")
        flow.preview(self.root, task.id)
        self.assertIn("approved the preview", approval.on_prompt(self.root, Path(task.workcopy), "승인"))
        return load(self.root, task.id), records

    def reviewed(self):
        task, records = self.approved()
        (records / "plan.md").write_text("# Plan\n- change app.py\n", encoding="utf-8")
        self.mark(f"No problems\nAKASHA-REVIEW: {task.id} {review.plan_digest(task)} PASS")
        return load(self.root, task.id), records

    def mark(self, text: str) -> str:
        return review.on_subagent_stop(self.root, {"agent_type": "akasha:akasha-reviewer",
                                                   "last_assistant_message": text})

    def test_start_makes_a_work_copy_on_a_new_branch(self):
        task = self.started()
        self.assertEqual(task.branch, "akasha/date-filter")
        self.assertTrue((Path(task.workcopy) / "app.py").is_file())
        self.assertEqual(run(Path(task.workcopy), "git", "branch", "--show-current").strip(), task.branch)
        self.assertIn("Ask the person", flow.next_step(task))
        with self.assertRaises(ValueError):
            flow.start(self.root, "again", name="date-filter")

    def test_only_an_approval_of_the_shown_preview_counts(self):
        task = self.started()
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>v1</html>", encoding="utf-8")
        flow.preview(self.root, task.id)
        self.assertIn("feedback", approval.on_prompt(self.root, self.root, "버튼 색 바꿔 줘"))
        (records / "preview.html").write_text("<html>v2</html>", encoding="utf-8")
        self.assertIn("changed after", approval.on_prompt(self.root, self.root, "승인"))
        self.assertEqual(load(self.root, task.id).status, "preview")
        flow.preview(self.root, task.id)
        approval.on_prompt(self.root, self.root, "좋아 진행해")
        self.assertEqual(load(self.root, task.id).status, "approved")

    def test_a_changed_preview_after_the_approval_needs_a_new_approval(self):
        task, records = self.approved()
        (records / "preview.html").write_text("<html>other</html>", encoding="utf-8")
        _task, message = flow.preview(self.root, task.id)
        self.assertIn("approves it again", message)
        self.assertEqual(load(self.root, task.id).status, "preview")

    def test_the_build_waits_for_the_review_of_the_current_plan(self):
        task, records = self.approved()
        self.assertIn("did not pass the review", flow.gate(task))
        (records / "plan.md").write_text("# Plan v1\n", encoding="utf-8")
        old = review.plan_digest(task)
        self.mark(f"AKASHA-REVIEW: {task.id} {old} CHANGES")
        self.assertIn("did not pass", flow.gate(load(self.root, task.id)))
        with self.assertRaises(ValueError):
            flow.self_review(self.root, task.id, "pass")          # a self PASS never replaces the CHANGES
        (records / "plan.md").write_text("# Plan v2\n", encoding="utf-8")
        self.assertIn("another version", self.mark(f"AKASHA-REVIEW: {task.id} {old} PASS"))
        task, _records = load(self.root, task.id), None
        new = review.plan_digest(task)
        self.mark(f"AKASHA-REVIEW: {task.id} {new} PASS\nAKASHA-REVIEW: {task.id} {new} PASS")
        task = load(self.root, task.id)
        self.assertEqual(flow.gate(task), "")
        self.assertEqual(task.review["rounds"], 2)

    def test_claude_code_has_no_self_review(self):
        task, records = self.approved()
        (records / "plan.md").write_text("# Plan\n", encoding="utf-8")
        with patch.dict("os.environ", {"CLAUDECODE": "1"}), self.assertRaises(ValueError):
            flow.self_review(self.root, task.id, "pass")
        self.assertEqual(flow.self_review(self.root, task.id, "pass").review["source"], "self")

    def test_an_approval_belongs_to_the_session_that_showed_the_preview(self):
        """A "좋아요" in one window approved the newest preview of another window (audit F07)."""
        task = self.started()
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>v1</html>", encoding="utf-8")
        with patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "session-a"}):
            flow.preview(self.root, task.id)
        self.assertIn("cannot tell", approval.on_prompt(self.root, self.root, "승인", "session-b"))
        self.assertEqual(approval.on_prompt(self.root, self.root, "이 쿼리 결과 봐줘", "session-b"), "")
        self.assertEqual(approval.on_prompt(self.root, self.root, "<task-notification>승인", "session-a"), "")
        self.assertEqual(load(self.root, task.id).status, "preview")
        self.assertIn("approved the preview", approval.on_prompt(self.root, self.root, "승인", "session-a"))

    def test_an_old_preview_is_not_approved(self):
        task = self.started()
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>v1</html>", encoding="utf-8")
        flow.preview(self.root, task.id)
        task = load(self.root, task.id)
        task.shown_at -= approval.MAX_AGE + 1
        save(self.root, task)
        self.assertEqual(approval.on_prompt(self.root, self.root, "승인"), "")

    def test_two_previews_without_a_session_need_a_choice(self):
        first = self.started()
        second, _notes = flow.start(self.root, "두 번째", name="second")
        for task in (first, second):
            (Path(task.workcopy) / ".akasha" / "tasks" / task.id / "preview.html").write_text("<p>x</p>",
                                                                                            encoding="utf-8")
            flow.preview(self.root, task.id)
        self.assertIn("cannot tell", approval.on_prompt(self.root, self.root, "승인"))
        self.assertIn("approved", approval.on_prompt(self.root, Path(second.workcopy), "승인"))
        self.assertEqual(load(self.root, first.id).status, "preview")

    def test_the_checks_see_new_files_in_the_index(self):
        """MIS static_check lists the files with git ls-files (audit F19)."""
        self.repo.close()
        self.repo = Repository('[checks]\nrequired = ["tests"]\n[checks.tests]\n'
                               'command = "git ls-files --error-unmatch new.py"\n')
        self.root = self.repo.root
        task = self.started()
        tree = Path(task.workcopy)
        records = tree / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<p>x</p>", encoding="utf-8")
        flow.preview(self.root, task.id)
        approval.on_prompt(self.root, tree, "승인")
        (records / "plan.md").write_text("plan", encoding="utf-8")
        self.mark(f"AKASHA-REVIEW: {task.id} {review.plan_digest(load(self.root, task.id))} PASS")
        (tree / "new.py").write_text("x = 1\n", encoding="utf-8")
        result, _notes = flow.check(self.root, task.id)
        self.assertEqual(result.status, {"tests": "PASS"})

    def test_a_failed_start_can_run_again(self):
        """A push or gh pr create that failed once left a task without a pull request (audit F31)."""
        with patch("akasha.board.available", return_value=True), patch("akasha.board.read", return_value=[]), \
                patch("akasha.repo.me", return_value="me"), patch("akasha.repo.fetch") as fetch, \
                patch("akasha.flow.pr.create", side_effect=RuntimeError("gh pr create failed: proxy")):
            fetch.return_value.returncode = 0
            with self.assertRaises(RuntimeError):
                flow.start(self.root, "Retry", name="retry")
        with self.assertRaises(LookupError):
            load(self.root, "retry")
        self.assertEqual(run(self.root, "git", "branch", "--list", "akasha/retry").strip(), "")
        self.assertNotIn("akasha/retry", run(self.root, "git", "ls-remote", "--heads", "origin"))
        self.assertFalse((self.root / ".akasha" / "work" / "retry").exists())

    def test_a_name_on_the_board_or_the_server_is_taken(self):
        """Two teams picked the same name, and the second task went into the branch of the first (audit F16)."""
        task = flow.Task(id="login", title="Login", branch="akasha/login")
        other = flow.board.Entry(task=flow.Task(id="login", title="Login"), number=3, url="", draft=True, author="kim",
                                 branch="akasha/login")
        self.assertTrue(flow._name_taken(self.root, task, "main", [other], online=False))
        self.assertFalse(flow._name_taken(self.root, task, "main", [], online=False))
        run(self.root, "git", "push", "-q", "origin", "main:refs/heads/akasha/login")
        self.assertTrue(flow._name_taken(self.root, task, "main", [], online=True))

    def test_a_task_that_moved_to_another_person_leaves_this_computer(self):
        """The old computer of a task went on, and its cancel closed the pull request of the new holder (audit F30)."""
        task = self.started()
        task.number = 7
        save(self.root, task)
        answer = {"state": "OPEN", "assignees": [{"login": "kim"}], "headRefOid": run(Path(task.workcopy), "git",
                                                                                       "rev-parse", "HEAD").strip()}
        with patch("akasha.board.available", return_value=True), patch("akasha.repo.me", return_value="me"), \
                patch("akasha.repo.gh_json", return_value=answer), patch("akasha.repo.gh") as gh:
            with self.assertRaises(ValueError):
                flow.preview(self.root, task.id, text="x")           # nothing goes to the branch of the new holder
            self.assertIn("@kim holds", flow.cancel(self.root, task.id))
            gh.assert_not_called()
        self.assertFalse(Path(task.workcopy).exists())

    def test_a_commit_that_is_only_here_stays_when_another_person_took_the_task(self):
        """tidy removed a copy whose commit never reached GitHub (review)."""
        task = self.started()
        task.number = 7
        save(self.root, task)
        tree = Path(task.workcopy)
        head = run(tree, "git", "rev-parse", "HEAD").strip()
        (tree / "app.py").write_text("print('only here')\n", encoding="utf-8")
        run(tree, "git", "commit", "-q", "-am", "only here")
        answer = {"state": "OPEN", "assignees": [{"login": "kim"}], "headRefOid": head}
        with patch("akasha.board.available", return_value=True), patch("akasha.repo.me", return_value="me"), \
                patch("akasha.repo.gh_json", return_value=answer):
            lines = flow.tidy(self.root)
        self.assertIn("not on GitHub", lines[0])
        self.assertTrue(tree.is_dir())
        self.assertEqual(load(self.root, task.id).id, task.id)

    def test_a_name_that_another_team_pushed_a_moment_ago_is_not_taken_over(self):
        """The undo of a failed start deleted the branch of another team (review)."""
        other = run(self.root, "git", "commit-tree", "HEAD^{tree}", "-m", "the start of another team").strip()
        run(self.root, "git", "push", "-q", "origin", f"{other}:refs/heads/akasha/race")
        with patch("akasha.board.available", return_value=True), patch("akasha.board.read", return_value=[]), \
                patch("akasha.repo.me", return_value="me"), patch("akasha.flow._name_taken", return_value=False), \
                patch("akasha.flow.pr.create") as create:
            with self.assertRaises(ValueError):
                flow.start(self.root, "Race", name="race")
            create.assert_not_called()
        self.assertIn("akasha/race", run(self.root, "git", "ls-remote", "--heads", "origin"))

    def test_handoff_and_cancel_wait_until_the_session_leaves_the_work_copy(self):
        task = self.started()
        with patch.object(Path, "cwd", return_value=Path(task.workcopy)), self.assertRaises(ValueError):
            flow.cancel(self.root, task.id)
        self.assertTrue(Path(task.workcopy).exists())

    def test_checks_save_the_work_and_land_waits_for_the_summary(self):
        task, records = self.reviewed()
        tree = Path(task.workcopy)
        (tree / "app.py").write_text("print('date filter')\n", encoding="utf-8")
        self.assertIn("akasha check", flow.next_step(load(self.root, task.id)))
        result, _notes = flow.check(self.root, task.id)
        self.assertEqual(result.status, {"secrets": "PASS", "tests": "PASS"})
        task = load(self.root, task.id)
        self.assertEqual(task.checks["commit"], run(tree, "git", "rev-parse", "HEAD").strip())
        self.assertIn("summary.md", flow.next_step(task))
        state, lines = land.land(self.root, task.id)
        self.assertEqual(state, land.BLOCKED)
        (records / "summary.md").write_text("## Why\n", encoding="utf-8")
        flow.check(self.root, task.id)
        state, lines = land.land(self.root, task.id)
        self.assertEqual(state, land.BLOCKED)
        self.assertIn("pull request on GitHub", lines[0])

    def test_a_failed_check_counts_and_a_secret_fails(self):
        task, _records = self.reviewed()
        tree = Path(task.workcopy)
        (tree / "app.py").write_text("key = 'AKIA" + "ABCDEFGHIJKLMNOP'\n", encoding="utf-8")
        result, _notes = flow.check(self.root, task.id)
        self.assertEqual(result.status["secrets"], "FAIL")
        task = load(self.root, task.id)
        self.assertEqual(task.failures, 1)
        self.assertEqual(task.stats["check_failures"], {"secrets": 1})
        self.assertFalse(task.checks)

    def test_cancel_removes_the_work_copy(self):
        task = self.started()
        self.assertIn("cancelled", flow.cancel(self.root, task.id))
        self.assertFalse(Path(task.workcopy).exists())
        with self.assertRaises(LookupError):
            load(self.root, task.id)

    def test_handoff_saves_the_work_on_the_server(self):
        task, _records = self.approved()
        flow.handoff(self.root, task.id)
        self.assertIn(task.branch, run(self.root, "git", "ls-remote", "--heads", "origin"))
        self.assertFalse(Path(task.workcopy).exists())
        with self.assertRaises(LookupError):
            load(self.root, task.id)


class CheckArtifactTests(unittest.TestCase):
    """A real run: the __pycache__ of the tests went into the commits of two tasks, and the second task conflicted
    with the first on files that nobody wrote (2026-10-31)."""

    TEAM = ('[checks]\nrequired = ["tests"]\n[checks.tests]\ncommand = "python -c \\"import pathlib; '
            "pathlib.Path('cache').mkdir(exist_ok=True); pathlib.Path('cache/x.bin').write_text('1')\\\"\"\n")

    def setUp(self):
        self.repo = Repository(self.TEAM)
        self.root = self.repo.root
        patcher = patch("webbrowser.open")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.repo.close()

    def test_files_that_a_check_makes_stay_out_of_the_commit(self):
        task, _notes = flow.start(self.root, "Artifacts", name="artifacts")
        tree = Path(task.workcopy)
        (tree / "app.py").write_text("print('x')\n", encoding="utf-8")
        result, notes = flow.check(self.root, task.id)
        self.assertEqual(result.status, {"tests": "PASS"})
        self.assertIn("cache/x.bin", notes[0])
        committed = run(tree, "git", "show", "--name-only", "--format=", "HEAD")
        self.assertIn("app.py", committed)
        self.assertNotIn("cache/x.bin", committed)
        self.assertEqual(run(tree, "git", "status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
