import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import config
from akasha.config import Team
from akasha.infra import desired, github, server

# The required check without [ci]. Akasha 1.0.0 had the same text without the concurrency group, the bash default,
# the fresh install, and the UTF-8 mode. A change of this text makes the handover wait in each repository until an
# administrator sets up Akasha again, so change it only on purpose.
DEFAULT_CHECK = """\
# Akasha installs this file. It runs the required checks of the team on each pull request.
# The rules come from the default branch, so a pull request cannot make its own checks weaker.
name: akasha
on:
  pull_request:
  merge_group:
permissions:
  contents: read
concurrency:
  # A new commit on the pull request, for example an update by Akasha, stops the check of the older commit
  group: akasha-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
jobs:
  akasha:
    runs-on: ubuntu-latest
    defaults:
      run:
        shell: bash               # also on a Windows runner: it needs Git Bash
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Akasha
        env:
          AKASHA_SOURCE: ${{ vars.AKASHA_SOURCE }}      # a repository variable can name a mirror or a fork
        # A runner of the team keeps its Python between runs, and an update of Akasha keeps the version 1.0.0. Without
        # --force-reinstall, pip keeps the Akasha that it installed first.
        run: pip install --force-reinstall --no-cache-dir "${AKASHA_SOURCE:-git+https://github.com/Gruci/akasha-team-harness@v1.0.0}"
      - name: Find the base branch
        env:
          BASE_REF: ${{ github.event.pull_request.base.ref || github.event.merge_group.base_ref }}
        run: echo "BASE=${BASE_REF#refs/heads/}" >> "$GITHUB_ENV"
      - name: Take the team config from the default branch
        run: |
          if git cat-file -e "origin/$BASE:akasha.toml" 2>/dev/null; then
            git show "origin/$BASE:akasha.toml" > "$RUNNER_TEMP/akasha.toml"
          else
            cp akasha.toml "$RUNNER_TEMP/akasha.toml"
          fi
      - name: Required checks
        # UTF-8 mode: on a Windows runner, Python writes to a pipe in the code page, which cannot write all text
        run: python -X utf8 -m akasha check --ci --config "$RUNNER_TEMP/akasha.toml" --base "origin/$BASE"
"""


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
        self.assertFalse(any(line.startswith("/.akasha/context") and " " in line or line == "/.akasha/ @admin"
                             for line in lines))                # the team context and the product map have no owner
        plain = Team(developers=("lead",), risk={"high": ("**/auth/**",)}, approval={"high": ("developer",)})
        self.assertIn("**/auth/** @lead", desired.codeowners(plain).splitlines())
        no_gate = Team(developers=("lead",), risk={"high": ("**/auth/**",)})
        self.assertNotIn("**/auth/** @lead", desired.codeowners(no_gate).splitlines())

    def test_a_map_file_has_no_owner_when_a_risk_pattern_matches_it(self):
        team = Team(developers=("lead",), administrators=("admin",), risk={"high": ("**/auth/**",)},
                    approval={"high": ("developer",)}, map_dir="docs/features")
        lines = desired.codeowners(team).splitlines()
        self.assertLess(lines.index("**/auth/** @lead"), lines.index("/docs/features/"))    # the last line wins
        self.assertIn("/.akasha/context/product-map.md", lines)
        self.assertEqual(server._owners(team, "src/auth/login.py"), {"lead"})
        for path in ("docs/features/auth/login-page.md", ".akasha/context/product-map.md"):
            with self.subTest(path=path):
                self.assertEqual(server._owners(team, path), set())
        self.assertEqual(server._owners(team, ".github/workflows/akasha.yml"), {"admin"})
        no_gate = desired.codeowners(Team(developers=("lead",), risk={"high": ("**/auth/**",)}))
        self.assertNotIn("/.akasha/context/map/", no_gate.splitlines())    # without a gate, the block is as before

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
        files = desired.workflows()                                      # without a team: the default values
        self.assertEqual(set(files), {f".github/workflows/akasha{name}.yml" for name in ("", "-merge", "-watch")})
        check = files[".github/workflows/akasha.yml"]
        self.assertIn("Take the team config from the default branch", check)
        self.assertIn("refs/heads/", check)
        self.assertIn("    runs-on: ubuntu-latest\n", check)
        self.assertIn('python-version: "3.12"', check)
        self.assertIn("When GitHub protects the default\n#   branch, GitHub merges.", files[".github/workflows/akasha-merge.yml"])
        self.assertIn("When GitHub protects the default branch, it does nothing.\n# update:",
                      files[".github/workflows/akasha-watch.yml"])
        self.assertEqual(desired.settings_drift({"allow_auto_merge": False, "allow_squash_merge": True}),
                         ["the repository setting allow_auto_merge is off"])
        self.assertEqual(desired.settings_drift({}), [])                # hidden settings are not problems

    def test_the_team_config_gives_the_machine_and_the_python_of_the_check(self):
        default = desired.workflows()
        self.assertEqual(default, desired.workflows(Team()))
        self.assertEqual(default[".github/workflows/akasha.yml"], DEFAULT_CHECK)
        self.assertIn("pip install --force-reinstall --no-cache-dir ", DEFAULT_CHECK)    # a runner keeps its Python
        self.assertIn("python -X utf8 -m akasha check --ci ", DEFAULT_CHECK)           # the code page of Windows
        team = Team(runs_on=("self-hosted", "windows"), python="3.13")
        files = desired.workflows(team)
        check = files[".github/workflows/akasha.yml"]
        self.assertNotIn("@@", "".join(files.values()))
        self.assertIn('python-version: "3.13"', check)
        line = next(line for line in check.splitlines() if line.startswith("    runs-on: "))
        self.assertEqual(json.loads(line.removeprefix("    runs-on: ")), ["self-hosted", "windows"])  # a YAML flow list
        self.assertIn("        shell: bash", check)                      # the steps use bash, also on Windows
        for helper in (".github/workflows/akasha-merge.yml", ".github/workflows/akasha-watch.yml"):
            self.assertEqual(files[helper], default[helper])               # the helpers stay on ubuntu-latest
            self.assertIn("runs-on: ubuntu-latest", files[helper])
        self.assertEqual(desired.runs_on(("windows-2022",)), "windows-2022")
        for labels in (("linux",), ("true",), ("my runner",)):           # YAML reads these as other values
            with self.subTest(labels=labels):
                self.assertEqual(desired.runs_on(labels), json.dumps(labels[0]))

    def test_the_helpers_use_the_app_token_when_the_repository_has_the_app(self):
        files = desired.workflows()
        jobs = {}
        for name in ("akasha-merge", "akasha-watch"):
            text = files[f".github/workflows/{name}.yml"]
            self.assertIn("git+https://github.com/Gruci/akasha-team-harness@v1.0.0", text)
            for part in re.split(r"\n(?=  \w)", "\n" + text.split("\njobs:\n", 1)[1])[1:]:     # one part for each job
                jobs[part.split(":")[0].strip()] = part
        self.assertEqual(set(jobs), {"merge", "failed", "watch", "update"})
        app = "uses: actions/create-github-app-token@v3"
        for job in ("merge", "watch"):                              # a repository without the app works as before
            with self.subTest(job=job):
                step = jobs[job][jobs[job].index("Make a token of the GitHub app"):jobs[job].index(app)]
                self.assertIn("if: ${{ vars.AKASHA_APP_CLIENT_ID != '' }}", step)
                self.assertIn("client-id: ${{ vars.AKASHA_APP_CLIENT_ID }}", jobs[job])
                self.assertIn("private-key: ${{ secrets.AKASHA_APP_KEY }}", jobs[job])
                self.assertIn("GH_TOKEN: ${{ steps.app.outputs.token || secrets.AKASHA_TOKEN || github.token }}",
                              jobs[job])
                self.assertLess(jobs[job].index(app), jobs[job].index("python -m akasha server"))
        self.assertIn("vars.AKASHA_APP_CLIENT_ID != ''", jobs["update"].splitlines()[1])   # only with the app
        self.assertIn("GH_TOKEN: ${{ steps.app.outputs.token }}", jobs["update"])
        self.assertNotIn(app, jobs["failed"])                        # a comment needs no app
        self.assertIn("persist-credentials: false", jobs["watch"])   # git pushes with the token of the undo step
        self.assertLess(jobs["watch"].index("gh auth setup-git"), jobs["watch"].index("server watch"))
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", jobs["merge"])  # never the pull request
        for job, group in (("merge", "akasha-merge"), ("update", "akasha-update")):
            self.assertIn(f"group: {group}", jobs[job])
            self.assertIn("cancel-in-progress: false", jobs[job])
        self.assertIn("--update-branch \"$UPDATE\"", jobs["merge"])
        self.assertIn("pull_request_review:", files[".github/workflows/akasha-merge.yml"])
        self.assertIn("server failed", jobs["failed"])
        self.assertIn("server update", jobs["update"])

    def test_a_runner_of_the_team_in_a_public_repository_gets_a_warning(self):
        own = Team(runs_on=("self-hosted", "linux"))
        self.assertTrue(desired.warnings(own, {"private": False})[0].startswith(
            'the required check runs on the runner ["self-hosted", "linux"] of [ci] runs-on'))
        self.assertEqual(desired.warnings(own, {"private": True}), [])
        self.assertEqual(desired.warnings(own, {}), [])                  # GitHub did not tell: no warning
        for labels in (("ubuntu-latest",), ("windows-2022",), ("macos-15",), ("ubuntu-24.04-arm",), ("windows-11-arm",),
                       ("macos-15-intel",), ("macos-14-large",), ("macos-latest-xlarge",), ("ubuntu-slim",)):
            with self.subTest(labels=labels):
                self.assertEqual(desired.warnings(Team(runs_on=labels), {"private": False}), [])
        for labels in (("ubuntu-22.04-gpu",), ("windows-2022-ours",), ("ubuntu-latest", "gpu")):    # a team label
            with self.subTest(labels=labels):
                self.assertEqual(len(desired.warnings(Team(runs_on=labels), {"private": False})), 1)

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

    def apply(self, login: str, admin: bool = True, by: str = "", origin: str = "team/app",
              private: bool = True) -> tuple[list[str], list[str]]:
        done = subprocess.CompletedProcess([], 0, "{}", "")
        current = {"private": private, "permissions": {"admin": admin}}
        with patch("akasha.repo.origin", return_value=origin), patch("akasha.repo.me", return_value=login), \
                patch("akasha.infra.github.repository", return_value=("team/app", "main") if origin else None), \
                patch("akasha.infra.github.settings", return_value=current), \
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
        self.assertEqual(self.apply("admin-a", by="@Admin-A"), ([], []))
        self.assertTrue((self.root / ".github" / "workflows" / "akasha.yml").is_file())

    def test_the_server_files_get_the_team_config_of_this_checkout(self):
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["Admin-A"]\n[ci]\nruns-on = "windows-latest"\n'
                                               'python = "3.11"\n', encoding="utf-8")
        self.assertEqual(self.apply("admin-a", private=False), ([], []))
        check = (self.root / ".github" / "workflows" / "akasha.yml").read_text(encoding="utf-8")
        self.assertIn("    runs-on: windows-latest\n", check)
        self.assertIn('python-version: "3.11"', check)

    def test_the_administrator_gets_the_warning_when_akasha_writes_the_file(self):
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["Admin-A"]\n[ci]\n'
                                               'runs-on = ["self-hosted", "linux"]\n', encoding="utf-8")
        self.assertEqual(self.apply("admin-a"), ([], []))                # a private repository
        problems, warned = self.apply("admin-a", private=False)
        self.assertEqual(problems, [])                                   # a warning does not stop a handover
        self.assertIn("a pull request from a fork runs its code on that machine", warned[0])

    def test_the_open_pull_requests_of_the_tasks_get_the_merge_label(self):
        listed = [{"number": 4, "body": "## Why\n\n<!-- akasha-task: t-1 -->\n", "labels": []},
                  {"number": 5, "body": "<!-- akasha-task: t-2 -->", "labels": [{"name": server.MERGE_LABEL}]},
                  {"number": 6, "body": "A pull request of a person", "labels": []}]

        def answers(root, *args, payload=None):
            return subprocess.CompletedProcess([], 0, json.dumps(listed) if args[:2] == ("pr", "list") else "{}", "")

        with patch("akasha.repo.origin", return_value="team/app"), patch("akasha.repo.me", return_value="admin-a"), \
                patch("akasha.infra.github.repository", return_value=("team/app", "main")), \
                patch("akasha.infra.github.settings", return_value={"permissions": {"admin": True}}), \
                patch("akasha.infra.github.gh", side_effect=answers) as gh:
            github.apply(self.root)
        calls = [call.args[1:] for call in gh.call_args_list]
        self.assertIn(("label", "create", server.MERGE_LABEL, *server.LABEL_OPTIONS, "--force"), calls)
        self.assertEqual([call for call in calls if call[:2] == ("pr", "edit")],
                         [("pr", "edit", "4", "--add-label", server.MERGE_LABEL)])     # also where GitHub merges

    def test_without_github_the_name_of_the_team_config(self):
        with self.assertRaises(PermissionError):
            self.apply("", by="dev-b", origin="")
        self.assertEqual(self.apply("", by="admin-a", origin=""),
                         (["Akasha wrote the files, but cannot reach GitHub to change the settings"], []))


class StatusTests(unittest.TestCase):
    """The server files must agree with the team config on the default branch, not with the checkout."""

    SERVER = '[ci]\nruns-on = ["self-hosted", "linux"]\npython = "3.13"\n'

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="akasha-status-"))
        for args in (("init", "-q"), ("config", "user.email", "test@example.com"), ("config", "user.name", "Test")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        (self.root / "akasha.toml").write_text(self.SERVER, encoding="utf-8")
        team = config.load(self.root)
        self.push({"akasha.toml": self.SERVER, ".github/CODEOWNERS": desired.codeowners(team),
                   **desired.workflows(team)})
        (self.root / "akasha.toml").write_text("", encoding="utf-8")       # the checkout is old: no [ci]

    def push(self, files: dict[str, str | None]) -> None:
        """Commit the files on the default branch of the server, and only them. None removes a file."""
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                path.unlink()
            else:
                path.write_bytes(text.encode("utf-8"))
        for args in (("add", "-A", "--", *files), ("commit", "-q", "-m", "server"),
                     ("update-ref", "refs/remotes/origin/main", "HEAD")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def status(self, private: bool = True, admin: bool = True,
               variable: subprocess.CompletedProcess | None = None) -> list[str]:
        """Examine the settings. `variable` is the answer of GitHub for the variable of the GitHub app."""
        correct = {"required_status_checks": {"strict": True, "contexts": ["akasha"]},
                   "required_pull_request_reviews": {"require_code_owner_reviews": True}}
        found = variable or subprocess.CompletedProcess([], 0, '{"name": "AKASHA_APP_CLIENT_ID"}', "")
        with patch("akasha.infra.github.repository", return_value=("team/app", "main")), \
                patch("akasha.infra.github.settings", return_value={"private": private, "permissions": {"admin": admin}}), \
                patch("akasha.infra.github.protection", return_value=correct), \
                patch("akasha.infra.github.fetch"), patch("akasha.infra.github.gh", return_value=found) as self.gh:
            return github.status(self.root)

    def test_only_an_administrator_is_told_about_a_missing_app(self):
        missing = subprocess.CompletedProcess([], 1, '{"message": "Not Found"}', "gh: Not Found (HTTP 404)")
        self.assertEqual(self.status(variable=missing), [])           # a notice does not stop a handover
        self.assertEqual(github.warnings(self.root), [github.NO_APP])
        self.assertEqual(self.gh.call_args.args[1:], ("api", f"repos/team/app/actions/variables/{github.APP_VARIABLE}"))
        hidden = subprocess.CompletedProcess([], 1, '{"message": "Forbidden"}', "gh: Forbidden (HTTP 403)")
        for admin, answer in ((True, None), (True, hidden), (False, missing)):
            with self.subTest(admin=admin, answer=answer):
                self.assertEqual(self.status(admin=admin, variable=answer), [])
                self.assertEqual(github.warnings(self.root), [])
        self.gh.assert_not_called()                                   # only an administrator is asked

    def test_the_server_files_follow_the_team_config_on_the_default_branch(self):
        self.assertEqual(self.status(), [])
        self.assertEqual(github.warnings(self.root), [])
        self.assertEqual(self.status(private=False), [])                  # a warning does not stop a handover
        self.assertIn("a pull request from a fork runs its code on that machine", github.warnings(self.root)[0])
        self.push({".github/workflows/akasha.yml": desired.workflows()[".github/workflows/akasha.yml"]})
        problems = self.status()
        self.assertEqual(len(problems), 1)
        self.assertIn(".github/workflows/akasha.yml on main is different from the file that the Akasha on this "
                      "computer makes", problems[0])
        self.assertIn("update Akasha (/plugin update akasha@akasha", problems[0])
        self.push({".github/workflows/akasha.yml": None})
        self.assertEqual(self.status(), [".github/workflows/akasha.yml is missing on main"])


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
