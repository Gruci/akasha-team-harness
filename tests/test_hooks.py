"""The hooks as Claude Code and Codex run them: a payload on the standard input, and the exit code and output."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from akasha import flow, hooks, setup
from akasha.task import load
from tests.helpers import Repository


class HookTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        patcher = patch("webbrowser.open")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.repo.close()

    def hook(self, event: str, payload: dict) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        payload = {"cwd": str(self.root), **payload}
        with patch("akasha.hooks._payload", return_value=payload), redirect_stdout(out), redirect_stderr(err):
            code = hooks.main("claude", event)
        return code, out.getvalue(), err.getvalue()

    def test_a_dangerous_command_stops(self):
        code, _out, err = self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git push -f"}})
        self.assertEqual(code, 2)
        self.assertIn("force push", err)
        code, _out, _err = self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status"}})
        self.assertEqual(code, 0)

    def test_the_main_checkout_is_closed_and_a_task_waits_for_its_approval(self):
        code, _out, err = self.hook("PreToolUse", {"tool_name": "Edit",
                                                   "tool_input": {"file_path": str(self.root / "app.py")}})
        self.assertEqual(code, 2)
        self.assertIn("akasha start", err)
        task, _notes = flow.start(self.root, "Title", name="t1")
        code, _out, err = self.hook("PreToolUse", {"tool_name": "Write",
                                                   "tool_input": {"file_path": str(Path(task.workcopy) / "app.py")}})
        self.assertEqual(code, 2)
        self.assertIn("did not approve", err)

    def test_the_prompt_of_the_person_approves_the_shown_preview(self):
        task, _notes = flow.start(self.root, "Title", name="t2")
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>x</html>", encoding="utf-8")
        flow.preview(self.root, task.id)
        code, out, _err = self.hook("UserPromptSubmit", {"prompt": "승인"})
        self.assertEqual(code, 0)
        self.assertIn("approved the preview", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(load(self.root, task.id).approval["source"], "prompt")

    def test_the_hook_reads_utf8_without_the_utf8_mode_of_python(self):
        """A real run: `akasha hook` of pip, without -X utf8, read "승인" in cp949 on Windows (2026-10-31)."""
        task, _notes = flow.start(self.root, "Title", name="t4")
        records = Path(task.workcopy) / ".akasha" / "tasks" / task.id
        (records / "preview.html").write_text("<html>x</html>", encoding="utf-8")
        flow.preview(self.root, task.id)
        env = {**os.environ, "PYTHONUTF8": "0", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        env.pop("PYTHONIOENCODING", None)
        payload = json.dumps({"cwd": str(self.root), "prompt": "승인"}, ensure_ascii=False).encode("utf-8")
        done = subprocess.run([sys.executable, "-m", "akasha", "hook", "--event", "UserPromptSubmit"], input=payload,
                              cwd=self.root, env=env, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("approved the preview", done.stdout.decode("utf-8"))
        self.assertEqual(load(self.root, task.id).approval["words"], "승인")

    def test_a_secret_key_goes_back_to_the_agent(self):
        path = Path(self.repo.folder.name) / "notes.txt"
        path.write_text("token = ghp_" + "a" * 36 + "\n", encoding="utf-8")
        code, _out, err = self.hook("PostToolUse", {"tool_name": "Write", "tool_input": {"file_path": str(path)}})
        self.assertEqual(code, 2)
        self.assertIn("GitHub token", err)

    def test_session_start_tells_the_steps_and_the_tasks(self):
        flow.start(self.root, "Title", name="t3")
        code, out, _err = self.hook("SessionStart", {})
        self.assertEqual(code, 0)
        self.assertIn("Each change of this repository is an Akasha task", out)
        self.assertIn("Your task t3", out)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(team="")
        self.root = self.repo.root

    def tearDown(self):
        self.repo.close()

    def test_setup_writes_each_file_once(self):
        lines = setup.run(self.root)
        written = "\n".join(lines)
        for name in ("akasha.toml", ".github/workflows/akasha.yml", ".github/pull_request_template.md", "AGENTS.md",
                     ".codex/hooks.json", ".claude/settings.json"):
            self.assertIn(name, written)
            self.assertTrue((self.root / name).is_file(), name)
        self.assertIn("akasha setup --apply", written)
        self.assertEqual(setup.run(self.root), ["the files of Akasha are up to date"])

    def test_the_hooks_wait_until_the_setup_merged(self):
        setup.run(self.root)
        out = io.StringIO()
        payload = {"cwd": str(self.root), "tool_name": "Edit", "tool_input": {"file_path": str(self.root / "a.py")}}
        with patch("akasha.hooks._payload", return_value=payload), redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(hooks.main("claude", "PreToolUse"), 0)

    def test_a_setup_after_the_first_one_writes_into_the_work_copy_of_a_task(self):
        setup.run(self.root)
        for args in (("add", "-A"), ("commit", "-q", "-m", "setup"), ("push", "-q", "origin", "main")):
            subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        task, _notes = flow.start(self.root, "Rules", name="rules")
        tree = Path(task.workcopy)
        (tree / ".claude" / "settings.json").unlink()
        lines = setup.run(tree)
        self.assertTrue((tree / ".claude" / "settings.json").is_file())
        self.assertIn("work copy of the task", lines[-1])

    def test_doctor_names_each_problem(self):
        found = dict((text, good) for good, text in setup.doctor(self.root))
        self.assertTrue(any(text.startswith("Python") and good for text, good in found.items()))
        self.assertTrue(any(text.startswith("origin on GitHub") and not good for text, good in found.items()))


if __name__ == "__main__":
    unittest.main()
