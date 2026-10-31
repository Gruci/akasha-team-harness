import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import repo
from akasha.config import STATE_DIR
from akasha.infra import github


def make_clone(address: str = "") -> Path:
    folder = Path(tempfile.mkdtemp(prefix="akasha-repo-"))
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    if address:
        subprocess.run(["git", "remote", "add", "origin", address], cwd=folder, check=True)
    return folder


def answer(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, "")


class GhTests(unittest.TestCase):
    def gh_env(self, root: Path) -> dict | None:
        """The environment that repo.gh gives to gh. git runs for real; gh does not run."""
        real, seen = subprocess.run, []

        def run(args, **options):
            if args[0] != "gh":
                return real(args, **options)
            seen.append(options)
            return answer()

        with patch("akasha.repo.subprocess.run", side_effect=run):
            repo.gh(root, "issue", "list", timeout=5)
        self.assertEqual(seen[0]["timeout"], 5)
        return seen[0]["env"]

    def test_gh_uses_the_repository_of_origin(self):
        with patch.dict(os.environ):
            os.environ.pop("GH_REPO", None)
            for address in ("https://github.com/a/b.git", "git@github.com:a/b.git", "https://github.com/a/b",
                            "ssh://git@ssh.github.com:443/a/b.git", "https://x-access-token@github.com/a/b/"):
                self.assertEqual(self.gh_env(make_clone(address))["GH_REPO"], "a/b", address)
            self.assertEqual(repo.github_slug("https://github.com/team/team.github.io.git"), "team/team.github.io")
            for address in ("https://gitlab.com/a/b.git", str(make_clone())):
                self.assertIsNone(self.gh_env(make_clone(address)), address)     # gh selects as before
            self.assertIsNone(self.gh_env(make_clone()))

    def test_a_gh_repo_that_the_person_set_stays(self):
        with patch.dict(os.environ, {"GH_REPO": "team/app"}):
            env = self.gh_env(make_clone("https://github.com/fork/app.git"))
        self.assertTrue(env is None or env["GH_REPO"] == "team/app")

    def test_the_repository_view_names_the_repository_of_origin(self):
        viewed = answer(json.dumps({"nameWithOwner": "a/b", "defaultBranchRef": {"name": "main"}}))
        with patch.dict(os.environ), patch("akasha.infra.github.gh", return_value=viewed) as gh:
            os.environ.pop("GH_REPO", None)
            self.assertEqual(github.repository(make_clone("git@github.com:a/b.git")), ("a/b", "main"))
            self.assertEqual(gh.call_args.args[1:4], ("repo", "view", "a/b"))
            github.repository(make_clone())
            self.assertEqual(gh.call_args.args[1:4], ("repo", "view", "--json"))      # gh selects as before


class IdentityTests(unittest.TestCase):
    def setUp(self):
        repo._logins.clear()

    def test_me_asks_gh_once_and_keeps_the_name_for_the_hooks(self):
        root = make_clone()
        with patch("akasha.repo.gh", return_value=answer("Dev-A\n")) as gh:
            self.assertEqual(repo.me(root), "dev-a")
            self.assertEqual(repo.me(root), "dev-a")
        self.assertEqual(gh.call_count, 1)
        self.assertEqual(gh.call_args.args[1:], ("api", "user", "--jq", ".login"))
        repo._logins.clear()                                     # a new process, for example a hook
        with patch("akasha.repo.gh") as gh:
            self.assertEqual(repo.me(root, kept=True), "dev-a")
        gh.assert_not_called()
        path = root / STATE_DIR / "me.json"
        path.write_text(json.dumps({"login": "dev-a", "checked": 0}), encoding="utf-8")
        repo._logins.clear()                                     # after one hour, the hook asks again
        with patch("akasha.repo.gh", return_value=answer("dev-b\n")):
            self.assertEqual(repo.me(root, kept=True), "dev-b")
        path.write_text(json.dumps({"login": "admin-a", "checked": time.time()}), encoding="utf-8")
        repo._logins.clear()                                     # a person edited the file
        with patch("akasha.repo.gh", return_value=answer("dev-b\n")):
            self.assertEqual(repo.me(root, kept=True), "admin-a")
            self.assertEqual(repo.me(root, fresh=True), "dev-b")      # for a change of the GitHub settings

    def test_a_command_after_a_login_with_another_account_has_the_new_name(self):
        root = make_clone()
        with patch("akasha.repo.gh", return_value=answer("admin-a\n")):
            self.assertEqual(repo.me(root), "admin-a")
        repo._logins.clear()                                     # gh auth login as dev-b, then a new command
        with patch("akasha.repo.gh", return_value=answer("dev-b\n")) as gh:
            self.assertEqual(repo.me(root), "dev-b")
            self.assertEqual(repo.me(root), "dev-b")
        self.assertEqual(gh.call_count, 1)                       # once in each process
        repo._logins.clear()                                     # the next hook gets the name of the command
        with patch("akasha.repo.gh") as gh:
            self.assertEqual(repo.me(root, kept=True), "dev-b")
        gh.assert_not_called()

    def test_me_is_empty_without_gh(self):
        with patch("akasha.repo.gh", return_value=answer("", 1)):
            self.assertEqual(repo.me(make_clone()), "")

    def test_each_copy_of_the_repository_has_its_own_mark(self):
        first, second = make_clone(), make_clone()
        mark = repo.host(first)
        self.assertEqual(len(mark), 16)
        self.assertEqual(repo.host(first), mark)
        self.assertNotEqual(repo.host(second), mark)
        (first / STATE_DIR / "machine.json").write_text("not json", encoding="utf-8")
        self.assertNotEqual(repo.host(first), mark)              # a damaged file gets a new mark
        self.assertEqual(repo.host(first), repo.host(first))

    def test_a_process_that_reads_while_another_writes_gets_the_same_mark(self):
        root = make_clone()
        opened = Path.open
        other: list[str] = []

        def interrupted(self, mode="r", *args, **values):      # the other process runs between the open and the write
            file = opened(self, mode, *args, **values)
            if ("w" in mode or "x" in mode) and not other:
                other.append("")
                other[0] = repo.host(root)
            return file

        with patch.object(Path, "open", interrupted):
            mine = repo.host(root)
        self.assertEqual(mine, other[0])
        self.assertEqual(repo.host(root), mine)
        self.assertEqual([item.name for item in (root / STATE_DIR).iterdir()], ["machine.json"])   # no temporary file


if __name__ == "__main__":
    unittest.main()
