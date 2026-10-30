import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from akasha import config, flow, setup
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
        task = flow.resume(root, task.id, "dev-a")
        self.assertEqual((task.status, task.failures), ("open", 0))

    def test_the_scope_stops_changes_outside_it(self):
        root = make_repo(PASS)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small", scope=["src/search/**"])
        (Path(task.workcopy) / "billing.py").write_text("x = 1\n", encoding="utf-8")
        self.assertIn("outside the task scope", flow.advance(root, task.id)[0])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(hooks.turn_end(root), 0)
        self.assertIn("billing.py", json.loads(output.getvalue())["systemMessage"])

    def test_the_handover_pushes_and_opens_one_pull_request(self):
        root = make_repo(PASS)
        remote = Path(tempfile.mkdtemp(prefix="akasha-remote-"))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main"], cwd=remote, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True, capture_output=True)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        (Path(task.workcopy) / "search.py").write_text("x = 1\n", encoding="utf-8")
        flow.advance(root, task.id)
        flow.check(root, task.id)
        flow.advance(root, task.id)
        opened = subprocess.CompletedProcess([], 0, "https://github.com/team/app/pull/7\n", "")
        with patch("akasha.flow.github.repository", return_value=("team/app", "main")), \
                patch("akasha.flow.github.status", return_value=[]), patch("akasha.flow.gh", return_value=opened) as gh:
            self.assertEqual(flow.handover(root, task.id), ("https://github.com/team/app/pull/7", []))
            self.assertEqual(tasks.load(root, task.id).status, "done")
            (Path(task.workcopy) / "search.py").write_text("x = 2\n", encoding="utf-8")
            flow.handover(root, task.id)                  # a review change goes to the same pull request
        self.assertEqual([call.args[1:3] for call in gh.call_args_list], [("pr", "create")])
        pushed = workcopy.git(remote, "rev-parse", task.branch).stdout
        self.assertEqual(pushed, workcopy.git(Path(task.workcopy), "rev-parse", "HEAD").stdout)

    def test_the_setup_command_runs_in_a_new_copy_and_in_ci(self):
        root = make_repo(PASS)
        with (root / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write(f"setup = '{FAIL}'\n")
        self.assertEqual(flow.ci_check(root, None, "HEAD").status, {"setup": "FAIL"})
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        self.assertIn("setup command failed", task.notes[0])

    def test_a_wider_scope_finds_overlaps(self):
        root = make_repo(PASS)
        first, _ = flow.start(root, "Change the search", "ops-a", scope=["src/search/**"])
        second, found = flow.start(root, "Add a date filter", "ops-b")
        self.assertEqual(found, [])
        _task, found = flow.specify(root, second.id, [], [], False, ["src/search/date.py"])
        self.assertEqual([(item.kind, item.other) for item in found], [("order", first.id)])

    def test_a_developer_approval_needs_a_developer_from_the_team_config(self):
        root = make_repo(PASS)
        with (root / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write('[roles]\ndevelopers = ["dev-a"]\n')
        task, _ = flow.start(root, "Change the totals", "ops-member")
        with self.assertRaises(ValueError):
            flow.approve(root, task.id, "developer", "ops-member")
        self.assertEqual(flow.approve(root, task.id, "developer", "dev-a").approvals, {"developer": "dev-a"})

    def test_setup_writes_a_team_config_that_loads(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-setup-"))
        subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
        report = setup.run(folder, "")
        self.assertIn("Akasha wrote akasha.toml", report[0])
        self.assertEqual(config.load(folder).required_checks, ("secrets",))
        self.assertIn("akasha:start", (folder / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn(".akasha/work/", (folder / ".gitignore").read_text(encoding="utf-8"))


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
        self.assertIn("akasha-setup", output.getvalue())
        self.assertIn("Akasha command:", output.getvalue())

    def test_session_start_shows_the_team_context(self):
        root = make_repo(PASS)
        (root / ".akasha" / "context").mkdir(parents=True)
        (root / ".akasha" / "context" / "decisions.md").write_text("# Decisions\n", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            hooks.session_start(root)
        self.assertIn(".akasha/context/decisions.md", output.getvalue())


if __name__ == "__main__":
    unittest.main()
