import unittest
from pathlib import Path

from akasha.guard import check_command, check_edit
from akasha.task import Task
from tests.helpers import Repository, run


class CommandTests(unittest.TestCase):
    root = Path.cwd()

    def stopped(self, line: str) -> bool:
        return check_command(line, self.root, self.root) is not None

    def test_stops_what_cannot_be_undone_or_goes_around_akasha(self):
        for line in ("git push --force", "git push -fu origin x", "git push origin +x", "git push origin main",
                     "git push origin HEAD:main", "git push origin --delete main", "git push origin :main",
                     "git branch -D main", "gh pr merge 5 --squash", "gh api repos/a/b/pulls/5/merge -X PUT",
                     "gh pr review 5 --approve", "rm -rf /", "rm -rf ~", "rm -rf $HOME/x",
                     "cd .. && rm -rf build", "echo x > .akasha/state/tasks/a.json"):
            with self.subTest(line=line):
                self.assertTrue(self.stopped(line))

    def test_lets_the_usual_work_run(self):
        for line in ("git status", "git push origin akasha/x", "git commit -m main", "gh pr view 5", "gh pr list",
                     "rm -rf build", "python -m pytest", "cat .akasha/state/tasks/a.json", "git log main",
                     "git commit -C HEAD"):
            with self.subTest(line=line):
                self.assertFalse(self.stopped(line))


class CurrentBranchTests(unittest.TestCase):
    """A push without a branch name, in the main checkout on main, went to main (audit F12)."""

    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root

    def tearDown(self):
        self.repo.close()

    def test_a_push_of_the_current_branch_is_examined(self):
        for line in ("git push", "git push origin", "git push origin HEAD", "git push origin @", "git -C . push",
                     "git push --all", "cd x && git push", "git worktree add worktrees/x -b x"):
            with self.subTest(line=line):
                self.assertIsNotNone(check_command(line, self.root, self.root))
        run(self.root, "git", "switch", "-q", "-c", "akasha/x")
        for line in ("git push", "git push -u origin HEAD", f"git -C {self.root.as_posix()} push"):
            with self.subTest(line=line):
                self.assertIsNone(check_command(line, self.root, self.root))

    def test_a_work_copy_outside_akasha_is_closed(self):
        """A git worktree in an ignored folder went around the approval and the review (audit F04)."""
        (self.root / ".gitignore").write_text(".akasha/state/\n.akasha/work/\nworktrees/\n", encoding="utf-8")
        inner, outer = self.root / "worktrees" / "x", Path(self.repo.folder.name) / "outer"
        run(self.root, "git", "worktree", "add", "-q", "-b", "x", str(inner))
        run(self.root, "git", "worktree", "add", "-q", "-b", "y", str(outer))
        for path in (inner / "app.py", outer / "app.py"):
            with self.subTest(path=path):
                found = check_edit(path, self.root, [], True, lambda task: "")
                self.assertIn("not an Akasha task", found or "")
        self.assertIsNone(check_edit(inner / "app.py", self.root, [Task(id="x", title="X", workcopy=str(inner))],
                                     True, lambda task: ""))


class EditTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        self.work = self.root / ".akasha" / "work" / "t1"
        self.work.mkdir(parents=True)
        self.task = Task(id="t1", title="T", workcopy=str(self.work))

    def tearDown(self):
        self.repo.close()

    def edit(self, path: Path, ready: str = "", set_up: bool = True):
        return check_edit(path, self.root, [self.task], set_up, lambda task: ready)

    def test_secret_files_and_the_state_of_akasha_are_closed(self):
        self.assertIsNotNone(self.edit(self.work / ".env"))
        self.assertIsNotNone(self.edit(self.work / ".env.local"))
        self.assertIsNone(self.edit(self.work / ".env.example"))
        self.assertIsNotNone(self.edit(self.root / ".akasha" / "state" / "tasks" / "t1.json"))

    def test_code_waits_for_the_approval_and_the_review(self):
        blocked = self.edit(self.work / "app.py", ready="The person did not approve its preview yet.")
        self.assertIn("not ready to build", blocked)
        self.assertIsNone(self.edit(self.work / ".akasha" / "tasks" / "t1" / "preview.html", ready="not yet"))
        self.assertIsNone(self.edit(self.work / "app.py"))

    def test_the_main_checkout_is_closed_after_the_setup(self):
        self.assertIsNotNone(self.edit(self.root / "app.py"))
        self.assertIsNone(self.edit(self.root / "app.py", set_up=False))
        self.assertIsNone(self.edit(self.root / ".akasha" / "work" / "other" / "x.log"))    # git ignores it
        self.assertIsNone(self.edit(Path(self.repo.folder.name) / "outside.txt"))


if __name__ == "__main__":
    unittest.main()
