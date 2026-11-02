"""The parts of a task: workers build at the same time, each in its own work copy and its own files, after one
approval of the person and one review of the plan. Real git repositories, without GitHub."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, flow, guard, land, review
from akasha.task import all_local, load
from tests.helpers import Repository, run

QUIET = {key: "" for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE")}


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        files = {"server/api.py": "def total():\n    return 0\n", "web/page.js": "export const a = 1;\n"}
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "app")
        run(self.root, "git", "push", "-q", "origin", "main")
        for patcher in (patch("webbrowser.open"), patch.dict(os.environ, QUIET)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.repo.close()

    def started(self):
        task, _notes = flow.start(self.root, "월 합계 화면", name="total", scope=("server/**", "web/**"))
        return task

    def ready(self):
        task = self.started()
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text('<section id="akasha-decisions">합계</section>', encoding="utf-8")
        flow.preview(self.root, task.id)
        approval.on_prompt(self.root, Path(task.workcopy), "좋아요")
        flow.approve(self.root, task.id)
        (records / "plan.md").write_text("# Plan\n", encoding="utf-8")
        task = load(self.root, task.id)
        review.on_subagent_stop(self.root, {"agent_type": "akasha-reviewer", "last_assistant_message":
                                            f"AKASHA-REVIEW: {task.id} {review.plan_digest(task)} PASS"})
        return load(self.root, task.id)

    def two_parts(self):
        task = self.ready()
        api, _notes = flow.split(self.root, task.id, "api", ("server/**",))
        web, _notes = flow.split(self.root, task.id, "web", ("web/",))
        return load(self.root, task.id), Path(api["workcopy"]), Path(web["workcopy"])

    def stopped(self, path: Path) -> str | None:
        return guard.check_edit(path, self.root, all_local(self.root), True, flow.gate, locked=("db/**",))

    def test_a_task_splits_only_after_the_approval_and_the_review(self):
        task = self.started()
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "api", ("server/**",))

    def test_a_quick_task_has_no_parts(self):
        task, _notes = flow.start(self.root, "오타", name="typo", scope=("web/page.js",), fast=True)
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "web", ("web/**",))

    def test_each_part_needs_its_own_files(self):
        task = self.ready()
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "api", ())
        flow.split(self.root, task.id, "web", ("web/**",))
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "pages", ("web/pages/**",))      # inside the scope of web
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "page", ("**/page.js",))         # a file of web
        with self.assertRaises(ValueError):
            flow.split(self.root, task.id, "web", ("docs/**",))             # the name is in use

    def test_a_part_changes_only_the_files_of_its_scope(self):
        task, api, web = self.two_parts()
        self.assertEqual(run(api, "git", "branch", "--show-current").strip(), "akasha/total--api")
        self.assertIsNone(self.stopped(api / "server" / "api.py"))
        self.assertIsNone(self.stopped(api / "server" / "new.py"))
        self.assertIn("outside the part api", self.stopped(api / "web" / "page.js"))
        self.assertIn("records", self.stopped(api / ".akasha" / "tasks" / task.id / "plan.md"))
        self.assertIn("only an administrator", self.stopped(api / "db" / "schema.sql"))
        self.assertIsNone(self.stopped(web / "web" / "page.js"))
        self.assertIsNone(guard._other_worktree(api / "server" / "api.py", self.root, all_local(self.root)))

    def test_join_merges_the_parts_and_the_landing_waits_for_it(self):
        task, api, web = self.two_parts()
        (api / "server" / "api.py").write_text("def total():\n    return 42\n", encoding="utf-8")
        (web / "web" / "page.js").write_text("export const a = 42;\n", encoding="utf-8")
        self.assertIn("did not join", land._ready(task))
        self.assertIn("akasha join", flow.next_step(task))
        self.assertEqual(flow.join(self.root, task.id), ["api", "web"])
        task, tree = load(self.root, task.id), Path(task.workcopy)
        self.assertEqual(task.parts, [])
        self.assertIn("42", (tree / "server" / "api.py").read_text(encoding="utf-8"))
        self.assertIn("42", (tree / "web" / "page.js").read_text(encoding="utf-8"))
        self.assertFalse(api.exists() or web.exists())
        self.assertNotIn("akasha/total--api", run(self.root, "git", "branch", "--list"))
        self.assertIn("akasha check", flow.next_step(task))

    def test_a_conflict_stops_the_join_with_the_files(self):
        task, api, _web = self.two_parts()
        tree = Path(task.workcopy)
        (api / "server" / "api.py").write_text("def total():\n    return 1\n", encoding="utf-8")
        (tree / "server" / "api.py").write_text("def total():\n    return 2\n", encoding="utf-8")
        with self.assertRaises(ValueError) as stop:
            flow.join(self.root, task.id)
        self.assertIn("server/api.py", str(stop.exception))
        self.assertIn("return 2", (tree / "server" / "api.py").read_text(encoding="utf-8"))
        self.assertEqual(len(load(self.root, task.id).parts), 2)

    def test_cancel_and_handoff_take_care_of_the_parts(self):
        task, api, web = self.two_parts()
        with self.assertRaises(ValueError):
            flow.handoff(self.root, task.id)
        self.assertIn("cancelled", flow.cancel(self.root, task.id, force=True))
        self.assertFalse(api.exists() or web.exists())


if __name__ == "__main__":
    unittest.main()
