"""A quick task: a small change of existing files that no other area uses. Akasha decides from what the change
touches, not from its size. Real git repositories, without GitHub."""

import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from akasha import approval, config, flow, land, quick, review
from akasha.task import load
from tests.helpers import Repository, run

SHARED = {"lib/button.js": "export const label = 'Save';\n",
          "pages/a/view.js": "import { label } from '../../lib/button';\n",
          "pages/b/view.js": "import { label } from '../../lib/button';\n",
          "pages/c/title.py": "TITLE = 'Monthly totl'\n",
          "pages/c/style.css": ".title { color: red; }\n",
          "README.md": "# Ap\n"}
QUIET = {key: "" for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE")}


class QuickTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        for name, text in SHARED.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "pages")
        run(self.root, "git", "push", "-q", "origin", "main")
        for name, patcher in (("browser", patch("webbrowser.open")), ("env", patch.dict(os.environ, QUIET))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.repo.close()

    def started(self, name="typo", scope=("pages/c/title.py",)):
        task, notes = flow.start(self.root, "오타 고치기", name=name, scope=scope, fast=True)
        self.assertEqual(task.kind, "quick")
        return task, notes

    def records(self, task) -> Path:
        return Path(task.workcopy) / ".akasha" / "tasks" / task.id

    def edit(self, task, name, text):
        (Path(task.workcopy) / name).write_text(text, encoding="utf-8")

    def mark(self, task, verdict="PASS"):
        return review.on_subagent_stop(self.root, {
            "agent_type": "akasha-reviewer",
            "last_assistant_message": f"AKASHA-REVIEW: {task.id} {quick.digest(load(self.root, task.id))} {verdict}"})

    def problems(self, task, team=None):
        tree = Path(task.workcopy)
        return quick.problems(team or flow.rules(self.root), tree, quick.base(tree))

    def ready(self):
        """A typo fixed, impact.md written, the change reviewed, shown, and approved by the person."""
        task, _notes = self.started()
        self.assertIn("Make the change", flow.next_step(task))
        self.assertEqual(flow.gate(task), "")                  # a quick task changes its code first
        self.edit(task, "pages/c/title.py", "TITLE = 'Monthly total'\n")
        self.assertIn("impact.md", flow.next_step(load(self.root, task.id)))
        (self.records(task) / "impact.md").write_text("- pages/c/title.py: only the page c uses it\n",
                                                      encoding="utf-8")
        with self.assertRaises(ValueError):
            flow.preview(self.root, task.id)                   # the reviewer did not pass it yet
        self.assertIn("akasha-reviewer", flow.next_step(load(self.root, task.id)))
        self.assertIn("gave PASS to the change", self.mark(task))
        flow.preview(self.root, task.id)
        task = load(self.root, task.id)
        self.assertEqual(quick.shown_change(task), quick.digest(task))
        self.assertIn('id="akasha-decisions"', (self.records(task) / "preview.html").read_text(encoding="utf-8"))
        self.assertIn("Wait for the message", flow.next_step(task))
        approval.on_prompt(self.root, Path(task.workcopy), "좋아요")
        _task, message = flow.approve(self.root, task.id)
        self.assertIn("akasha check", message)
        return load(self.root, task.id)

    def test_a_typo_in_a_file_of_one_area_is_quick_and_lands(self):
        task = self.ready()
        self.assertEqual(task.approval["change_sha"], quick.digest(task))
        self.assertEqual(quick.missing(flow.rules(self.root), task), "")
        result, _notes = flow.check(self.root, task.id)
        self.assertEqual(result.status[flow.QUICK], "PASS")
        (self.records(task) / "summary.md").write_text("## Why\n", encoding="utf-8")
        self.assertIn("akasha check", land._ready(load(self.root, task.id)))   # the summary came after the check
        flow.check(self.root, task.id)
        self.assertEqual(land._ready(load(self.root, task.id)), "")           # every rule of the task passed

    def test_one_line_of_a_button_that_many_screens_use_is_not_quick(self):
        task, notes = self.started(name="button", scope=("lib/button.js",))
        self.assertTrue(any(line.startswith("not quick") for line in notes))
        self.edit(task, "lib/button.js", "export const label = 'Save';\nexport const size = 2;\n")   # only a new line
        found = self.problems(task)
        self.assertTrue(any("lib/button.js" in item and "other areas" in item for item in found), found)
        (self.records(task) / "impact.md").write_text("- lib/button.js\n", encoding="utf-8")
        result, _notes = flow.check(self.root, task.id)
        self.assertEqual(result.status[flow.QUICK], "FAIL")
        self.assertIn("akasha upgrade", result.details[flow.QUICK])
        with self.assertRaises(ValueError):
            flow.preview(self.root, task.id)

    def test_an_administrator_has_the_same_rules(self):
        team = replace(flow.rules(self.root), admins=("tester",), own_procedure=("tester",))
        task, _notes = self.started(name="admin", scope=("lib/button.js",))
        self.edit(task, "lib/button.js", "export const label = 'Store';\n")
        self.assertTrue(self.problems(task, team))

    def test_a_new_or_deleted_file_is_not_quick(self):
        task, _notes = self.started(name="new-page")
        self.edit(task, "pages/c/new.py", "X = 1\n")
        (Path(task.workcopy) / "pages/c/title.py").unlink()
        found = self.problems(task)
        self.assertTrue(any("pages/c/new.py: a new file" in item for item in found), found)
        self.assertTrue(any("pages/c/title.py: a deleted file" in item for item in found), found)

    def test_a_risky_path_is_not_quick(self):
        task, _notes = self.started(name="schema", scope=("db/schema.sql",))
        self.edit(task, "db/schema.sql", "create table a (x bigint);\n")
        self.assertTrue(any("only an administrator" in item for item in self.problems(task)))

    def test_a_kind_of_file_without_imports_needs_quick_paths(self):
        task, _notes = self.started(name="style", scope=("pages/c/style.css",))
        self.edit(task, "pages/c/style.css", ".title { color: blue; }\n")
        self.assertTrue(any("cannot tell" in item for item in self.problems(task)))
        team = replace(flow.rules(self.root), quick_paths=("pages/*/*.css",))
        self.assertEqual(self.problems(task, team), [])

    def test_text_for_people_is_quick(self):
        task, _notes = self.started(name="readme", scope=("README.md",))
        self.edit(task, "README.md", "# App\n")
        self.assertEqual(self.problems(task), [])

    def test_a_change_after_the_approval_needs_the_review_and_the_approval_again(self):
        task = self.ready()
        self.edit(task, "pages/c/title.py", "TITLE = 'Monthly totals'\n")
        task = load(self.root, task.id)
        self.assertIn("akasha-reviewer", quick.missing(flow.rules(self.root), task))
        self.mark(task)
        self.assertIn("did not approve", quick.missing(flow.rules(self.root), load(self.root, task.id)))
        self.assertIn("akasha preview", flow.next_step(load(self.root, task.id)))
        self.assertIn("did not approve", land._ready(load(self.root, task.id)))

    def test_an_approval_of_an_older_change_is_refused(self):
        task, _notes = self.started()
        self.edit(task, "pages/c/title.py", "TITLE = 'Monthly total'\n")
        (self.records(task) / "impact.md").write_text("- pages/c/title.py\n", encoding="utf-8")
        self.mark(task)
        flow.preview(self.root, task.id)
        self.edit(task, "pages/c/title.py", "TITLE = 'Weekly total'\n")       # after the person saw it
        approval.on_prompt(self.root, Path(task.workcopy), "좋아요")
        with self.assertRaises(ValueError):
            flow.approve(self.root, task.id)

    def test_upgrade_makes_a_full_task_and_keeps_the_change(self):
        task = self.ready()
        task = flow.upgrade(self.root, task.id)
        self.assertEqual((task.kind, task.status, task.approval, task.review), ("full", "preview", {}, {}))
        self.assertIn("approve", flow.gate(task))
        self.assertFalse((self.records(task) / "preview.html").exists())
        self.assertIn("total", (Path(task.workcopy) / "pages/c/title.py").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            flow.upgrade(self.root, task.id)


class ServerTests(unittest.TestCase):
    """The server check examines each pull request whose records have impact.md."""

    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        for name, text in SHARED.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "pages")
        run(self.root, "git", "push", "-q", "origin", "main")
        run(self.root, "git", "checkout", "-q", "-b", "akasha/fix")
        self.team = flow.rules(self.root)

    def tearDown(self):
        self.repo.close()

    def pull_request(self, files: dict[str, str]) -> list[str]:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "change")
        return run(self.root, "git", "diff", "--name-only", "origin/main...HEAD").split()

    def test_a_pull_request_without_impact_md_has_no_quick_check(self):
        changed = self.pull_request({"lib/button.js": "export const label = 'Store';\n"})
        self.assertIsNone(quick.server(self.team, self.root, "origin/main", changed))

    def test_a_quick_task_that_changes_a_shared_file_fails(self):
        changed = self.pull_request({".akasha/tasks/fix/impact.md": "- button\n",
                                     "lib/button.js": "export const label = 'Store';\n"})
        status, detail = quick.server(self.team, self.root, "origin/main", changed)
        self.assertEqual(status, "FAIL")
        self.assertIn("lib/button.js", detail)

    def test_a_quick_task_of_one_area_passes(self):
        changed = self.pull_request({".akasha/tasks/fix/impact.md": "- title\n",
                                     "pages/c/title.py": "TITLE = 'Monthly total'\n"})
        self.assertEqual(quick.server(self.team, self.root, "origin/main", changed), ("PASS", ""))


class ConfigTests(unittest.TestCase):
    def test_quick_paths(self):
        team = config.parse('[quick]\npaths = ["pages/*/*.css", "config/"]\n')
        self.assertEqual(team.quick_paths, ("pages/*/*.css", "config/**"))
        self.assertEqual(config.parse("").quick_paths, ())


if __name__ == "__main__":
    unittest.main()
