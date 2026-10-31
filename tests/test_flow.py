"""The whole way of a task on a computer without GitHub: start, preview, the approval of the person, the plan and its
review, the build, the checks, and the summary."""

import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, flow, land, review
from akasha.task import load
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
        mark = f"No problems\nAKASHA-REVIEW: {task.id} {review.plan_digest(task)} PASS"
        review.on_subagent_stop(self.root, {"last_assistant_message": mark})
        return load(self.root, task.id), records

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
        review.on_subagent_stop(self.root, {"last_assistant_message": f"AKASHA-REVIEW: {task.id} {old} CHANGES"})
        self.assertIn("did not pass", flow.gate(load(self.root, task.id)))
        (records / "plan.md").write_text("# Plan v2\n", encoding="utf-8")
        told = review.on_subagent_stop(self.root, {"last_assistant_message": f"AKASHA-REVIEW: {task.id} {old} PASS"})
        self.assertIn("another version", told)
        task, _records = load(self.root, task.id), None
        new = review.plan_digest(task)
        review.on_subagent_stop(self.root, {"last_assistant_message": f"AKASHA-REVIEW: {task.id} {new} PASS"})
        task = load(self.root, task.id)
        self.assertEqual(flow.gate(task), "")
        self.assertEqual(task.review["rounds"], 2)

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


if __name__ == "__main__":
    unittest.main()
