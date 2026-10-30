import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from akasha import flow
from akasha.core import handover, workcopy
from akasha.core import task as tasks
from akasha.engine import hooks

PASS = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAIL = f'"{sys.executable}" -c "raise SystemExit(1)"'


def make_repo(tests_command: str) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="akasha-flow-"))
    run = lambda *args: subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (folder / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (folder / "akasha.toml").write_text(
        f'[checks]\nrequired = ["secrets", "tests"]\ntests = \'{tests_command}\'\n', encoding="utf-8")
    (folder / ".gitignore").write_text(".akasha/state/\n.akasha/work/\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "first")
    return folder


class FlowTests(unittest.TestCase):
    def test_a_request_goes_through_the_stages(self):
        root = make_repo(PASS)
        task, overlaps = flow.start(root, "Add a date filter", "ops-member")
        self.assertEqual((task.stage, overlaps), ("request", []))
        self.assertIn("completion conditions are not clear", flow.advance(root, task.id)[0])
        flow.specify(root, task.id, ["Filter by the transaction date"], ["Must hidden customers show?"], False)
        self.assertTrue(flow.advance(root, task.id))
        flow.specify(root, task.id, [], [], True)
        self.assertEqual(flow.advance(root, task.id), [])
        self.assertIn("requester did not approve", flow.advance(root, task.id)[0])
        flow.approve(root, task.id, "requester", "ops-member")
        self.assertEqual(flow.advance(root, task.id), [])
        task = tasks.load(root, task.id)
        self.assertEqual(task.stage, "build")
        work = Path(task.workcopy)
        self.assertTrue((work / "app.py").is_file())
        (work / "search.py").write_text("def search(date):\n    return date\n", encoding="utf-8")
        self.assertEqual(flow.advance(root, task.id), [])
        self.assertEqual(flow.check(root, task.id).status, {"secrets": "PASS", "tests": "PASS"})
        self.assertEqual(flow.advance(root, task.id), [])
        self.assertIn("did not accept", flow.advance(root, task.id)[0])
        flow.accept(root, task.id, None, True)
        self.assertEqual(flow.advance(root, task.id), [])
        task = tasks.load(root, task.id)
        self.assertEqual(task.stage, "handover")
        self.assertIn("search.py", handover.render(task, workcopy.changed_files(task)))
        with self.assertRaises(RuntimeError):            # no GitHub repository in this test
            flow.handover(root, task.id)

    def test_three_failed_checks_stop_the_task(self):
        root = make_repo(FAIL)
        task, _ = flow.start(root, "Fix the total", "ops-member", workflow="small")
        self.assertEqual(task.stage, "build")
        for _ in range(3):
            self.assertEqual(flow.check(root, task.id).status["tests"], "FAIL")
        task = tasks.load(root, task.id)
        self.assertEqual(task.status, "stopped")
        self.assertIn("A developer must examine the problem", task.notes[-1])

    def test_the_scope_stops_changes_outside_it(self):
        root = make_repo(PASS)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small", scope=["src/search/**"])
        (Path(task.workcopy) / "billing.py").write_text("x = 1\n", encoding="utf-8")
        self.assertIn("outside the task scope", flow.advance(root, task.id)[0])


class HookTests(unittest.TestCase):
    def test_hooks_stop_unsafe_work(self):
        root = make_repo(PASS)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(hooks.before_tool(root, root, "Bash", {"command": "git push --force"}), 2)
            self.assertEqual(hooks.before_tool(root, root, "Bash", {"command": "git status"}), 0)
            self.assertEqual(hooks.before_tool(root, root, "Edit", {"file_path": str(root / "app.py")}), 2)
            inside = Path(task.workcopy) / "app.py"
            self.assertEqual(hooks.before_tool(root, root, "Edit", {"file_path": str(inside)}), 0)
            inside.write_text("KEY = 'sk-" + "c" * 24 + "'\n", encoding="utf-8")
            self.assertEqual(hooks.after_tool(root, "Write", {"file_path": str(inside)}), 2)

    def test_session_start_without_a_team_config(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-plain-"))
        subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"cwd": str(folder)}))), redirect_stdout(output):
            self.assertEqual(hooks.main("claude", "SessionStart"), 0)
        self.assertIn("Set up Akasha", output.getvalue())


if __name__ == "__main__":
    unittest.main()
