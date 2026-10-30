import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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

        with patch("akasha.coordinator.board.available", return_value=True):
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
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)):
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

        with patch("akasha.coordinator.board.available", return_value=True):
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
                flow.cancel(root, saved.id, "ops-a")
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
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.coordinator.board.available", return_value=True):
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
