import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from akasha import __main__ as command_line
from akasha import config, flow, setup
from akasha.coordinator import board
from akasha.core import workcopy
from akasha.core import task as tasks
from akasha.engine import hooks
from akasha.infra import desired, github
from tests.test_coordinator import FakeBoard, answer
from tests.test_risk import BRIEFING

PASS = f'"{sys.executable}" -c "raise SystemExit(0)"'
FAIL = f'"{sys.executable}" -c "raise SystemExit(1)"'
IMPACT = {"features": "The customer search", "data": "No data change", "contracts": "No public contract",
          "tasks": "No other task", "rollback": "Revert the squash commit"}
PULL_REQUEST = "https://github.com/team/app/pull/7"
WRITES = (("issue", "create"), ("issue", "edit"), ("issue", "close"))


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


@contextmanager
def person(login: str = "dev-a", mark: str = "pc-a", fake: FakeBoard | None = None):
    """One person in one copy of the repository, with the shared task board on GitHub. Nothing asks the real gh for
    the name of the person. With `fake`, the board is the fake, and its comments come from this person."""
    with ExitStack() as stack:
        for target, value in (("akasha.coordinator.board.available", True), ("akasha.repo.me", login),
                              ("akasha.repo.host", mark)):
            stack.enter_context(patch(target, return_value=value))
        if fake is not None:
            fake.login = login
            stack.enter_context(patch("akasha.coordinator.board.gh", fake))
        yield


@contextmanager
def github_merges_later():
    """GitHub opens the pull request and turns on auto-merge. The pull request did not merge yet."""
    opened = subprocess.CompletedProcess([], 0, PULL_REQUEST + "\n", "")
    with patch("akasha.flow.github.repository", return_value=("team/app", "main")), \
            patch("akasha.flow.github.pull_request", return_value={}), \
            patch("akasha.flow.github.merged", return_value=False), \
            patch("akasha.flow.github.auto_merge", return_value=answer()), \
            patch("akasha.flow.gh", return_value=opened) as gh:
        yield gh


def clone(remote: Path) -> Path:
    """Another copy of the repository, as on another computer."""
    folder = Path(tempfile.mkdtemp(prefix="akasha-clone-"))
    subprocess.run(["git", "clone", "-q", str(remote), str(folder)], check=True, capture_output=True)
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test")):
        subprocess.run(["git", "config", key, value], cwd=folder, check=True)
    return folder


def add_remote(root: Path) -> Path:
    remote = Path(tempfile.mkdtemp(prefix="akasha-remote-"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main"], cwd=remote, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True, capture_output=True)
    return remote


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
        blocked = flow.advance(root, task.id)
        self.assertIn("the requester did not approve the specification", blocked)
        self.assertTrue(any("impact analysis is not complete" in reason for reason in blocked))
        flow.approve(root, task.id, "requester", "ops-member")
        flow.impact(root, task.id, IMPACT)
        self.assertEqual(flow.advance(root, task.id), [])
        task = tasks.load(root, task.id)
        self.assertEqual(task.stage, "build")
        work = Path(task.workcopy)
        (work / "search.py").write_text("def search(date):\n    return date\n", encoding="utf-8")
        self.assertEqual(flow.advance(root, task.id), [])
        self.assertEqual(flow.check(root, task.id).status, {"secrets": "PASS", "tests": "PASS"})
        self.assertEqual(workcopy.git(work, "status", "--porcelain").stdout, "")   # a pass saves the work
        self.assertEqual(flow.advance(root, task.id), [])
        blocked = flow.advance(root, task.id)
        self.assertTrue(any("did not accept" in reason for reason in blocked))
        self.assertTrue(any("product map" in reason for reason in blocked))
        flow.accept(root, task.id, None, True)
        (work / ".akasha" / "context").mkdir(parents=True)
        (work / ".akasha" / "context" / "product-map.md").write_text("## Customer search\n", encoding="utf-8")
        with patch("akasha.flow.github.status", return_value=[]):
            self.assertEqual(flow.advance(root, task.id), [])
        self.assertEqual(tasks.load(root, task.id).stage, "handover")
        with self.assertRaises(ValueError):                 # no briefing yet
            flow.handover(root, task.id)
        self.assertEqual(flow.brief(root, task.id, BRIEFING), [])
        self.assertTrue(flow.brief(root, task.id, "## Why\n\nNo other section."))
        with self.assertRaises(RuntimeError):               # no GitHub repository in this test
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
        flow.impact(root, task.id, IMPACT)
        work = Path(task.workcopy)
        (work / "src" / "search").mkdir(parents=True)
        (work / "src" / "search" / "안내.md").write_text("검색 안내\n", encoding="utf-8")
        (work / ".akasha" / "context").mkdir(parents=True)
        (work / ".akasha" / "context" / "product-map.md").write_text("## Search\n", encoding="utf-8")
        self.assertEqual(flow.advance(root, task.id), [])    # a Korean name and the product map are in order
        (work / "billing.py").write_text("x = 1\n", encoding="utf-8")
        (work / "청구.py").write_text("KEY = 'sk-" + "d" * 24 + "'\n", encoding="utf-8")
        self.assertEqual(flow.outside_scope(tasks.load(root, task.id), workcopy.changed_files(task)),
                         ("billing.py", "청구.py"))
        self.assertEqual(flow.check(root, task.id).status["secrets"], "FAIL")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(hooks.turn_end(root), 0)
        self.assertIn("billing.py", json.loads(output.getvalue())["systemMessage"])

    def test_the_handover_opens_one_pull_request_with_auto_merge(self):
        root = make_repo(PASS)
        remote = add_remote(root)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        (Path(task.workcopy) / "search.py").write_text("x = 1\n", encoding="utf-8")
        flow.impact(root, task.id, IMPACT, map_note="The change adds no feature, screen, table, or API.")
        self.assertEqual(flow.advance(root, task.id), [])
        flow.check(root, task.id)
        self.assertEqual(workcopy.git(remote, "rev-parse", task.branch).returncode, 0)   # a pass pushes the branch
        with patch("akasha.flow.github.status", return_value=[]):
            self.assertEqual(flow.advance(root, task.id), [])
        flow.brief(root, task.id, BRIEFING)
        opened = subprocess.CompletedProcess([], 0, PULL_REQUEST + "\n", "")
        queued = subprocess.CompletedProcess([], 0, "", "")
        found = [{}, {"url": PULL_REQUEST, "state": "OPEN", "autoMergeRequest": {"enabledAt": "now"}}]
        with patch("akasha.flow.github.repository", return_value=("team/app", "main")), \
                patch("akasha.flow.github.pull_request", side_effect=found), \
                patch("akasha.flow.github.merged", side_effect=[False, False, True]), \
                patch("akasha.flow.github.auto_merge", return_value=queued) as auto_merge, \
                patch("akasha.flow.gh", return_value=opened) as gh:
            address, blocked = flow.handover(root, task.id)
            self.assertEqual(address, PULL_REQUEST)
            self.assertTrue(any("did not merge yet" in reason for reason in blocked))
            (Path(task.workcopy) / "search.py").write_text("x = 2\n", encoding="utf-8")
            flow.handover(root, task.id)                     # a repair goes to the same pull request
            self.assertEqual(flow.advance(root, task.id), [])    # GitHub merged it
        self.assertEqual([call.args[1:3] for call in gh.call_args_list], [("pr", "create")])
        subject, body = auto_merge.call_args.args[2:4]
        self.assertEqual(subject, "Change the search (#7)")
        self.assertTrue(body.startswith("## Why") and "## Verification" in body)
        self.assertEqual(auto_merge.call_count, 1)
        task = tasks.load(root, task.id)
        self.assertEqual((task.status, task.workcopy), ("done", ""))
        self.assertEqual(workcopy.git(remote, "log", "-1", "--format=%s", task.branch).stdout.strip(), task.title)

    def test_without_github_protection_the_pull_request_gets_the_merge_label(self):
        root = make_repo(PASS)
        add_remote(root)
        with (root / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write('[server]\nrules = "akasha"\n')
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        (Path(task.workcopy) / "search.py").write_text("x = 1\n", encoding="utf-8")
        flow.impact(root, task.id, IMPACT, map_note="The change adds no feature, screen, table, or API.")
        flow.advance(root, task.id)
        flow.check(root, task.id)
        with patch("akasha.flow.github.status", return_value=[]):
            flow.advance(root, task.id)
        flow.brief(root, task.id, BRIEFING)
        opened = subprocess.CompletedProcess([], 0, PULL_REQUEST + "\n", "")
        with patch("akasha.flow.github.repository", return_value=("team/app", "main")), \
                patch("akasha.flow.github.pull_request", return_value={}), \
                patch("akasha.flow.github.merged", return_value=False), \
                patch("akasha.flow.github.auto_merge") as auto_merge, patch("akasha.flow.gh", return_value=opened) as gh:
            flow.handover(root, task.id)
        created = gh.call_args_list[0].args
        self.assertEqual(created[created.index("--label") + 1], "akasha-merge")
        auto_merge.assert_not_called()                       # the merge workflow of Akasha merges it

    def test_files_outside_the_scope_never_go_into_a_commit(self):
        root = make_repo(PASS)
        remote = add_remote(root)
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small", scope=["src/**"])
        work = Path(task.workcopy)
        (work / "src").mkdir()
        (work / "src" / "search.py").write_text("x = 1\n", encoding="utf-8")
        (work / "notes.pyc").write_text("made by a test\n", encoding="utf-8")
        self.assertEqual(flow.check(root, task.id).status["tests"], "PASS")
        self.assertNotEqual(workcopy.git(work, "status", "--porcelain").stdout, "")     # nothing saved
        self.assertNotEqual(workcopy.git(remote, "rev-parse", "--verify", "-q", task.branch).returncode, 0)
        task = tasks.load(root, task.id)
        task.stage, task.briefing = "handover", BRIEFING
        tasks.save(root, task)
        with patch("akasha.flow.github.repository", return_value=("team/app", "main")), \
                patch("akasha.flow.github.pull_request", return_value={}), self.assertRaises(RuntimeError) as stopped:
            flow.handover(root, task.id)
        self.assertIn("notes.pyc", str(stopped.exception))
        (work / "notes.pyc").unlink()
        flow.check(root, task.id)
        self.assertEqual(workcopy.git(remote, "rev-parse", "--verify", "-q", task.branch).returncode, 0)

    def test_setup_ignores_the_files_that_tests_make(self):
        root = make_repo(PASS)                                # it tracks app.py, so the Python pack applies
        setup.run(root, "")
        self.assertIn("__pycache__/", (root / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_a_task_builds_on_an_earlier_task(self):
        root = make_repo(PASS)
        add_remote(root)
        earlier, _ = flow.start(root, "Add a date filter", "ops-a", workflow="small", feature="search-filter")
        (Path(earlier.workcopy) / "date_filter.py").write_text("x = 1\n", encoding="utf-8")
        flow.check(root, earlier.id)
        with self.assertRaises(ValueError):
            flow.start(root, "Export", "ops-b", workflow="small", builds_on="no-such-task")
        later, found = flow.start(root, "Export the filtered list", "ops-b", workflow="small",
                                  feature="search-filter", builds_on=earlier.id)
        self.assertEqual(found, [])                          # one line of work, not an overlap
        self.assertTrue((Path(later.workcopy) / "date_filter.py").is_file())
        (Path(later.workcopy) / "export.py").write_text("y = 2\n", encoding="utf-8")
        self.assertEqual(workcopy.changed_files(later), ["export.py"])
        later = tasks.load(root, later.id)
        later.stage, later.briefing = "handover", BRIEFING
        tasks.save(root, later)
        nothing = subprocess.CompletedProcess([], 0, "0\n", "")
        with patch("akasha.flow.gh", return_value=nothing), self.assertRaises(RuntimeError) as stopped:
            flow.handover(root, later.id)
        self.assertIn("did not merge yet", str(stopped.exception))
        flow.cancel(root, earlier.id, "ops-a")
        with patch("akasha.flow.gh", return_value=nothing), self.assertRaises(RuntimeError) as stopped:
            flow.handover(root, later.id)
        self.assertIn(f"the earlier task {earlier.id} was cancelled", str(stopped.exception))
        with self.assertRaises(ValueError):                  # only "" stops the stack; a new stack is a new request
            flow.specify(root, later.id, [], [], False, builds_on="other-task")
        with patch("akasha.__main__.main_root", return_value=root), redirect_stdout(io.StringIO()):
            self.assertEqual(command_line.run(["specify", later.id, "--builds-on", ""]), 0)
        later = tasks.load(root, later.id)
        self.assertEqual(later.builds_on, "")
        self.assertEqual(workcopy.changed_files(later), ["date_filter.py", "export.py"])     # now changes of this task

    def test_a_work_copy_that_cannot_start_names_the_recorded_task(self):
        root = make_repo(PASS)
        earlier, _ = flow.start(root, "Add a date filter", "ops-a")          # its branch is not there yet
        with self.assertRaises(RuntimeError) as stopped:
            flow.start(root, "Use the date filter", "ops-b", workflow="small", builds_on=earlier.id)
        self.assertIn("not on this computer or on the server yet", str(stopped.exception))
        self.assertEqual([item.id for item in tasks.all_tasks(root)], [earlier.id])     # nothing recorded, as in 1.0.0
        fake = FakeBoard()
        with person(fake=fake):
            with patch("akasha.flow.workcopy.create", side_effect=RuntimeError("git worktree add failed: disk full")), \
                    self.assertRaises(RuntimeError) as stopped:
                flow.start(root, "Export the filtered list", "ops-b", workflow="small")
            [recorded] = [item for item in tasks.all_tasks(root) if item.id != earlier.id]
            self.assertIn(f"Akasha recorded the task {recorded.id}: continue with it", str(stopped.exception))
            self.assertIn(f"run `akasha advance {recorded.id}`", str(stopped.exception))
            self.assertIn(recorded.board, fake.issues)
            flow.advance(root, recorded.id)                                   # it makes the work copy
        self.assertTrue(Path(tasks.load(root, recorded.id).workcopy).is_dir())

    def test_a_change_of_accepted_behavior_is_told_to_the_earlier_requester(self):
        root = make_repo(PASS)
        earlier, _ = flow.start(root, "Add a date filter", "ops-a")
        earlier.board = "https://github.com/team/app/issues/3"
        tasks.save(root, earlier)
        later, _ = flow.start(root, "Use the transaction date", "ops-b")
        with patch("akasha.flow.board.comment", return_value=True) as comment:
            _task, told = flow.impact(root, later.id, IMPACT, changes=(earlier.id, "The filter uses another date"))
        address, text = comment.call_args.args[1:3]
        self.assertEqual(address, earlier.board)
        self.assertTrue(text.startswith("@ops-a Akasha:"))
        self.assertIn("ops-a", told)

    def test_a_notice_that_github_refused_is_not_told(self):
        root = make_repo(PASS)
        fake = FakeBoard()

        def refuse(root, *args, **values):                   # the board reads and updates work, comments do not
            if args[:2] == ("issue", "comment"):
                return answer("", 1, "HTTP 403: Resource not accessible")
            return fake(root, *args, **values)

        with person():
            with patch("akasha.coordinator.board.gh", fake):
                earlier, _ = flow.start(root, "Add a date filter", "ops-a")
                later, _ = flow.start(root, "Use the transaction date", "ops-b")
            with patch("akasha.coordinator.board.gh", refuse), self.assertRaises(board.BoardError):
                flow.impact(root, later.id, IMPACT, changes=(earlier.id, "The filter uses another date"))
            self.assertEqual((tasks.load(root, later.id).notes, fake.issues[earlier.board]["comments"]), ([], []))
            with patch("akasha.coordinator.board.gh", fake):
                _task, told = flow.impact(root, later.id, IMPACT, changes=(earlier.id, "The filter uses another date"))
        self.assertEqual(told, f"Akasha told ops-a on {earlier.board}.")
        self.assertEqual(len(fake.issues[earlier.board]["comments"]), 1)

    def test_the_setup_command_runs_in_a_new_copy_and_in_ci(self):
        root = make_repo(PASS)
        with (root / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write(f"setup = '\"{sys.executable}\" -c \"raise SystemExit(str(1234567))\"'\n")
        self.assertEqual(flow.ci_check(root, None, "HEAD").status, {"setup": "FAIL"})
        task, _ = flow.start(root, "Change the search", "ops-member", workflow="small")
        self.assertIn("setup command failed", task.notes[0])
        self.assertIn("1234567", task.setup_output)                   # the output stays on this computer
        self.assertNotIn("1234567", board.body(task))

    def test_a_wider_scope_finds_overlaps(self):
        root = make_repo(PASS)
        first, _ = flow.start(root, "Change the search", "ops-a", scope=["src/search/**"])
        second, found = flow.start(root, "Add a date filter", "ops-b")
        self.assertEqual(found, [])
        _task, found = flow.specify(root, second.id, [], [], False, ["src/search/date.py"])
        self.assertEqual([(item.kind, item.other) for item in found], [("order", first.id)])
        flow.cancel(root, first.id, "ops-a")
        self.assertEqual(flow.specify(root, second.id, [], [], False, ["src/search/more.py"])[1], [])

    def test_task_ids_are_unique_in_the_repository(self):
        self.assertRegex(tasks.new_id("날짜 필터"), r"^task-[0-9a-f]{8}$")
        root = make_repo(PASS)
        add_remote(root)
        tasks.save(root, tasks.Task(id="x-1", title="x", workflow="feature", stage="request"))
        workcopy.git(root, "branch", "akasha/x-2")
        workcopy.git(root, "push", "-q", "origin", "HEAD:refs/heads/akasha-wip/x-4", "HEAD:refs/heads/akasha/x-6")
        fake = FakeBoard()
        fake.add(board.body(tasks.Task(id="x-3", title="x", workflow="feature", stage="request", status="done")),
                 state="CLOSED")
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.core.task.new_id", side_effect=["x-1", "x-2", "x-3", "x-4", "x-5"]):
            task, _ = flow.start(root, "x", "ops-a")
        self.assertEqual(task.id, "x-5")
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.core.task.new_id", side_effect=["x-1", "x-2", "x-3", "x-4", "x-6"]), \
                self.assertRaises(RuntimeError) as stopped:
            flow.start(root, "x", "ops-a")
        self.assertIn("five task ids", str(stopped.exception))       # the last one is a branch on the server

    def test_a_board_on_github_that_fails_stops_the_request(self):
        root = make_repo(PASS)
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)), \
                patch("akasha.repo.me", return_value="dev-a"), patch("akasha.repo.host", return_value="pc-a"):
            first, _ = flow.start(root, "Add a date filter", "ops-a")     # without GitHub, the board is local
            self.assertEqual([item.id for item in board.read(root)[0]], [first.id])
            workcopy.git(root, "remote", "add", "origin", "https://github.com/team/app.git")
            with self.assertRaises(board.BoardError) as stopped:
                flow.start(root, "Export the filtered list", "ops-b")
            self.assertIn("gh auth status", str(stopped.exception))
            with self.assertRaises(board.BoardError):
                flow.advance(root, first.id)
            output = io.StringIO()
            with patch("akasha.__main__.main_root", return_value=root), redirect_stderr(output):
                self.assertEqual(command_line.run(["board"]), 2)
            self.assertIn("cannot read the shared task board", output.getvalue())
        self.assertEqual([item.id for item in tasks.all_tasks(root)], [first.id])

    def test_a_failed_board_write_keeps_the_task_and_names_it(self):
        root = make_repo(PASS)
        fake = FakeBoard()

        def refuse(root, *args, **values):                   # the board reads work, the writes do not
            return answer("", 1, "HTTP 502: Bad Gateway") if args[:2] in WRITES else fake(root, *args, **values)

        with person():
            with patch("akasha.coordinator.board.gh", refuse), self.assertRaises(board.BoardError) as stopped:
                flow.start(root, "Add a date filter", "ops-a")
            [saved] = tasks.all_tasks(root)
            self.assertIn(f"run `akasha specify {saved.id}`", str(stopped.exception))
            self.assertEqual(fake.issues, {})
            with patch("akasha.coordinator.board.gh", fake):
                flow.specify(root, saved.id, [], [], False)          # puts the saved task on the board
            address = tasks.load(root, saved.id).board
            self.assertEqual(board.parse(fake.issues[address]["body"]).id, saved.id)
            with patch("akasha.coordinator.board.gh", refuse), self.assertRaises(board.BoardError) as stopped:
                flow.cancel(root, saved.id)                          # the comment goes on, the issue update not
            self.assertIn(saved.id, str(stopped.exception))
            self.assertEqual(fake.issues[address]["state"], "OPEN")
            with patch("akasha.coordinator.board.gh", fake):
                flow.specify(root, saved.id, [], [], False)
        self.assertEqual(fake.issues[address]["state"], "CLOSED")
        self.assertEqual(board.parse(fake.issues[address]["body"]).status, "cancelled")
        self.assertEqual([item.id for item in tasks.all_tasks(root)], [saved.id])

    def test_an_issue_that_akasha_cannot_update_does_not_stop_a_request(self):
        root = make_repo(PASS)
        fake = FakeBoard()
        with person(fake=fake):
            first, _ = flow.start(root, "Add a date filter", "ops-a")
            first = tasks.load(root, first.id)
            first.stage, first.pull_request = "handover", PULL_REQUEST
            tasks.save(root, first)
            del fake.issues[first.board]                             # a person deleted the issue
            with patch("akasha.flow.github.merged", return_value=True):
                second, _ = flow.start(root, "Export the filtered list", "ops-b")
        self.assertEqual(tasks.load(root, first.id).status, "done")
        self.assertIn(second.board, fake.issues)

    def test_a_gate_needs_a_person_from_the_team_config(self):
        root = make_repo(PASS)
        with (root / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write('[roles]\ndevelopers = ["dev-a"]\n[risk]\nhigh = ["**/auth/**"]\n[approval]\nhigh = ["developer"]\n')
        task, _ = flow.start(root, "Change the login", "ops-member", workflow="small")
        with self.assertRaises(ValueError):
            flow.approve(root, task.id, "developer", "ops-member")
        flow.impact(root, task.id, IMPACT)
        (Path(task.workcopy) / "auth").mkdir()
        (Path(task.workcopy) / "auth" / "login.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(flow.advance(root, task.id), ["a developer must approve the high risk level"])
        flow.approve(root, task.id, "developer", "dev-a")
        self.assertEqual(flow.advance(root, task.id), [])

    def test_setup_writes_a_team_config_that_loads(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-setup-"))
        subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
        report = setup.run(folder, "")
        self.assertIn("Akasha wrote akasha.toml", report[0])
        team = config.load(folder)
        self.assertEqual((team.required_checks, team.approval), (("secrets",), {}))
        self.assertTrue((folder / config.PRODUCT_MAP).is_file())
        self.assertIn("akasha:start", (folder / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn(".akasha/work/", (folder / ".gitignore").read_text(encoding="utf-8"))

    def test_setup_does_nothing_in_a_ready_repository(self):
        root = make_repo(PASS)
        with patch("akasha.setup.github.status", return_value=[]):
            report = setup.run(root, "")
        self.assertEqual(len(report), 1)
        self.assertIn("ready", report[0])
        self.assertFalse((root / "AGENTS.md").exists())             # it writes nothing


class SharedTaskTests(unittest.TestCase):
    """Two copies of one repository, as on two computers, with the shared task board on GitHub."""

    def setUp(self):
        self.remote = add_remote(make_repo(PASS))
        self.first, self.second = clone(self.remote), clone(self.remote)
        self.fake = FakeBoard()

    def started(self, scope: list[str] | None = None) -> tasks.Task:
        """dev-a starts a small task in the first copy and changes search.py in its work copy."""
        with person("dev-a", "pc-a", self.fake):
            task, _ = flow.start(self.first, "Change the search", "ops-a", workflow="small", scope=scope)
        (Path(task.workcopy) / "search.py").write_text("x = 1\n", encoding="utf-8")
        return task

    def on_server(self, branch: str) -> str:
        found = workcopy.git(self.remote, "rev-parse", "--verify", "-q", branch)
        return found.stdout.strip() if found.returncode == 0 else ""

    def moved_main(self) -> str:
        """Another change merges on the default branch. Return its commit."""
        (self.first / "other.py").write_text("y = 1\n", encoding="utf-8")
        for args in (("add", "other.py"), ("commit", "-q", "-m", "other"), ("push", "-q", "origin", "main")):
            workcopy.git(self.first, *args)
        return workcopy.git(self.first, "rev-parse", "HEAD").stdout.strip()

    def test_another_person_takes_over_and_hands_over(self):
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.impact(self.first, task.id, IMPACT, map_note="The change adds no feature, screen, table, or API.")
            handed = flow.handoff(self.first, task.id)
        self.assertEqual((handed.holder, handed.workcopy), ("", ""))
        self.assertFalse(Path(task.workcopy).exists())
        self.assertNotEqual(workcopy.git(self.first, "rev-parse", "--verify", "-q", task.branch).returncode, 0)
        self.assertEqual(self.on_server(f"akasha-wip/{task.id}"), handed.wip)
        self.assertEqual(self.on_server(task.branch), "")          # the task branch waits until the checks pass
        output = io.StringIO()
        with redirect_stdout(output):
            hooks.turn_end(self.first)                                  # no work copy here: nothing to tell
        self.assertEqual(output.getvalue(), "")
        main = self.moved_main()
        with person("dev-b", "pc-b", self.fake):
            with self.assertRaises(flow.HolderError) as stopped:
                flow.advance(self.second, task.id)
            self.assertIn(f"akasha takeover {task.id}", str(stopped.exception))
            taken = flow.takeover(self.second, task.id)
            self.assertEqual((taken.holder, taken.holder_host), ("dev-b", "pc-b"))
            self.assertEqual(workcopy.changed_files(taken), ["search.py"])      # the base of the task stays
            self.assertEqual(flow.advance(self.second, task.id), [])
            self.assertEqual(flow.check(self.second, task.id).status["tests"], "PASS")
            with patch("akasha.flow.github.status", return_value=[]):
                self.assertEqual(flow.advance(self.second, task.id), [])
            flow.brief(self.second, task.id, BRIEFING)
            with github_merges_later() as gh:
                address, blocked = flow.handover(self.second, task.id)
            task = flow.load(self.second, task.id)
        self.assertEqual((address, [call.args[1:3] for call in gh.call_args_list]), (PULL_REQUEST, [("pr", "create")]))
        self.assertTrue(any("did not merge yet" in reason for reason in blocked))
        self.assertEqual(task.base, main)                               # the new base of the handover stays
        self.assertEqual(workcopy.changed_files(task), ["search.py"])
        shared = board.parse(self.fake.issues[task.board]["body"])
        self.assertEqual((shared.holder, shared.stage, shared.base, shared.wip, shared.pull_request),
                         ("dev-b", "handover", main, "", PULL_REQUEST))
        self.assertEqual(self.on_server(f"akasha-wip/{task.id}"), "")      # the task branch has the work now
        self.assertNotEqual(self.on_server(task.branch), "")

    def test_the_work_of_each_holder_stays(self):
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.handoff(self.first, task.id)
        with person("dev-b", "pc-b", self.fake):
            taken = flow.takeover(self.second, task.id)
            (Path(taken.workcopy) / "export.py").write_text("y = 2\n", encoding="utf-8")
            flow.handoff(self.second, task.id)
        with person("dev-a", "pc-a", self.fake):
            back = flow.takeover(self.first, task.id)
        self.assertEqual(workcopy.changed_files(back), ["export.py", "search.py"])
        with person("dev-b", "pc-b", self.fake), self.assertRaises(flow.HolderError) as stopped:
            flow.advance(self.second, task.id)
        self.assertIn(f"dev-a holds the task {task.id}", str(stopped.exception))

    def test_the_same_person_hands_off_in_the_other_copy_first(self):
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.check(self.first, task.id)                             # search.py is on the server
        (Path(task.workcopy) / "export.py").write_text("y = 2\n", encoding="utf-8")      # not on the server yet
        with person("dev-a", "pc-b", self.fake), self.assertRaises(flow.HolderError) as stopped:
            flow.takeover(self.second, task.id)
        self.assertIn(f"in another copy of the repository. Hand it off there with akasha handoff {task.id}",
                      str(stopped.exception))
        with person("dev-a", "pc-a", self.fake):
            flow.handoff(self.first, task.id)
        with person("dev-a", "pc-b", self.fake):
            moved = flow.takeover(self.second, task.id)
        self.assertEqual(workcopy.changed_files(moved), ["export.py", "search.py"])

    def test_an_old_work_copy_on_this_computer_only_goes_forward(self):
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.check(self.first, task.id)                             # the checks pass: the task branch is pushed
            stopped_task = flow.load(self.first, task.id)
            stopped_task.status = "stopped"                             # a developer can take it over without a handoff
            flow._publish(self.first, stopped_task)
        with person("dev-a", "pc-b", self.fake):                        # the same person in another copy
            moved = flow.takeover(self.second, task.id)
            (Path(moved.workcopy) / "export.py").write_text("y = 2\n", encoding="utf-8")
        old = Path(task.workcopy)
        with person("dev-a", "pc-a", self.fake), self.assertRaises(flow.HolderError) as stopped:
            flow.advance(self.first, task.id)
        self.assertIn("in another copy of the repository", str(stopped.exception))
        self.assertIn(f"still has a work copy of the task in {old}", str(stopped.exception))
        with person("dev-a", "pc-b", self.fake):
            flow.handoff(self.second, task.id)
        (old / "search.py").write_text("x = 3\n", encoding="utf-8")       # work that is not on the server
        with person("dev-a", "pc-a", self.fake):
            with self.assertRaises(RuntimeError) as stopped:
                flow.takeover(self.first, task.id)
            self.assertIn("cannot go forward to the work on the server", str(stopped.exception))
            workcopy.git(old, "checkout", "--", "search.py")
            back = flow.takeover(self.first, task.id)
        self.assertEqual(Path(back.workcopy), old)
        self.assertEqual(workcopy.changed_files(back), ["export.py", "search.py"])

    def test_a_folder_that_is_not_the_work_copy_stops_the_takeover(self):
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.handoff(self.first, task.id)
        (self.second / ".akasha" / "work" / task.id).mkdir(parents=True)     # git reads it as the main checkout
        main = workcopy.git(self.second, "rev-parse", "HEAD").stdout.strip()
        with person("dev-b", "pc-b", self.fake), self.assertRaises(RuntimeError) as stopped:
            flow.takeover(self.second, task.id)
        self.assertIn("not on the branch of the task", str(stopped.exception))
        self.assertEqual(workcopy.git(self.second, "rev-parse", "HEAD").stdout.strip(), main)    # main did not move

    def test_a_handoff_never_writes_over_newer_work(self):
        task = self.started()
        workcopy.git(self.second, "commit", "-q", "--allow-empty", "-m", "newer work")
        workcopy.git(self.second, "push", "-q", "origin", f"HEAD:refs/heads/akasha-wip/{task.id}")
        with person("dev-a", "pc-a", self.fake):
            with self.assertRaises(RuntimeError) as stopped:
                flow.handoff(self.first, task.id)
            self.assertIn("never forces", str(stopped.exception))
            kept = flow.load(self.first, task.id)
        self.assertEqual((kept.holder, Path(kept.workcopy).is_dir()), ("dev-a", True))

    def test_a_handoff_needs_a_clean_work_copy(self):
        task = self.started(scope=["search.py"])
        work = Path(task.workcopy)
        (work / "search.py").write_text("KEY = 'sk-" + "e" * 24 + "'\n", encoding="utf-8")
        with person("dev-a", "pc-a", self.fake):
            with self.assertRaises(RuntimeError) as stopped:
                flow.handoff(self.first, task.id)
            self.assertIn("secret keys: search.py:1", str(stopped.exception))
            (work / "search.py").write_text("x = 1\n", encoding="utf-8")
            (work / "notes.txt").write_text("made by a test\n", encoding="utf-8")
            with self.assertRaises(RuntimeError) as stopped:
                flow.handoff(self.first, task.id)
            self.assertIn("outside the scope: notes.txt", str(stopped.exception))
            self.assertEqual(self.on_server(f"akasha-wip/{task.id}"), "")
            (work / "notes.txt").unlink()
            flow.handoff(self.first, task.id)
        self.assertNotEqual(self.on_server(f"akasha-wip/{task.id}"), "")

    def test_a_handoff_keeps_the_main_checkout_safe(self):
        task = self.started()
        work = Path(task.workcopy)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(work)                                                  # a shell in the work copy
        with person("dev-a", "pc-a", self.fake), self.assertRaises(RuntimeError) as stopped:
            flow.handoff(self.first, task.id)
        os.chdir(self.first)
        self.assertIn(f"run the handoff in the main checkout {self.first}", str(stopped.exception))
        self.assertEqual(self.on_server(f"akasha-wip/{task.id}"), "")      # nothing went to the server
        refused = RuntimeError("git worktree remove failed: Permission denied")
        with person("dev-a", "pc-a", self.fake):
            with patch("akasha.flow.workcopy.remove", side_effect=refused), self.assertRaises(RuntimeError) as stopped:
                flow.handoff(self.first, task.id)                       # a program uses the work copy
            self.assertIn(f"Akasha handed off the task {task.id}", str(stopped.exception))
            shared = board.parse(self.fake.issues[task.board]["body"])
            self.assertEqual((shared.holder, shared.wip), ("", self.on_server(f"akasha-wip/{task.id}")))
            flow.takeover(self.first, task.id)
        workcopy.git(self.first, "worktree", "remove", "--force", str(work))
        work.mkdir()                                                    # an empty folder that a failed removal left
        (self.first / "draft.txt").write_text("not for the task\n", encoding="utf-8")
        main = workcopy.git(self.first, "rev-parse", "HEAD").stdout.strip()
        with person("dev-a", "pc-a", self.fake):
            for command in (flow.check, flow.handoff):
                with self.assertRaises(RuntimeError) as stopped:
                    command(self.first, task.id)
                self.assertIn("is not the work copy of the task", str(stopped.exception))
        self.assertEqual(workcopy.git(self.first, "rev-parse", "HEAD").stdout.strip(), main)    # main did not move

    def test_a_task_that_another_computer_cancelled_is_not_on_the_board_here(self):
        task = self.started(scope=["search.py"])
        with person("dev-a", "pc-a", self.fake):
            flow.handoff(self.first, task.id)
        with person("dev-b", "pc-b", self.fake):
            flow.takeover(self.second, task.id)
            flow.cancel(self.second, task.id)                           # dev-b has write access
        comments = len(self.fake.issues[task.board]["comments"])
        self.assertEqual(tasks.load(self.first, task.id).status, "open")       # the task file here is old
        with person("dev-a", "pc-a", self.fake):
            new, found = flow.start(self.first, "Add a date filter", "ops-b", scope=["search.py"])
            listed = board.read(self.first)[0]
        self.assertEqual((found, [item.id for item in listed]), ([], [new.id]))
        self.assertEqual(len(self.fake.issues[task.board]["comments"]), comments)

    def test_a_setup_that_passes_clears_the_old_output(self):
        with patch("akasha.flow.runner.prepare", return_value=("FAIL", "npm ERR! C:/Users/kim/app")):
            task = self.started()
        self.assertEqual(tasks.load(self.first, task.id).setup_output, "npm ERR! C:/Users/kim/app")
        self.assertNotIn("C:/Users/kim", self.fake.issues[task.board]["body"])
        with person("dev-a", "pc-a", self.fake):
            flow.handoff(self.first, task.id)
            flow.takeover(self.first, task.id)                          # the setup passes in the new work copy
        self.assertEqual(tasks.load(self.first, task.id).setup_output, "")

    def test_a_developer_takes_over_a_stopped_task(self):
        with (self.second / "akasha.toml").open("a", encoding="utf-8") as file:
            file.write('[roles]\ndevelopers = ["dev-c"]\n')
        task = self.started()
        with person("dev-a", "pc-a", self.fake):
            flow.check(self.first, task.id)
        with person("dev-b", "pc-b", self.fake), self.assertRaises(flow.HolderError) as stopped:
            flow.takeover(self.second, task.id)                         # an open task waits for its handoff
        self.assertIn(f"akasha handoff {task.id}", str(stopped.exception))
        with person("dev-a", "pc-a", self.fake):
            stopped_task = flow.load(self.first, task.id)
            stopped_task.status = "stopped"
            flow._publish(self.first, stopped_task)
        with person("dev-b", "pc-b", self.fake), self.assertRaises(ValueError):
            flow.takeover(self.second, task.id)                         # dev-b is not a developer
        with person("dev-c", "pc-c", self.fake):
            taken = flow.takeover(self.second, task.id)
        self.assertEqual((taken.holder, taken.status), ("dev-c", "stopped"))
        self.assertTrue((Path(taken.workcopy) / "search.py").is_file())
        told = self.fake.issues[task.board]["comments"][-1]
        self.assertTrue(told["body"].startswith(f"@dev-a Akasha: dev-c took over the stopped task {task.id}"))


class SharedStateTests(unittest.TestCase):
    def test_a_new_task_is_on_the_board_before_the_comparison(self):
        root = make_repo(PASS)
        fake = FakeBoard()
        compare, seen = flow._compare, []

        def compared(root, task):
            seen.append(task.board in fake.issues)
            return compare(root, task)

        output = io.StringIO()
        with person(fake=fake), patch("akasha.flow._compare", side_effect=compared):
            task, _ = flow.start(root, "Add a date filter", "ops-a", workflow="small", feature="search")
            with patch("akasha.__main__.main_root", return_value=root), redirect_stdout(output):
                command_line.run(["board"])
        self.assertEqual(seen, [True])
        shared = board.parse(fake.issues[task.board]["body"])
        self.assertEqual((shared.holder, shared.holder_host, shared.branch), ("dev-a", "pc-a", task.branch))
        self.assertIn("ops-a · holder dev-a · feature search · Add a date filter", output.getvalue())

    def test_the_newer_state_wins(self):
        root = make_repo(PASS)
        fake = FakeBoard()
        with person(fake=fake):
            task, _ = flow.start(root, "Add a date filter", "ops-a")
            read = flow.load(root, task.id)
            other = board.parse(fake.issues[task.board]["body"])        # another command writes the issue
            other.conditions, other.revision = ["Filter by the date"], other.revision + 1
            fake.issues[task.board]["body"] = board.body(other)
            with self.assertRaises(flow.HolderError) as stopped:
                flow._publish(root, read)
            self.assertIn("changed the task", str(stopped.exception))
            self.assertEqual(flow.load(root, task.id).conditions, ["Filter by the date"])
            flow.specify(root, task.id, ["Keep the order"], [], False)
        self.assertEqual(board.parse(fake.issues[task.board]["body"]).conditions,
                         ["Filter by the date", "Keep the order"])

    def test_a_task_of_akasha_1_0_0_goes_to_the_computer_with_its_file(self):
        root, other = make_repo(PASS), make_repo(PASS)
        fake = FakeBoard()
        old = tasks.Task(id="date-filter-0a1b", title="Add a date filter", workflow="feature", stage="request",
                         requester="ops-a", notes=["the setup command failed in the work copy: pip install "
                                                   "--index-url https://kim:token-1@pypi.example C:/Users/kim/app"])
        data = {name: getattr(old, name) for name in ("id", "title", "workflow", "stage", "status", "requester",
                                                      "feature", "scope", "contracts", "risk", "conditions",
                                                      "accepted", "builds_on", "pull_request")}
        old.board = fake.add(f"Requester: ops-a\n\n```akasha-scope\n{json.dumps(data)}\n```\n")
        tasks.save(root, old)
        with person("dev-b", "pc-b", fake), self.assertRaises(RuntimeError) as stopped:
            flow.takeover(other, old.id)
        self.assertIn("Akasha 1.0.0", str(stopped.exception))
        with person("dev-a", "pc-a", fake):
            flow.specify(root, old.id, ["Filter by the date"], [], False)
        shared = board.parse(fake.issues[old.board]["body"])
        self.assertEqual((shared.format, shared.holder, shared.conditions), (2, "dev-a", ["Filter by the date"]))
        self.assertNotIn("token-1", fake.issues[old.board]["body"])        # the old setup output stays here
        self.assertEqual(shared.notes, [flow._setup_note(old)])
        self.assertIn("token-1", tasks.load(root, old.id).setup_output)

    def test_a_body_without_the_format_does_not_stop_the_holder(self):
        root = make_repo(PASS)
        fake = FakeBoard()
        with person(fake=fake):
            task, _ = flow.start(root, "Add a date filter", "ops-a")
            data = {"id": task.id, "title": task.title, "workflow": "feature", "stage": "request"}
            fake.issues[task.board]["body"] = f"Requester: ops-a\n\n```akasha-scope\n{json.dumps(data)}\n```\n"
            flow.specify(root, task.id, ["Filter by the date"], [], False)      # Akasha 1.0.0 wrote the issue
        shared = board.parse(fake.issues[task.board]["body"])
        self.assertEqual((shared.format, shared.holder, shared.conditions), (2, "dev-a", ["Filter by the date"]))

    def test_a_task_without_an_issue_goes_to_the_person_here(self):
        root = make_repo(PASS)
        recorded, _ = flow.start(root, "Add a date filter", "ops-a", workflow="small")    # origin is not GitHub yet
        self.assertEqual((recorded.holder, recorded.board), ("", ""))
        old = tasks.Task(id="export-0a1b", title="Export the list", workflow="feature", stage="request")
        tasks.save(root, old)                                   # Akasha 1.0.0, and its board write failed
        add_remote(root)
        fake = FakeBoard()
        with person(fake=fake):
            for task_id in (recorded.id, old.id):
                flow.specify(root, task_id, ["Filter by the date"], [], False)
                shared = board.parse(fake.issues[tasks.load(root, task_id).board]["body"])
                self.assertEqual((shared.holder, shared.holder_host), ("dev-a", "pc-a"))
            handed = flow.handoff(root, recorded.id)            # the holder can hand it off
            broken = tasks.Task(id="import-0a1b", title="Import", workflow="feature", stage="request",
                                board=fake.add("A person damaged the body"), revision=4, synced=4)
            tasks.save(root, broken)                            # handed off here; another person can hold it
            with self.assertRaises(flow.HolderError):
                flow.specify(root, broken.id, ["Import a file"], [], False)
        self.assertEqual((handed.holder, Path(recorded.workcopy).exists()), ("", False))


def said(number: int, author: str, text: str, association: str = "MEMBER", edited: bool = False,
         hidden: bool = False) -> board.Comment:
    return board.Comment(number, author, association, "2026-10-31T00:00:00Z", edited, hidden, text)


class DecisionRuleTests(unittest.TestCase):
    """The rules for the decision comments on the issue of a task."""

    def setUp(self):
        self.task = tasks.Task(id="t-1", title="x", workflow="feature", stage="inspection", requester="Ops-A",
                               conditions=["Filter by the date", "Keep the order"], spec_rev=2, risk="high",
                               approvals={"requester": "ops-a"}, accepted={"Filter by the date": True})

    def reasons(self, team: config.Team, comments: list[board.Comment]) -> list[tuple[int, str]]:
        return [(comment.number, reason) for comment, reason in flow._decided(team, self.task, comments)]

    def test_the_requester_decides_for_the_current_specification(self):
        self.assertEqual(self.reasons(config.Team(), [
            said(1, "dev-b", "/approve spec r2"), said(2, "ops-a", "/approve spec r1"),
            said(3, "ops-a", "/approve spec r2", edited=True), said(4, "ops-a", "/approve spec r2", hidden=True),
            said(5, "ops-a", "/accept 1 r2"), said(6, "ops-a", "/reject 2 r2 the order is wrong"),
            said(7, "ops-a", "/accept 3 r2"), said(8, "ops-a", "/accept 1 r1"), said(9, "ops-a", "Looks good")]), [
            (1, "only the requester Ops-A makes this decision"), (2, "it is not for the current specification r2"),
            (3, "somebody edited the comment"), (4, "somebody hid the comment"),
            (7, "the task has no completion condition 3"), (8, "it is not for the current specification r2")])
        self.assertEqual(self.task.approvals, {})                   # the value in the body or the task file is gone
        self.assertEqual(self.task.accepted, {"Filter by the date": True, "Keep the order": False})
        self.assertIn("ops-a rejected the completion condition 2: the order is wrong", self.task.notes)
        self.reasons(config.Team(), [said(1, "@OPS-A", "/Approve spec R2"), said(2, "ops-a", "/reject all r2"),
                                     said(3, "ops-a", "/accept 2 r2\nThe order is correct now")])
        self.assertEqual((self.task.approvals, self.task.accepted),     # a later comment wins
                         ({"requester": "@OPS-A"}, {"Filter by the date": False, "Keep the order": True}))

    def test_a_gate_role_approves_its_risk_level(self):
        team = config.Team(administrators=("admin-a",), approval={"high": ("administrator",), "medium": ("developer",)})
        self.assertEqual(self.reasons(team, [said(1, "admin-a", "/approve risk medium"),
                                             said(2, "dev-b", "/approve risk high"),
                                             said(3, "admin-a", "/approve risk high")]), [
            (1, "the risk level of the task is high now"), (2, "dev-b has no gate role for the high risk level")])
        self.assertEqual(self.task.approvals, {"administrator": "admin-a"})
        anyone = config.Team(approval={"high": ("developer",)})     # akasha.toml names no developer
        self.assertEqual(self.reasons(anyone, [said(1, "ops-b", "/approve risk high", "NONE"),
                                               said(2, "dev-c", "/approve risk high", "COLLABORATOR")]),
                         [(1, "ops-b has no gate role for the high risk level")])
        self.assertEqual(self.task.approvals, {"developer": "dev-c"})

    def test_a_resume_counts_once_after_the_stop(self):
        team = config.Team(developers=("dev-c",))
        self.task.status, self.task.failures, self.task.stopped_comment = "stopped", 3, 5
        comments = [said(4, "dev-c", "/resume"), said(6, "dev-b", "/resume"), said(7, "dev-c", "/resume")]
        self.assertEqual(self.reasons(team, comments), [
            (4, "it is older than the last stop of the task. Write a new /resume"),
            (6, "only a developer opens a stopped task again")])
        self.assertEqual((self.task.status, self.task.failures, self.task.resumed), ("open", 0, 7))
        self.task.status, self.task.stopped_comment = "stopped", 9          # the task stops again
        self.assertEqual(self.reasons(team, comments), [])
        self.assertEqual(self.task.status, "stopped")

    def test_only_the_requester_or_a_developer_cancels(self):
        team = config.Team(developers=("dev-c",))
        self.assertEqual(self.reasons(team, [said(1, "dev-b", "/cancel")]),
                         [(1, "only the requester or a developer cancels the task")])
        self.assertEqual(self.task.status, "open")
        self.assertEqual(self.reasons(team, [said(1, "ops-a", "/cancel not needed now")]), [])
        self.assertEqual(self.task.status, "cancelled")
        self.assertIn("ops-a cancelled the task: not needed now", self.task.notes)


class DecisionTests(unittest.TestCase):
    """With GitHub, a decision is a comment on the issue from the GitHub account of the person who decides."""

    def setUp(self):
        self.root, self.fake = make_repo(PASS), FakeBoard()

    def recorded(self, roles: str = "", workflow: str = "feature") -> tasks.Task:
        """dev-a records a task of ops-a with two completion conditions."""
        if roles:
            with (self.root / "akasha.toml").open("a", encoding="utf-8") as file:
                file.write(roles)
        with person("dev-a", "pc-a", self.fake):
            task, _ = flow.start(self.root, "Add a date filter", "ops-a", workflow=workflow)
            flow.specify(self.root, task.id, ["Filter by the date", "Keep the order"], [], False)
            return flow.load(self.root, task.id)

    def comments(self, task: tasks.Task) -> list[tuple[str, str]]:
        return [(item["author"]["login"], item["body"]) for item in self.fake.issues[task.board]["comments"]]

    def test_decisions_count_only_from_the_comments_of_the_person(self):
        task = self.recorded()
        self.assertEqual(task.spec_rev, 1)
        self.fake.say(task.board, "dev-b", "/approve spec r1")                   # another account
        self.fake.say(task.board, "ops-a", "/approve spec r1", edited=True)      # dev-b edited a comment of ops-a
        shared = board.parse(self.fake.issues[task.board]["body"])
        shared.approvals = {"requester": "ops-a"}                                # a person edits the issue body
        self.fake.issues[task.board]["body"] = board.body(shared)
        with person("dev-a", "pc-a", self.fake):
            flow.impact(self.root, task.id, IMPACT)
            self.assertEqual(flow.advance(self.root, task.id), [])               # to the specification stage
            blocked = flow.advance(self.root, task.id)
            self.assertIn(f"the requester did not approve the specification. ops-a writes `/approve spec r1` on "
                          f"{task.board}", blocked)
            self.assertEqual([item.split(" — ")[-1] for item in flow.ignored(task.id)],
                             ["only the requester ops-a makes this decision", "somebody edited the comment"])
            self.fake.say(task.board, "ops-a", "/approve spec r1")
            self.assertEqual(flow.advance(self.root, task.id), [])
            self.assertEqual(flow.load(self.root, task.id).stage, "build")
            task = flow.specify(self.root, task.id, ["Show the newest first"], [], False)[0]
            self.assertEqual((task.spec_rev, task.stage, task.approvals), (2, "specification", {}))
            self.assertIn("ops-a writes `/approve spec r2`", flow.advance(self.root, task.id)[0])
        self.assertEqual(board.parse(self.fake.issues[task.board]["body"]).approvals, {})

    def test_the_same_computer_writes_the_decision_of_its_own_account(self):
        task = self.recorded()
        with person("dev-a", "pc-a", self.fake):
            for by in ("", "ops-a"):
                with self.assertRaises(PermissionError) as refused:
                    flow.approve(self.root, task.id, "requester", by)
                self.assertIn(f"ops-a must write the comment `/approve spec r1` on {task.board}",
                              str(refused.exception))
            with self.assertRaises(PermissionError):
                flow.accept(self.root, task.id, "1", True)
        self.assertEqual(self.comments(task), [])
        with person("ops-a", "pc-b", self.fake):                                  # the requester at this computer
            self.assertEqual(flow.approve(self.root, task.id, "requester").approvals, {"requester": "ops-a"})
            accepted = flow.accept(self.root, task.id, "Keep the order", True)
            rejected = flow.accept(self.root, task.id, None, False, "The dates are wrong")
        self.assertEqual(accepted.accepted, {"Keep the order": True})
        self.assertEqual(rejected.accepted, {"Filter by the date": False, "Keep the order": False})
        self.assertEqual(self.comments(task), [("ops-a", "/approve spec r1"), ("ops-a", "/accept 2 r1"),
                                               ("ops-a", "/reject all r1 The dates are wrong")])

    def test_a_gate_needs_a_comment_of_a_person_with_the_role(self):
        task = self.recorded('[roles]\nadministrators = ["admin-a"]\n[risk]\nhigh = ["**/auth/**"]\n'
                             '[approval]\nhigh = ["administrator"]\n', workflow="small")
        (Path(task.workcopy) / "auth").mkdir()
        (Path(task.workcopy) / "auth" / "login.py").write_text("x = 1\n", encoding="utf-8")
        with person("dev-a", "pc-a", self.fake):
            flow.impact(self.root, task.id, IMPACT)
            self.assertEqual(flow.advance(self.root, task.id), [
                "a administrator must approve the high risk level. A person with that role writes "
                f"`/approve risk high` on {task.board}"])
            with self.assertRaises(PermissionError) as refused:
                flow.approve(self.root, task.id, "administrator")
            self.assertIn("admin-a must write the comment `/approve risk high`", str(refused.exception))
        with person("admin-a", "pc-c", self.fake):
            flow.approve(self.root, task.id, "administrator")
        with person("dev-a", "pc-a", self.fake):
            self.assertEqual(flow.advance(self.root, task.id), [])

    def test_a_stopped_task_waits_for_a_resume_comment(self):
        self.root = make_repo(FAIL)
        task = self.recorded('[roles]\ndevelopers = ["dev-c"]\n', workflow="small")
        with person("dev-a", "pc-a", self.fake):
            for _ in range(3):
                flow.check(self.root, task.id)
            stopped = flow.load(self.root, task.id)
            self.assertIn(f"A developer examines the problem, then writes `/resume` on {task.board}",
                          flow.advance(self.root, task.id)[0])
        author, text = self.comments(task)[-1]
        self.assertTrue(text.startswith(f"@dev-c Akasha stopped the task {task.id}"))
        self.assertEqual((stopped.status, stopped.stopped_comment), ("stopped", 100))
        with person("dev-b", "pc-b", self.fake), self.assertRaises(PermissionError):
            flow.resume(self.root, task.id)                                      # not a developer
        with person("dev-c", "pc-c", self.fake):
            self.assertEqual(flow.resume(self.root, task.id).status, "open")
        self.assertEqual(board.parse(self.fake.issues[task.board]["body"]).status, "stopped")    # dev-a holds it
        with person("dev-a", "pc-a", self.fake):
            self.assertEqual(flow.check(self.root, task.id).status["tests"], "FAIL")      # a new count of repairs
            shared = board.parse(self.fake.issues[task.board]["body"])
            self.assertEqual((shared.status, shared.failures, shared.resumed), ("open", 1, 101))
            for _ in range(2):
                flow.check(self.root, task.id)
            self.assertEqual(flow.load(self.root, task.id).status, "stopped")    # the old /resume does not count

    def test_a_cancel_closes_the_pull_request_and_tells_the_later_tasks(self):
        task = self.recorded('[roles]\ndevelopers = ["dev-c"]\n', workflow="small")
        with person("dev-a", "pc-a", self.fake):
            later, _ = flow.start(self.root, "Export the filtered list", "ops-b", workflow="small", builds_on=task.id)
            held = flow.load(self.root, task.id)
            held.stage, held.pull_request = "handover", PULL_REQUEST
            flow._publish(self.root, held)
        self.fake.say(task.board, "dev-b", "/cancel")                             # not the requester or a developer
        with person("dev-b", "pc-b", self.fake), self.assertRaises(PermissionError) as refused:
            flow.cancel(self.root, task.id)
        self.assertIn("ops-a or dev-c must write the comment `/cancel`", str(refused.exception))
        with person("ops-a", "pc-b", self.fake):                                  # the requester, on any computer
            self.assertEqual(flow.cancel(self.root, task.id, reason="not needed now").status, "cancelled")
        self.assertEqual(self.fake.issues[task.board]["state"], "OPEN")           # the holder closes the rest
        opened = {"url": PULL_REQUEST, "state": "OPEN"}
        with person("dev-a", "pc-a", self.fake), patch("akasha.flow.github.pull_request", return_value=opened), \
                patch("akasha.flow.gh", return_value=answer()) as gh:
            self.assertIn("dev-b: /cancel — only the requester or a developer cancels the task",
                          flow.ignored(flow.load(self.root, task.id).id))
        self.assertEqual([call.args[1:3] for call in gh.call_args_list],
                         [("pr", "merge"), ("pr", "edit"), ("pr", "close")])
        self.assertIn("--disable-auto", gh.call_args_list[0].args)
        self.assertEqual(self.fake.issues[task.board]["state"], "CLOSED")
        shared = board.parse(self.fake.issues[task.board]["body"])
        self.assertIn("ops-a cancelled the task: not needed now", shared.notes)
        told = self.fake.issues[later.board]["comments"][-1]["body"]
        self.assertTrue(told.startswith(f"@ops-b Akasha: the earlier task {task.id}"))

    def test_the_requester_is_a_github_account(self):
        self.fake.accounts = {"ops-a": "Ops-A"}
        with person("dev-a", "pc-a", self.fake):
            self.assertEqual(flow.start(self.root, "Add a date filter")[0].requester, "dev-a")    # by default, you
            self.assertEqual(flow.start(self.root, "Export", "@ops-a")[0].requester, "Ops-A")
            with self.assertRaises(ValueError) as refused:
                flow.start(self.root, "Import", "nobody-x")
            self.assertIn("GitHub has no account nobody-x", str(refused.exception))
            with patch("akasha.coordinator.board.can_comment", return_value=False):
                warned, _ = flow.start(self.root, "Print", "ops-a")
        self.assertIn("Ops-A has no access to this private repository", warned.notes[0])
        with self.assertRaises(ValueError):
            flow.start(make_repo(PASS), "Add a date filter")                     # without GitHub, a name is necessary

    def test_show_numbers_the_conditions_and_tells_what_does_not_count(self):
        task = self.recorded()
        self.fake.say(task.board, "dev-b", "/approve spec r1")
        output = io.StringIO()
        with person("dev-a", "pc-a", self.fake), patch("akasha.__main__.main_root", return_value=self.root), \
                redirect_stdout(output):
            self.assertEqual(command_line.run(["show", task.id]), 0)
        for line in ("  specification: r1", "  condition 1: Filter by the date", "  condition 2: Keep the order",
                     "  not counted — dev-b: /approve spec r1 — only the requester ops-a makes this decision"):
            self.assertIn(line, output.getvalue().splitlines())


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

    def test_a_problem_in_a_hook_never_stops_the_agent(self):
        with patch("akasha.engine.hooks.main", side_effect=RuntimeError("damaged task file")), \
                redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(command_line.run(["hook", "--event", "Stop"]), 0)
        self.assertIn("damaged task file", errors.getvalue())

    def test_session_start_without_a_team_config(self):
        folder = Path(tempfile.mkdtemp(prefix="akasha-plain-"))
        subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps({"cwd": str(folder)}))), redirect_stdout(output):
            self.assertEqual(hooks.main("claude", "SessionStart"), 0)
        self.assertIn("akasha-setup", output.getvalue())
        self.assertIn(Path(sys.executable).as_posix(), output.getvalue())

    def test_session_start_shows_the_team_context(self):
        root = make_repo(PASS)
        (root / ".akasha" / "context").mkdir(parents=True)
        (root / ".akasha" / "context" / "decisions.md").write_text("# Decisions\n", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            hooks.session_start(root)
        self.assertIn(".akasha/context/decisions.md", output.getvalue())

    def test_session_start_shows_the_tasks_of_this_person_from_the_board(self):
        root = make_repo(PASS)
        fake = FakeBoard()
        for task_id, holder, host, requester in (("held-1", "dev-a", "pc-a", "ops-x"),
                                                 ("elsewhere-1", "dev-a", "pc-b", "ops-x"),
                                                 ("asked-1", "dev-b", "pc-b", "@Dev-A"), ("free-1", "", "", "dev-a"),
                                                 ("other-1", "dev-b", "pc-b", "ops-x")):
            fake.add(board.body(tasks.Task(id=task_id, title=f"Task {task_id}", workflow="small", stage="build",
                                           holder=holder, holder_host=host, requester=requester)))
        output = io.StringIO()
        with person(fake=fake), patch("akasha.engine.hooks._server_notice", return_value=[]), redirect_stdout(output):
            hooks.session_start(root)
        text = output.getvalue()
        for line in ("Task held-1: open, stage build, risk low, you hold it, Task held-1",
                     "Task elsewhere-1: open, stage build, risk low, you hold it in another copy: hand it off there",
                     "Task asked-1: open, stage build, risk low, dev-b holds it",
                     "Task free-1: open, stage build, risk low, nobody holds it"):
            self.assertIn(line, text)
        self.assertNotIn("other-1", text)
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)), \
                patch("akasha.coordinator.board.available", return_value=True), \
                patch("akasha.engine.hooks._server_notice", return_value=[]), redirect_stdout(io.StringIO()) as local:
            tasks.save(root, tasks.Task(id="local-1", title="x", workflow="small", stage="build"))
            hooks.session_start(root)                                   # gh does not answer: the tasks here
        self.assertIn("Task local-1: open, stage build, risk low, x", local.getvalue())

    def test_session_start_examines_the_server_rules_first(self):
        root = make_repo(PASS)

        def notice(problems: list[str], admin: bool) -> str:
            (root / github.SERVER_STATE).unlink(missing_ok=True)
            output = io.StringIO()
            with patch("akasha.infra.github.repository", return_value=("team/app", "main")), \
                    patch("akasha.infra.github.settings", return_value={"permissions": {"admin": admin}}), \
                    patch("akasha.infra.github.protection", return_value=None), \
                    patch("akasha.infra.desired.drift", return_value=problems), \
                    patch("akasha.infra.github._server_file", side_effect=lambda r, b, p: None), \
                    patch("akasha.infra.desired.workflows", return_value={}), \
                    patch("akasha.infra.desired.block", return_value=""), \
                    patch("akasha.infra.desired.codeowners", return_value=""), redirect_stdout(output):
                hooks.session_start(root)
            return output.getvalue()

        self.assertNotIn("server rules", notice([], admin=False))                # ready: nothing to tell
        self.assertIn("You administer this repository", notice(["the check akasha is not required"], admin=True))
        self.assertIn("Ask an administrator", notice(["the check akasha is not required"], admin=False))
        plan = notice([desired.NO_PLAN], admin=True)                             # the setup switches to the helpers
        self.assertIn("merge and watch workflows of Akasha", plan)
        self.assertIn("You administer this repository", plan)
        with patch("akasha.infra.github.status") as examined, redirect_stdout(io.StringIO()):
            hooks.session_start(root)                                            # a fresh record needs no network
        examined.assert_not_called()


if __name__ == "__main__":
    unittest.main()
