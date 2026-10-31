import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha.config import Check, Team
from akasha.core.task import Task
from akasha.validators import guard, langs, runner, secrets


def python(code: str) -> str:
    """A check command that runs Python code. It is correct for cmd.exe and for /bin/sh."""
    return f'"{sys.executable}" -c "{code}"'


PASS = python("raise SystemExit(0)")


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
                     "gh issue create --title x --body '/approve'", "gh api repos/team/app/pulls/7",
                     "cd src && git push", "git -C src push", "GH_REPO=team/app gh pr view 7", "env CI=1 npm test",
                     "gh issue edit 5 --add-label bug", "gh api repos/team/app/issues/comments/123",
                     "gh api repos/team/app/issues/5"):
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
                     "gh api repos/team/app/issues/5/comments -F body=@note.md",
                     "cd .akasha/work/t-1 && git push", "git -C .akasha/work/t-1 push -u origin HEAD",
                     'GH_REPO=o/r gh issue comment 5 --body "/approve spec r2"', "GH_REPO=team/app gh pr merge 5",
                     "gh -R team/app pr merge 5 --squash", "env GH_REPO=team/app gh pr merge 5",
                     'gh --repo team/app issue comment 5 --body "/approve spec r1"',
                     "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { x } }'",
                     "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) { x } }'",
                     "gh api -X DELETE repos/team/app/issues/comments/123",
                     "gh api --method PATCH repos/team/app/issues/comments/123 -f body=ok",
                     "gh api graphql -f query='mutation { minimizeComment(input: {subjectId: \"x\"}) { x } }'",
                     "gh api graphql -f query='mutation { updateIssue(input: {id: \"x\", body: \"\"}) { x } }'",
                     "gh issue comment 5 --edit-last --body ok", "gh issue edit 5 --body-file note.md",
                     "gh issue edit 5 -b x", "gh api -X PATCH repos/team/app/issues/5 -f state=closed",
                     "gh pr create --head feature-x --label akasha-merge --fill", "gh pr create -l bug,akasha-merge",
                     "gh pr edit 7 --add-label akasha-merge", "gh issue edit 7 --add-label=Akasha-Merge",
                     "gh api repos/team/app/issues/7/labels -f 'labels[]=akasha-merge'",
                     "gh api graphql -f query='mutation { addLabelsToLabelable(input: {}) { x } }'",
                     "gh pr review 7 --approve", "gh pr review 7 -a -b ok", "gh -R team/app pr review 7 --approve",
                     "gh api repos/team/app/pulls/7/reviews -f event=APPROVE",
                     "gh api graphql -f query='mutation { addPullRequestReview(input: {event: APPROVE}) { x } }'"):
            with self.subTest(line=line):
                self.assertIsNotNone(self.stop(line))
        for line in ("git push", "git push origin", "git push -u origin HEAD"):        # in the work copy of a task
            with self.subTest(line=line):
                self.assertIsNotNone(guard.check_command(line, work, self.root))
                self.assertIsNone(guard.check_command("git push origin feature-x", work, self.root))
        for line in ("git stash push -m wip", "git stash push -- src/a.py", "git commit -m push", "git -C . stash push",
                     "gh pr create --label bug --fill", "gh pr edit 7 --add-label akasha-merged",
                     "gh pr review 7 --comment -b 'looks ok'", "gh pr review 7 --request-changes -b 'see the test'",
                     "gh api repos/team/app/pulls/7/reviews"):                       # not an approval
            with self.subTest(line=line):
                self.assertIsNone(guard.check_command(line, work, self.root))

    def test_the_guard_uses_the_names_of_work_in_the_team_config(self):
        team = Team(work_dir="tools/worktrees", branch_prefix="feat/", wip_prefix="wip/")
        work = self.root / "tools" / "worktrees" / "t-1"
        work.mkdir(parents=True)
        for line in ("git push origin feat/t-1", "git push origin HEAD:refs/heads/wip/t-1",
                     "git push origin --delete feat/t-1", "git push origin akasha/t-1",     # also the default prefixes
                     "git push origin akasha-wip/t-1"):
            with self.subTest(line=line):
                self.assertIsNotNone(guard.check_command(line, self.root, self.root, team))
        for line in ("git push", "git push -u origin HEAD"):                              # in its work copy
            with self.subTest(line=line):
                self.assertIsNotNone(guard.check_command(line, work, self.root, team))
        self.assertIsNone(guard.check_command("git push origin feature-x", work, self.root, team))
        self.assertIsNone(guard.check_command("git push origin feat/t-1", self.root, self.root))    # not a task branch

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
                        checks={"tests": Check(python("raise SystemExit(0)"))})
            result = runner.run(team, work, ["config.py"])
            self.assertEqual(result.status, {"secrets": "FAIL", "tests": "PASS", "lint": "SKIP"})
            self.assertIn("config.py:1 GitHub token", result.details["secrets"])
            failing = Team(required_checks=("tests",), checks={"tests": Check(python("raise SystemExit(3)"))})
            self.assertEqual(runner.run(failing, work, []).status, {"tests": "FAIL"})

    def test_not_needed_is_a_pass_and_skip_is_not(self):
        self.assertTrue(runner.passed({"secrets": "PASS", "front": "NOT_NEEDED"}))
        for status in ({}, {"secrets": "PASS", "lint": "SKIP"}, {"secrets": "FAIL", "front": "NOT_NEEDED"}):
            with self.subTest(status=status):
                self.assertFalse(runner.passed(status))

    def test_a_check_runs_only_when_the_change_touches_its_files(self):
        team = Team(required_checks=("pytest",), checks={"pytest": Check(PASS, only_when=("**/*.py", "tests/**"))})
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            for changed, status in ((["docs/guide.md"], "NOT_NEEDED"), ([], "NOT_NEEDED"), (["app.py"], "PASS"),
                                    (["src/app/main.py"], "PASS"), (["tests/data.json"], "PASS"),
                                    (["requirements-dev.txt"], "PASS"), (["web/package.json"], "PASS"),
                                    (["akasha.toml"], "PASS"), ([".github/workflows/deploy.yml"], "PASS")):
                with self.subTest(changed=changed):          # the files of run_all_when run each check
                    self.assertEqual(runner.run(team, work, changed).status, {"pytest": status})
            quiet = Team(required_checks=("pytest",), checks=team.checks, run_all_when=())
            result = runner.run(quiet, work, ["requirements.txt"])
            self.assertEqual(result.status, {"pytest": "NOT_NEEDED"})
            self.assertIn("only_when: **/*.py, tests/**", result.details["pytest"])

    def test_a_check_runs_in_its_folder(self):
        where = python("import os; print(os.path.basename(os.getcwd()))")
        team = Team(required_checks=("front", "mobile"),
                    checks={"front": Check(where, cwd="frontend/app"), "mobile": Check(where, cwd="mobile")})
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "frontend" / "app").mkdir(parents=True)
            result = runner.run(team, work, ["frontend/app/main.ts"])
        self.assertEqual(result.status, {"front": "PASS", "mobile": "FAIL"})          # no traceback
        self.assertEqual(result.details["front"], "app")
        self.assertIn("the folder mobile of the check mobile does not exist", result.details["mobile"])

    def test_command_windows_replaces_the_command_on_windows(self):
        say = lambda word: python(f"print({word!r})")  # noqa: E731
        both = Team(required_checks=("build",), checks={"build": Check(say("posix"), command_windows=say("windows"))})
        one = Team(required_checks=("build",), checks={"build": Check(say("posix"))})
        with tempfile.TemporaryDirectory() as folder:
            for windows, team, word in ((True, both, "windows"), (False, both, "posix"), (True, one, "posix")):
                with self.subTest(windows=windows, word=word), patch.object(runner, "WINDOWS", windows):
                    self.assertEqual(runner.run(team, Path(folder), []).details["build"], word)

    def test_output_in_the_code_page_of_the_computer_is_read_in_utf8_mode(self):
        korean = "테스트 실패"
        self.assertEqual(runner._decode(korean.encode("utf-8")), korean)
        with patch("locale.getpreferredencoding", return_value="utf-8"), \
                patch("locale.getencoding", return_value="cp949"):     # Python -X utf8 on a Korean Windows
            self.assertEqual(runner._decode(korean.encode("cp949")), korean)

    def test_a_timeout_stops_the_command_and_its_children(self):
        child = "import subprocess, sys; subprocess.run([sys.executable, '-c', 'import time; time.sleep(60)'])"
        hung = Team(required_checks=("tests",), checks={"tests": Check(python(child))})
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
