import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha.config import Team
from akasha.infra import desired, github


class InfraTests(unittest.TestCase):
    def test_codeowners_follow_the_gates_and_keep_the_rules_with_the_administrators(self):
        team = Team(developers=("@lead",), administrators=("@admin",),
                    risk={"high": ("**/auth/**",), "medium": ("**/api/**",)},
                    approval={"high": ("developer",), "medium": ("developer", "administrator")})
        lines = desired.codeowners(team).splitlines()
        self.assertEqual((lines[0], lines[-1]), (desired.START, desired.END))
        self.assertIn("**/auth/** @lead", lines)
        self.assertIn("**/api/** @admin @lead", lines)
        self.assertIn("/akasha.toml @admin", lines)
        self.assertIn("/.akasha/workflows/ @admin", lines)
        self.assertFalse(any(line.startswith("/.akasha/context") or line == "/.akasha/ @admin" for line in lines))
        plain = Team(developers=("lead",), risk={"high": ("**/auth/**",)}, approval={"high": ("developer",)})
        self.assertIn("**/auth/** @lead", desired.codeowners(plain).splitlines())
        no_gate = Team(developers=("lead",), risk={"high": ("**/auth/**",)})
        self.assertNotIn("**/auth/** @lead", desired.codeowners(no_gate).splitlines())

    def test_the_block_keeps_the_lines_of_the_team(self):
        block = desired.codeowners(Team(administrators=("admin",)))
        merged = desired.merge("* @team-leads\n", block)
        self.assertTrue(merged.startswith("* @team-leads\n"))
        self.assertTrue(merged.endswith(block))                         # the last matching line wins
        self.assertEqual(desired.block(merged), block)
        again = desired.merge(merged, desired.codeowners(Team(administrators=("other",))))
        self.assertEqual(again.count(desired.START), 1)
        self.assertIn("* @team-leads", again)

    def test_protection_and_settings(self):
        wanted = desired.protection()
        self.assertEqual(wanted["required_status_checks"], {"strict": True, "contexts": ["akasha"]})
        self.assertEqual(wanted["required_pull_request_reviews"],
                         {"required_approving_review_count": 0, "require_code_owner_reviews": True})
        files = desired.workflows()
        self.assertEqual(set(files), {f".github/workflows/akasha{name}.yml" for name in ("", "-merge", "-watch")})
        check = files[".github/workflows/akasha.yml"]
        self.assertIn("Take the team config from the default branch", check)
        self.assertIn("refs/heads/", check)
        for helper in (".github/workflows/akasha-merge.yml", ".github/workflows/akasha-watch.yml"):
            self.assertIn("When GitHub protects the default branch, it does nothing", files[helper])
        self.assertEqual(desired.settings_drift({"allow_auto_merge": False, "allow_squash_merge": True}),
                         ["the repository setting allow_auto_merge is off"])
        self.assertEqual(desired.settings_drift({}), [])                # hidden settings are not problems

    def test_drift(self):
        self.assertEqual(desired.drift(None), ["the default branch has no branch protection"])
        correct = {"required_status_checks": {"strict": True, "contexts": ["akasha"]},
                   "required_pull_request_reviews": {"required_approving_review_count": 0,
                                                     "require_code_owner_reviews": True},
                   "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
        self.assertEqual(desired.drift(correct), [])
        weak = {"required_status_checks": {"strict": False, "checks": [{"context": "lint"}]},
                "allow_force_pushes": {"enabled": True}}
        problems = desired.drift(weak)
        self.assertIn("the check akasha is not required", problems)
        self.assertIn("force pushes are permitted", problems)
        self.assertIn("code owners do not have to approve", problems)
        partial = {"required_status_checks": {"contexts": ["akasha"]}, "partial": True}
        self.assertEqual(desired.drift(partial), [])                     # a person without administrator rights
        self.assertEqual(desired.drift({"unavailable": True}), [desired.NO_PLAN])     # a private repository on Free


class ApplyTests(unittest.TestCase):
    """Only an administrator changes the GitHub settings. With GitHub, Akasha asks GitHub who the person is."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="akasha-apply-"))
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["Admin-A"]\n', encoding="utf-8")

    def apply(self, login: str, admin: bool = True, by: str = "", origin: str = "team/app") -> list[str]:
        done = subprocess.CompletedProcess([], 0, "{}", "")
        with patch("akasha.repo.origin", return_value=origin), patch("akasha.repo.me", return_value=login), \
                patch("akasha.infra.github.repository", return_value=("team/app", "main") if origin else None), \
                patch("akasha.infra.github.settings", return_value={"permissions": {"admin": admin}}), \
                patch("akasha.infra.github.gh", return_value=done):
            return github.apply(self.root, by)

    def test_the_account_of_this_computer_approves(self):
        for login, admin, by, reason in (("dev-b", True, "", "dev-b is not an administrator"),
                                         ("admin-a", False, "", "does not administer this repository"),
                                         ("admin-a", True, "dev-b", "dev-b must approve the change on their own"),
                                         ("", True, "admin-a", "cannot read your GitHub name")):
            with self.subTest(login=login, by=by), self.assertRaises(PermissionError) as refused:
                self.apply(login, admin, by)
            self.assertIn(reason, str(refused.exception))
        self.assertFalse((self.root / ".github").exists())               # nothing written
        self.assertEqual(self.apply("admin-a", by="@Admin-A"), [])
        self.assertTrue((self.root / ".github" / "workflows" / "akasha.yml").is_file())

    def test_without_github_the_name_of_the_team_config(self):
        with self.assertRaises(PermissionError):
            self.apply("", by="dev-b", origin="")
        self.assertEqual(self.apply("", by="admin-a", origin=""),
                         ["Akasha wrote the files, but cannot reach GitHub to change the settings"])


class ReadinessTests(unittest.TestCase):
    """The record of the last examination of the server rules follows the server, the person, and Akasha."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="akasha-ready-"))
        for args in (("init", "-q"), ("config", "user.email", "test@example.com"), ("config", "user.name", "Test"),
                     ("commit", "-q", "--allow-empty", "-m", "first"), ("update-ref", "refs/remotes/origin/main", "HEAD")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        self.login = "dev-a"

    def examined(self) -> bool:
        """Read the record. True when Akasha examined GitHub again."""
        with patch("akasha.repo.origin", return_value="team/app"), \
                patch("akasha.repo.me", side_effect=lambda root: self.login), \
                patch("akasha.infra.github.status", side_effect=lambda root: github._remember(root, [], True, "github",
                                                                                           "main")) as status:
            github.readiness(self.root)
        return status.called

    def test_a_record_is_old_when_the_server_the_person_or_akasha_changes(self):
        self.assertTrue(self.examined())                               # no record yet
        self.assertFalse(self.examined())
        self.assertEqual(github.known_branch(self.root), "main")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "settings"], cwd=self.root, check=True)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=self.root, check=True)
        self.assertTrue(self.examined())                               # a fetch moved the default branch
        self.assertFalse(self.examined())
        self.login = "dev-b"
        self.assertTrue(self.examined())                               # another GitHub account
        with patch("akasha.infra.github._installed", return_value="another-akasha"):
            self.assertTrue(self.examined())                           # an update of Akasha keeps the version 1.0.0
        self.assertTrue(self.examined())
        path = self.root / github.SERVER_STATE
        record = json.loads(path.read_text(encoding="utf-8"))
        record["checked"] -= github.RECORD_AGE + 1
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertTrue(self.examined())                               # one hour at most


if __name__ == "__main__":
    unittest.main()
