import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha.config import Team
from akasha.core.task import Task
from akasha.validators import guard, langs, runner, secrets


class GuardTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "project"
        (self.root / "src").mkdir(parents=True)

    def stop(self, line: str) -> str | None:
        return guard.check_command(line, self.root, self.root)

    def test_commands_that_cannot_be_undone_are_stopped(self):
        for line in ("git push --force origin main", "git push -f", "git push origin +main",
                     "git push --force-with-lease", "git push origin --delete main", "git push origin :master",
                     "git branch -D main", "rm -rf /", "rm -rf ..", "rm -rf ~", f"rm -rf {self.root}",
                     "Remove-Item -Recurse -Force C:\\Windows", "git status && git push -f",
                     'rm -rf "$HOME/Documents"', "rm -rf $HOME", 'Remove-Item -Recurse "$env:USERPROFILE\\Documents"',
                     "rd /s /q %USERPROFILE%", "cd .. && rm -rf project", "git push -fu origin main",
                     "git push origin -d main", "git push \\\n--force origin main", "sleep 1 & rm -rf ~",
                     "git push origin main", "git push origin HEAD:main", "git push origin HEAD:refs/heads/master"):
            with self.subTest(line=line):
                self.assertIsNotNone(self.stop(line))

    def test_usual_commands_pass(self):
        for line in ("git push origin feature-x", "git status", "rm -rf src/build", "rm file.txt",
                     "python -m pytest -q", "git branch -D akasha/old-task", "echo push --force",
                     "git push -u origin feature-x", "git push", "cd src && ls", "npm test 2>&1",
                     "gh pr view 7", "gh issue comment 5 --body 'Write /approve spec r2 when the plan is correct'",
                     "gh issue create --title x --body '/approve'", "gh api repos/team/app/pulls/7"):
            with self.subTest(line=line):
                self.assertIsNone(self.stop(line))

    def test_shared_state_is_for_akasha_github_and_people(self):
        work = self.root / ".akasha" / "work" / "t-1"
        work.mkdir(parents=True)
        (self.root / "note.md").write_text("Looks good.\n/accept 1 r2\n", encoding="utf-8")
        for line in ("git push origin akasha/date-filter", "git push -u origin HEAD:akasha/date-filter",
                     "git push origin HEAD:refs/heads/akasha-wip/t-1", "git push origin --delete akasha/t-1",
                     "git push origin :akasha-wip/t-1", "git push --all origin", "git push --mirror origin",
                     "gh pr merge 7 --squash", "gh pr merge --auto 7", "gh api -X PUT repos/team/app/pulls/7/merge",
                     'gh issue comment 5 --body "/approve spec r2"', "gh pr comment 7 -b '/accept all r2'",
                     "gh issue comment 5 --body-file note.md", "gh issue comment 5 -F - <<'EOF'\n/resume\nEOF",
                     'echo "/cancel not needed" | gh issue comment 5 -F -',
                     "gh api repos/team/app/issues/5/comments -f body='/Reject 1 r2 too slow'",
                     "gh api repos/team/app/issues/5/comments -F body=@note.md"):
            with self.subTest(line=line):
                self.assertIsNotNone(self.stop(line))
        for line in ("git push", "git push origin", "git push -u origin HEAD"):        # in the work copy of a task
            with self.subTest(line=line):
                self.assertIsNotNone(guard.check_command(line, work, self.root))
                self.assertIsNone(guard.check_command("git push origin feature-x", work, self.root))

    def test_edits_go_into_the_work_copy_of_an_active_task(self):
        work = self.root / ".akasha" / "work" / "t-1"
        task = Task(id="t-1", title="x", workflow="feature", stage="build", workcopy=str(work))
        self.assertIsNone(guard.check_edit(self.root / "src" / "a.py", self.root, [task]))     # handed off: no copy
        work.mkdir(parents=True)
        self.assertIsNotNone(guard.check_edit(self.root / "src" / "a.py", self.root, [task]))
        self.assertIsNone(guard.check_edit(work / "src" / "a.py", self.root, [task]))
        self.assertIsNone(guard.check_edit(self.root / "src" / "a.py", self.root, []))
        task.stage = "inspection"
        self.assertIsNone(guard.check_edit(self.root / "src" / "a.py", self.root, [task]))


class CheckTests(unittest.TestCase):
    def test_secret_patterns(self):
        key = "sk-" + "a" * 24
        self.assertEqual(secrets.find(f"API = '{key}'\nx = 1"), [(1, "OpenAI or Anthropic key")])
        self.assertEqual(secrets.find("token = os.environ['TOKEN']"), [])

    def test_runner_pass_fail_and_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "config.py").write_text("TOKEN = 'ghp_" + "b" * 36 + "'\n", encoding="utf-8")
            team = Team(required_checks=("secrets", "tests", "lint"),
                        commands={"tests": f'"{sys.executable}" -c "raise SystemExit(0)"'})
            result = runner.run(team, work, ["config.py"])
            self.assertEqual(result.status, {"secrets": "FAIL", "tests": "PASS", "lint": "SKIP"})
            self.assertIn("config.py:1 GitHub token", result.details["secrets"])
            failing = Team(required_checks=("tests",), commands={"tests": f'"{sys.executable}" -c "raise SystemExit(3)"'})
            self.assertEqual(runner.run(failing, work, []).status, {"tests": "FAIL"})

    def test_a_timeout_stops_the_command_and_its_children(self):
        child = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'import time; time.sleep(60)'])"
        hung = Team(required_checks=("tests",), commands={"tests": f'"{sys.executable}" -c "{child}"'})
        with tempfile.TemporaryDirectory() as folder, patch.object(runner, "TIMEOUT_SECONDS", 2):
            started = time.monotonic()
            result = runner.run(hung, Path(folder), [])
        self.assertEqual(result.status, {"tests": "FAIL"})
        self.assertIn("did not stop", result.details["tests"])
        self.assertLess(time.monotonic() - started, 20)

    def test_language_detection(self):
        self.assertEqual({pack.name for pack in langs.packs()}, {"python", "typescript", "go", "java"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
            self.assertEqual([pack.name for pack in langs.detect(root)], ["python"])


if __name__ == "__main__":
    unittest.main()
