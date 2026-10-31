import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import __main__ as command_line
from akasha.coordinator import board
from akasha.core.task import Task
from akasha.core.workcopy import git
from akasha.infra import server

SHA = "a" * 40
OTHER = "b" * 40
UPDATED = {"message": "Updating pull request branch."}
CONFLICT = (422, "merge conflict between base and head")
HEAD_CHANGED = (422, "expected head sha didn't match current head ref.")


def answer(stdout: object = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout if isinstance(stdout, str) else json.dumps(stdout), "")


def refused(status: int, message: str) -> subprocess.CompletedProcess:
    """A failed gh api call: gh writes the answer of GitHub, and the status on the error output."""
    return subprocess.CompletedProcess([], 1, json.dumps({"message": message}), f"gh: {message} (HTTP {status})")


def task_issue(holder: str = "dev-b", status: str = "open") -> dict:
    task = Task(id="t-1", title="Add a date filter", workflow="feature", stage="handover", status=status,
                holder=holder, holder_host="pc-b" if holder else "")
    return {"body": board.body(task), "state": "open"}


def labeled(number: int, head: str, body: str = "Closes #3\n\n<!-- akasha-task: t-1 -->\n", draft: bool = False,
            label: bool = True) -> dict:
    """An open pull request of a task in the shape of the REST API."""
    return {"state": "open", "number": number, "title": "Add a date filter", "head": {"sha": head},
            "base": {"ref": "main"}, "labels": [{"name": server.MERGE_LABEL}] if label else [], "draft": draft,
            "user": {"login": "dev-a"}, "body": body}


class FakeGitHub:
    """Answers the gh calls of the server helpers and records them. Comments that Akasha writes stay, so that a second
    run finds them. `fail` names the parts of the API paths that do not answer. `account` is the person of the token;
    the token of an app has none."""

    def __init__(self, protected: bool = False, pulls: dict | None = None, behind: int | dict = 0,
                 listed: list | None = None, conclusions: dict | None = None, files: dict | None = None,
                 reviews: dict | None = None, updates: dict | None = None, issues: dict | None = None,
                 fail: tuple[str, ...] = (), account: str = ""):
        self.protected, self.pulls, self.behind, self.listed = protected, pulls or {}, behind, listed or []
        self.conclusions, self.files, self.reviews = conclusions or {}, files or {}, reviews or {}
        self.updates, self.issues, self.fail = updates or {}, issues or {"3": task_issue()}, fail
        self.account = account
        self.calls: list[tuple[str, ...]] = []
        self.comments: dict[str, list[str]] = {}

    def __call__(self, root, *args, payload=None):
        self.calls.append(args)
        if args[:1] != ("api",):
            return answer("")
        method = args[args.index("--method") + 1] if "--method" in args else "GET"
        path = next((arg for arg in args[1:] if "/" in arg), args[1])
        if any(part in path for part in self.fail):
            return refused(502, "Server Error")
        if path == "user":
            return answer(self.account) if self.account else refused(403, "Resource not accessible by integration")
        if path.count("/") == 2:
            return answer({"default_branch": "main"})
        number = path.split("/")[4] if len(path.split("/")) > 4 else ""
        if path.endswith("/branches/main"):
            return answer({"protected": self.protected})
        if "/compare/" in path:
            head = path.rsplit("...", 1)[1]
            return answer({"behind_by": self.behind.get(head, 0) if isinstance(self.behind, dict) else self.behind})
        if "/commits/" in path and path.endswith("/pulls"):
            return answer(self.pulls.get(path.split("/commits/")[1].split("/")[0], []))
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            return answer({"check_runs": [{"conclusion": item} for item in self.conclusions.get(sha, ["success"])]})
        if "/pulls?" in path:
            return answer(self.listed)
        if path.endswith("/update-branch"):
            self.calls.append(("update-branch", number, payload["expected_head_sha"]))
            found = self.updates.get(number)
            return refused(*found) if found else answer(UPDATED)
        if "/files" in path:
            return answer(self.files.get(number, []))
        if "/reviews" in path:
            return answer(self.reviews.get(number, []))
        if "/comments" in path:
            if method == "POST":
                self.comments.setdefault(number, []).append(payload["body"])
                return answer({"id": 1})
            return answer([{"body": text} for text in self.comments.get(number, [])])
        if "/issues/" in path:
            return answer(self.issues.get(number, {}))
        if "/pulls/" in path:
            return answer({"number": 5, "head": {"sha": SHA}, "merged_by": {"login": "dev-a"}})
        return answer("")

    def did(self, *words: str) -> bool:
        return any(call[:len(words)] == words for call in self.calls)

    def updated(self) -> list[tuple[str, str]]:
        """The pull requests that Akasha asked GitHub to bring up to date, with the expected head."""
        return [call[1:] for call in self.calls if call[0] == "update-branch"]


def team_repository(config_text: str) -> Path:
    """A checkout of the default branch with the team config, as the merge workflow makes it."""
    root = Path(tempfile.mkdtemp(prefix="akasha-server-"))
    for args in (("init", "-q"), ("config", "user.email", "dev@example.com"), ("config", "user.name", "Dev")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "akasha.toml").write_text(config_text, encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "first"), ("update-ref", "refs/remotes/origin/main", "HEAD")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.root = team_repository('[roles]\nadministrators = ["Admin-A"]\n')

    def pull(self, labeled_: bool = True) -> dict:
        found = labeled(7, SHA, body="## Why\n\nA reason.\n\nCloses #3\n\n<!-- akasha-task: t-1 -->\n", label=labeled_)
        return {SHA: [found]}

    def merge(self, fake: FakeGitHub, update_branch: bool = False, legacy: bool = False) -> str:
        with patch("akasha.infra.server.gh", fake):
            return server.merge(self.root, "team/app", SHA, update_branch, legacy)

    def test_merges_a_marked_pull_request_on_the_latest_branch(self):
        fake = FakeGitHub(pulls=self.pull())
        self.assertEqual(self.merge(fake), "merged #7")
        merged = next(call for call in fake.calls if call[:2] == ("pr", "merge"))
        self.assertIn("--match-head-commit", merged)
        self.assertEqual(merged[merged.index("--subject") + 1], "Add a date filter (#7)")
        self.assertEqual(merged[merged.index("--body") + 1], "## Why\n\nA reason.\n")
        self.assertTrue(fake.did("issue", "close", "3"))             # the workflow token does not close it
        self.assertEqual(fake.updated(), [])                         # the workflow token brings nothing up to date

    def test_steps_aside_or_waits(self):
        cases = {"has no akasha-merge label": FakeGitHub(pulls=self.pull(labeled_=False)),
                 "GitHub protects main": FakeGitHub(protected=True, pulls=self.pull()),
                 "is behind main": FakeGitHub(behind=2, pulls=self.pull()),
                 "did not pass": FakeGitHub(pulls=self.pull(), conclusions={SHA: [""]})}    # an early approval
        for expected, fake in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, self.merge(fake))
                self.assertFalse(fake.did("pr", "merge"))
        behind = cases["is behind main"]                              # without a token that starts workflows
        self.assertIn("pull request #7 is behind main", self.merge(behind))     # also after an approval
        self.assertEqual(len(behind.comments["7"]), 1)               # one comment for each head
        self.assertTrue(behind.comments["7"][0].startswith("Akasha: the default branch moved after the check."))
        self.assertIn(f"<!-- akasha-behind: {SHA} -->", behind.comments["7"][0])

    def test_a_pull_request_that_is_behind_comes_up_to_date_in_each_repository(self):
        for protected in (False, True):
            with self.subTest(protected=protected):
                fake = FakeGitHub(protected=protected, behind=2, pulls=self.pull())
                self.assertEqual(self.merge(fake, update_branch=True), "pull request #7 comes up to date with main")
                self.assertEqual(fake.updated(), [("7", SHA)])           # with the head that the check passed on
                self.assertFalse(fake.did("pr", "comment") or fake.did("pr", "merge"))

    def test_a_merge_brings_the_other_pull_requests_up_to_date(self):
        fake = FakeGitHub(pulls=self.pull(), behind={OTHER: 1}, listed=[labeled(7, SHA), labeled(8, OTHER)])
        self.assertEqual(self.merge(fake, update_branch=True).splitlines(),
                         ["merged #7", "pull request #7 is up to date with main",
                          "pull request #8 comes up to date with main"])
        self.assertEqual(fake.updated(), [("8", OTHER)])

    def test_the_owners_approve_before_the_helper_merges(self):
        files = {"7": [{"filename": "app.py"}, {"filename": "ci.yml", "previous_filename": ".github/workflows/ci.yml"}]}
        fake = FakeGitHub(pulls=self.pull(), files=files)
        for _ in range(2):
            self.assertEqual(self.merge(fake), "pull request #7 waits for the approval of @Admin-A")
        self.assertFalse(fake.did("pr", "merge"))
        self.assertEqual(len(fake.comments["7"]), 1)                 # one comment, not one for each run
        self.assertIn("changes .github/workflows/ci.yml", fake.comments["7"][0])
        approved = {"user": {"login": "admin-a"}, "state": "APPROVED"}
        changes = {"user": {"login": "admin-a"}, "state": "CHANGES_REQUESTED"}
        comment = {"user": {"login": "admin-a"}, "state": "COMMENTED"}
        fake.reviews = {"7": [approved, changes]}
        self.assertIn("waits for the approval", self.merge(fake))
        fake.reviews = {"7": [changes, approved, comment]}         # a comment does not take an approval back
        self.assertEqual(self.merge(fake), "merged #7")

    def test_each_run_settles_the_other_pull_requests(self):
        """GitHub cancels a waiting run of the merge job when a newer run comes. The newer run must merge a pull
        request that the cancelled run would merge."""
        owned = {"7": [{"filename": ".github/x.yml"}]}
        listed = [labeled(9, "e" * 40, draft=True), labeled(8, OTHER), labeled(6, "d" * 40, label=False),
                  labeled(7, SHA)]                                    # GitHub lists the newest first
        fake = FakeGitHub(pulls=self.pull(), files=owned, listed=listed)
        self.assertEqual(self.merge(fake).splitlines(), ["pull request #7 waits for the approval of @Admin-A",
                                                         "merged #8"])
        self.assertEqual([call[2] for call in fake.calls if call[:2] == ("pr", "merge")], ["8"])
        for name, trigger in (("another pull request", {}), ("no label", self.pull(labeled_=False))):
            with self.subTest(trigger=name):
                fake = FakeGitHub(pulls=trigger, listed=[labeled(8, OTHER)])
                self.assertEqual(self.merge(fake).splitlines()[1:], ["merged #8"])
        fake = FakeGitHub(pulls=self.pull(), files=owned, listed=listed, behind={OTHER: 1})
        self.assertEqual(self.merge(fake).splitlines()[1:], ["pull request #8 is behind main"])
        self.assertEqual(len(fake.comments["8"]), 1)                 # the cancelled run would ask for the handover
        fake = FakeGitHub(pulls=self.pull(), files=owned, listed=listed, behind={OTHER: 1})
        self.assertEqual(self.merge(fake, update_branch=True).splitlines()[1:],
                         ["pull request #8 comes up to date with main"])
        fake = FakeGitHub(pulls=self.pull(), files=owned, listed=listed, conclusions={OTHER: [""]})
        self.assertIn("did not pass on the head of pull request #8", self.merge(fake).splitlines()[1])
        self.assertFalse(fake.did("pr", "merge"))

    def test_a_workflow_file_of_akasha_1_0_0_merges_as_before(self):
        """Its job runs only after the check passed, and its token cannot read the checks."""
        fake = FakeGitHub(pulls=self.pull(), listed=[labeled(8, OTHER)], fail=("/check-runs",))
        self.assertEqual(self.merge(fake, legacy=True), "merged #7")
        self.assertFalse(any("/pulls?" in " ".join(call) for call in fake.calls))     # its runs do not wait
        with self.assertRaises(server.ServerError):                  # the new file can read the checks
            self.merge(FakeGitHub(pulls=self.pull(), fail=("/check-runs",)))

    def test_github_that_does_not_answer_stops_the_merge(self):
        fake = FakeGitHub(pulls=self.pull(), fail=("/compare/",))
        with self.assertRaises(server.ServerError):
            self.merge(fake, update_branch=True)
        self.assertFalse(fake.did("pr", "merge"))


class UpdateTests(unittest.TestCase):
    def update(self, fake: FakeGitHub) -> list[str]:
        with patch("akasha.infra.server.gh", fake):
            return server.update(Path("."), "team/app", "main").splitlines()

    def test_a_pull_request_that_is_behind_comes_up_to_date(self):
        fake = FakeGitHub(behind={OTHER: 3}, listed=[labeled(7, SHA), labeled(8, OTHER)])
        self.assertEqual(self.update(fake), ["pull request #7 is up to date with main",
                                             "pull request #8 comes up to date with main"])
        self.assertEqual(fake.updated(), [("8", OTHER)])
        listing = next(call for call in fake.calls if call[:2] == ("api", "--paginate") and "/pulls?" in call[2])
        self.assertIn("state=open&base=main", listing[2])

    def test_a_conflict_is_told_once_on_the_pull_request_and_the_issue(self):
        fake = FakeGitHub(behind=1, listed=[labeled(8, OTHER)], updates={"8": CONFLICT})
        for _ in range(2):
            self.assertEqual(self.update(fake), ["pull request #8 conflicts with main"])
        self.assertEqual(sorted(fake.comments), ["3", "8"])
        for number in ("3", "8"):
            self.assertEqual(len(fake.comments[number]), 1)
            self.assertTrue(fake.comments[number][0].startswith("@dev-b Akasha: pull request #8 conflicts"))
            self.assertIn(f"<!-- akasha-conflict: {OTHER} -->", fake.comments[number][0])
            self.assertIn("akasha handover t-1", fake.comments[number][0])

    def test_a_new_head_and_other_failures_write_no_comment(self):
        for answer_, expected in ((HEAD_CHANGED, "got a new commit"), ((403, "Resource not accessible"), "HTTP 403"),
                                  ((502, "Server Error"), "HTTP 502")):
            with self.subTest(expected=expected):
                fake = FakeGitHub(behind=1, listed=[labeled(8, OTHER)], updates={"8": answer_})
                self.assertIn(expected, self.update(fake)[0])
                self.assertEqual(fake.comments, {})

    def test_skips_what_must_not_come_up_to_date(self):
        listed = [labeled(5, "c" * 40, draft=True), labeled(6, "d" * 40, label=False), labeled(7, SHA),
                  labeled(8, OTHER, body="Closes #4\n")]
        issues = {"3": task_issue(), "4": task_issue(status="cancelled")}
        fake = FakeGitHub(behind=1, listed=listed, issues=issues, conclusions={SHA: ["failure"]})
        self.assertEqual(self.update(fake), ["pull request #7: the check akasha failed on its head",
                                             "pull request #8: its task is cancelled"])
        self.assertEqual(fake.updated(), [])

    def test_a_pull_request_without_an_answer_does_not_stop_the_others(self):
        fake = FakeGitHub(behind=1, listed=[labeled(7, SHA, body="Closes #9\n"), labeled(8, OTHER)], fail=("/issues/9",))
        lines = self.update(fake)
        self.assertIn("GitHub did not answer", lines[0])
        self.assertEqual(fake.updated(), [("8", OTHER)])
        with self.assertRaises(server.ServerError):                 # no list: nothing to do, and the run fails
            self.update(FakeGitHub(fail=("/pulls?",)))


class FailedTests(unittest.TestCase):
    def test_a_failed_check_is_told_once_for_each_head(self):
        fake = FakeGitHub(pulls={SHA: [labeled(7, SHA)]}, issues={"3": task_issue(holder="")})
        with patch("akasha.infra.server.gh", fake):
            for _ in range(2):
                self.assertIn("told the people of pull request #7", server.failed(Path("."), "team/app", SHA))
            self.assertIn("no open pull request", server.failed(Path("."), "team/app", OTHER))
        self.assertEqual({number: len(texts) for number, texts in fake.comments.items()}, {"3": 1, "7": 1})
        self.assertTrue(fake.comments["7"][0].startswith("@dev-a Akasha: the check akasha failed"))   # nobody holds it
        self.assertIn(f"<!-- akasha-failed: {SHA} -->", fake.comments["3"][0])

    def test_the_command_line_runs_each_server_job(self):
        jobs = {"merge": ["--head-sha", SHA, "--update-branch", "true"], "update": ["--branch", "main"],
                "failed": ["--head-sha", SHA], "watch": ["--branch", "main"]}
        for job, values in jobs.items():
            with self.subTest(job=job), patch(f"akasha.infra.server.{job}", return_value=f"{job} done") as called, \
                    patch("sys.stdout"):
                self.assertEqual(command_line.main(["server", job, "--repository", "team/app", *values]), 0)
                called.assert_called_once()
        with patch("akasha.infra.server.merge", return_value="") as merged, patch("sys.stdout"):
            command_line.main(["server", "merge", "--repository", "team/app", "--head-sha", SHA])
            self.assertEqual((merged.call_args.args[1:], merged.call_args.kwargs),
                             (("team/app", SHA, False), {"legacy": True}))     # the workflow of Akasha 1.0.0
            command_line.main(["server", "merge", "--repository", "team/app", "--head-sha", SHA,
                               "--update-branch", "false"])
            self.assertEqual(merged.call_args.kwargs, {"legacy": False})


class WatchTests(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-watch-"))
        self.remote, self.root = folder / "remote.git", folder / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.root)], check=True, capture_output=True)
        for key, value in (("user.email", "dev@example.com"), ("user.name", "Dev")):
            git(self.root, "config", key, value)
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["admin-a"]\n', encoding="utf-8")
        self.before = self.commit("first")
        (self.root / "app.py").write_text("x = 1\n", encoding="utf-8")
        self.after = self.commit("a direct change")

    def commit(self, message: str, root: Path | None = None) -> str:
        root = root or self.root
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)
        git(root, "push", "-q", "origin", "HEAD:main")
        return git(root, "rev-parse", "HEAD").stdout.strip()

    def watch(self, fake: FakeGitHub, pusher: str = "dev-b", forced: bool = False) -> str:
        with patch("akasha.infra.server.gh", fake):
            return server.watch(self.root, "team/app", "main", self.before, self.after, forced, pusher)

    def remote_files(self) -> list[str]:
        return git(self.remote, "ls-tree", "--name-only", "main").stdout.split()

    def test_a_direct_change_is_undone(self):
        fake = FakeGitHub()
        self.assertEqual(self.watch(fake), "undid 1 change(s)")
        self.assertTrue(git(self.remote, "log", "-1", "--format=%s", "main").stdout.startswith(server.UNDO_MARK))
        self.assertFalse((self.root / "app.py").exists())
        self.assertTrue(fake.did("issue", "create"))
        self.before, self.after = self.after, git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(self.watch(FakeGitHub(), pusher="akasha-app[bot]"), "all changes are in order")

    def test_the_watch_keeps_its_own_undo_also_when_the_undone_change_made_new_rules(self):
        """With the app token, the undo starts the watch again, and that run reads the rules of the undone commit."""
        (self.root / "akasha.toml").write_text('[roles]\nadministrators = ["admin-a", "dev-a"]\n', encoding="utf-8")
        self.before, self.after = self.after, self.commit("make dev-a an administrator")   # merged by dev-a
        merged = {self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]}     # and no owner approved
        self.assertEqual(self.watch(FakeGitHub(pulls=merged)), "undid 1 change(s)")
        undone = git(self.remote, "show", "main:akasha.toml").stdout
        self.before, self.after = self.after, git(self.remote, "rev-parse", "main").stdout.strip()
        self.assertEqual(self.watch(FakeGitHub(pulls=merged), pusher="akasha-app[bot]"), "all changes are in order")
        self.assertEqual(git(self.remote, "show", "main:akasha.toml").stdout, undone)
        self.assertNotIn("dev-a", undone)

    def test_only_a_helper_can_push_an_undo(self):
        """A person can copy the subject and the exact reverse change, for example of a commit from before Akasha."""
        git(self.root, "revert", "--no-commit", self.after)
        self.before, self.after = self.after, self.commit(f"{server.UNDO_MARK} {self.after[:12]}: it went around the "
                                                          "check")
        for pusher, fake in (("akasha-app[bot]", FakeGitHub()), ("ci-owner", FakeGitHub(account="CI-Owner"))):
            with self.subTest(pusher=pusher):
                self.assertEqual(self.watch(fake, pusher=pusher), "all changes are in order")
        with self.assertRaises(server.ServerError):                  # no answer is not "the token of an app"
            self.watch(FakeGitHub(fail=("user",)))
        self.assertEqual(git(self.remote, "rev-parse", "main").stdout.strip(), self.after)
        self.assertEqual(self.watch(FakeGitHub()), "undid 1 change(s)")
        self.assertIn("app.py", self.remote_files())                # the change from before Akasha comes back

    def test_the_patch_id_keeps_text_that_is_not_utf_8(self):
        def change(text: str) -> str:
            (self.root / "limit.txt").write_bytes(text.encode("cp949"))
            return self.commit(text)
        old, new, other = change("limit = '가'\n"), change("limit = '나'\n"), change("limit = '하'\n")
        self.assertTrue(server._patch_id(self.root, new, old))
        self.assertNotEqual(server._patch_id(self.root, new, old), server._patch_id(self.root, new, other))

    def test_an_undo_that_is_not_exact_is_undone(self):
        git(self.root, "rm", "-q", "app.py")
        (self.root / "extra.py").write_text("import os\n", encoding="utf-8")
        self.before, self.after = self.after, self.commit(f"{server.UNDO_MARK} {self.after[:12]}: it went around the "
                                                          "check")
        self.assertEqual(self.watch(FakeGitHub()), "undid 1 change(s)")
        self.assertNotIn("extra.py", self.remote_files())

    def test_an_exact_undo_of_a_change_in_order_is_undone(self):
        merged = {self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]}
        git(self.root, "revert", "--no-commit", self.after)
        self.before, self.after = self.after, self.commit(f"{server.UNDO_MARK} {self.after[:12]}: it went around the "
                                                          "check")
        self.assertEqual(self.watch(FakeGitHub(pulls=merged)), "undid 1 change(s)")
        self.assertIn("app.py", self.remote_files())                # the change that the team accepted stays

    def test_github_that_does_not_answer_undoes_nothing(self):
        for part in ("/commits/", "/branches/"):
            with self.subTest(part=part), self.assertRaises(server.ServerError):
                self.watch(FakeGitHub(fail=(part,)))
            self.assertEqual(git(self.remote, "rev-parse", "main").stdout.strip(), self.after)

    def test_a_refused_push_undoes_again_on_the_latest_branch(self):
        other = Path(tempfile.mkdtemp(prefix="akasha-watch-other-")) / "work"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(other)], check=True, capture_output=True)
        for key, value in (("user.email", "dev@example.com"), ("user.name", "Dev")):
            git(other, "config", key, value)
        raced = []

        def first_push_races(cwd, *args, **values):
            if args[:1] == ("push",) and not raced:            # another push arrives before the push of the watch
                raced.append(True)
                (other / "notes.md").write_text("notes\n", encoding="utf-8")
                self.commit("another change", other)
            return git(cwd, *args, **values)

        with patch("akasha.infra.server.git", side_effect=first_push_races):
            self.assertEqual(self.watch(FakeGitHub()), "undid 1 change(s)")
        self.assertEqual(sorted(self.remote_files()), ["akasha.toml", "notes.md"])
        self.assertTrue(git(self.remote, "log", "-1", "--format=%s", "main").stdout.startswith(server.UNDO_MARK))

    def test_reported_but_not_undone(self):
        for name, fake, pusher, forced in (("administrator", FakeGitHub(), "Admin-A", False),
                                           ("force push", FakeGitHub(), "dev-b", True)):
            with self.subTest(name=name):
                self.assertIn("reported", self.watch(fake, pusher, forced))
                self.assertTrue(fake.did("issue", "create"))
                self.assertEqual(git(self.remote, "rev-parse", "main").stdout.strip(), self.after)

    def test_a_change_in_order_or_under_github_protection_stays(self):
        merged = FakeGitHub(pulls={self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]})
        self.assertEqual(self.watch(merged), "all changes are in order")
        protected = FakeGitHub(protected=True)
        self.assertIn("GitHub protects main", self.watch(protected))
        self.assertFalse(protected.did("issue", "create"))

    def test_a_rules_file_needs_its_owner(self):
        (self.root / ".github").mkdir()
        (self.root / ".github" / "x.yml").write_text("on: push\n", encoding="utf-8")
        self.after = self.commit("change a rule")
        fake = FakeGitHub(pulls={self.after: [{"number": 5, "merged_at": "now", "head": {"sha": SHA}}]})
        with patch("akasha.infra.server.gh", fake):
            reason = server._reason(self.root, "team/app", server._team_at(self.root, self.before), self.after)
        self.assertIn("without the approval of its owner", reason)


if __name__ == "__main__":
    unittest.main()
