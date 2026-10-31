import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from akasha.coordinator import board, overlap, resources
from akasha.core import task as tasks
from akasha.core.task import Task

NOT_LOGGED_IN = "To get started with GitHub CLI, please run:  gh auth login"


def task(task_id: str, **values) -> Task:
    return Task(id=task_id, title=task_id, workflow="feature", stage="request", **values)


def answer(stdout: object = "", code: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout if isinstance(stdout, str) else json.dumps(stdout), stderr)


class FakeBoard:
    """GitHub issues in memory, for the gh calls of the board. It records each call. A broken board fails each call,
    as gh does when nobody logged in."""

    def __init__(self, broken: bool = False, login: str = "dev-a"):
        self.broken, self.login = broken, login
        self.issues: dict[str, dict] = {}
        self.calls: list[tuple[str, ...]] = []
        self.accounts: dict[str, str] | None = None      # lower case -> the exact name. None: GitHub has each account
        self.private = False
        self.permissions: dict[str, str] = {}            # lower case -> the permission. Each other account: write

    def add(self, text: str, state: str = "OPEN", comments: list[dict] | None = None) -> str:
        address = f"https://github.com/team/app/issues/{len(self.issues) + 1}"
        self.issues[address] = {"body": text, "state": state, "comments": comments or []}
        return address

    def say(self, address: str, login: str, text: str, association: str = "MEMBER", edited: bool = False) -> int:
        """A person writes a comment on GitHub. Return its number."""
        number = 100 + sum(len(item["comments"]) for item in self.issues.values())
        self.issues[address]["comments"].append({"author": {"login": login}, "authorAssociation": association,
                                                 "body": text, "createdAt": "2026-10-31T00:00:00Z",
                                                 "includesCreatedEdit": edited, "isMinimized": False,
                                                 "url": f"{address}#issuecomment-{number}"})
        return number

    def __call__(self, root, *args, payload=None, timeout=60):
        self.calls.append(args)
        if self.broken:
            return answer("", 1, NOT_LOGGED_IN)
        value = lambda name: args[args.index(name) + 1] if name in args else ""     # noqa: E731
        verb = args[:2]
        if verb == ("label", "create"):
            return answer()
        if args[:1] == ("api",) and args[1].startswith("users/"):
            name = args[1].removeprefix("users/")
            login = name if self.accounts is None else self.accounts.get(name.lower(), "")
            return answer({"login": login}) if login else answer("", 1, "gh: Not Found (HTTP 404)")
        if args[:1] == ("api",) and args[1].endswith("/permission"):
            return answer({"permission": self.permissions.get(args[1].split("/")[-2].lower(), "write")})
        if args[:1] == ("api",):
            return answer({"private": self.private})
        if verb == ("issue", "create"):
            return answer(self.add(value("--body")) + "\n")
        if verb == ("issue", "list"):
            words = value("--search").replace(" in:body", "")
            found = [{name: issue[name] if name != "url" else address for name in value("--json").split(",")}
                     for address, issue in self.issues.items()
                     if (value("--state") == "all" or issue["state"] == "OPEN") and words in issue["body"]]
            return answer(found)
        issue = self.issues.get(args[2] if len(args) > 2 else "")
        if issue is None:
            return answer("", 1, "GraphQL: Could not resolve to an issue or pull request")
        if verb == ("issue", "edit"):
            issue["body"] = value("--body")
        elif verb == ("issue", "close"):
            issue["state"] = "CLOSED"
        elif verb == ("issue", "comment"):
            return answer(f"{args[2]}#issuecomment-{self.say(args[2], self.login, value('--body'))}\n")
        elif verb == ("issue", "view"):
            fields = value("--json").split(",")
            return answer({name: issue[name] if name != "url" else args[2] for name in fields})
        return answer()


class OverlapTests(unittest.TestCase):
    def test_join_order_and_notify(self):
        mine = task("a", feature="customer-search-filter", scope=["src/search/**"], contracts=["customers-api"])
        others = [task("b", feature="customer-search-filter"),
                  task("c", scope=["src/search/date.py"]),
                  task("d", contracts=["customers-api"]),
                  task("e", scope=["src/billing/**"], feature="invoices"),
                  task("f", feature="customer-search-filter", status="done"),
                  task("g", scope=["src/search/**"], status="stopped")]
        kinds = {(item.kind, item.other) for item in overlap.find(mine, others)}
        self.assertEqual(kinds, {("stack", "b"), ("order", "c"), ("notify", "d"), ("order", "g")})

    def test_a_task_and_the_task_that_it_builds_on_do_not_overlap(self):
        earlier = task("a", feature="search-filter", scope=["src/search/**"])
        later = task("b", feature="search-filter", scope=["src/search/**"], builds_on="a")
        self.assertEqual(overlap.find(later, [earlier]), [])
        self.assertEqual(overlap.find(earlier, [later]), [])
        self.assertIn("Build the new task on the earlier task", overlap.ACTIONS["stack"])

    def test_messages_tell_the_action(self):
        found = overlap.find(task("a", scope=["src/**"]), [task("b", scope=["src/app.py"])])
        self.assertIn("Akasha does not set the sequence: the task that merges later gets the earlier change",
                      found[0].message())

    def test_a_task_does_not_overlap_itself(self):
        mine = task("a", feature="x", scope=["src/**"])
        self.assertEqual(overlap.find(mine, [mine]), [])


class BoardTests(unittest.TestCase):
    def test_the_scope_block_goes_and_comes_back(self):
        mine = task("date-filter-0a1b", feature="customer-search-filter", scope=["src/search/**"], risk="medium",
                    conditions=["Filter by the date", "Keep the order\n```akasha-scope\n{}\n```"],
                    accepted={"Filter by the date": True}, approvals={"requester": "ops-a"}, briefing="## Why\n\nx",
                    notes=["the setup command failed in the work copy"], base="a" * 40, branch="akasha/x",
                    holder="dev-a", holder_host="pc-a", revision=3, wip="b" * 40, spec_rev=2, stopped_comment=104,
                    resumed=107, workcopy="C:/work/date-filter-0a1b", synced=3, setup_output="C:/Users/dev-a/.env: KEY",
                    port=4236, previewed=True, board="https://github.com/team/app/issues/1")
        text = board.body(mine)
        self.assertEqual(board.parse(text), replace(mine, workcopy="", synced=0, setup_output="", port=0,
                                                    previewed=False, board=""))
        for name in tasks.LOCAL_FIELDS:                                      # the fields of one computer stay there
            self.assertNotIn(f'"{name}"', text)
        self.assertNotIn("C:/", text)
        for line in ("Holder: dev-a (pc-a)", "Completion conditions (specification r2):",
                     "1. [accepted] Filter by the date", "2. [not inspected] Keep the order", "Approvals: requester ops-a",
                     "- `/approve spec r2`: the requester approves the specification",
                     "- `/approve risk medium`: a person with a gate role approves the risk level"):
            self.assertIn(line, text)
        self.assertIn("nobody — `akasha takeover t-1`", board.body(task("t-1")))
        self.assertIsNone(board.parse("an issue without a block"))
        self.assertIsNone(board.parse("```akasha-scope\nnot json\n```"))

    def test_a_body_of_akasha_1_0_0_and_a_wrong_value(self):
        data = {"id": "t-1", "title": "x", "workflow": "feature", "stage": "request", "revision": "2"}
        parsed = board.parse(f"Requester: ops-a\n\n```akasha-scope\n{json.dumps(data)}\n```\n")
        self.assertEqual((parsed.id, parsed.format, parsed.revision), ("t-1", 1, 0))      # the wrong type: default

    def test_find_takes_only_the_issue_with_exactly_the_id(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        fake.add(board.body(task("date-filter-0a1b2c3d-old")))
        closed = fake.add(board.body(task("date-filter-0a1b2c3d", status="done")), state="CLOSED")
        with patch("akasha.coordinator.board.gh", fake):
            found = board.find(root, "date-filter-0a1b2c3d")
            self.assertEqual((found.id, found.board), ("date-filter-0a1b2c3d", closed))
            searched = fake.calls[-1]
            self.assertEqual(searched[searched.index("--search") + 1], "date-filter-0a1b2c3d in:body")
            self.assertEqual(searched[searched.index("--state") + 1], "all")
            self.assertIsNone(board.find(root, "date-filter-9f9f9f9f"))
            tasks.save(root, task("date-filter-0a1b2c3d", board=closed))      # this computer knows the issue
            fake.calls.clear()
            self.assertEqual(board.find(root, "date-filter-0a1b2c3d").board, closed)
        self.assertEqual(fake.calls, [("issue", "view", closed, "--json", "body,url")])

    def test_a_board_on_github_that_fails_stops_the_command(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        tasks.save(root, task("date-filter-0a1b2c3d"))
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)):
            self.assertEqual(board.read(root)[1], "local")                 # without GitHub, as before
            self.assertIsNone(board.find(root, "date-filter-0a1b2c3d"))
            self.assertEqual(board.publish(root, task("date-filter-0a1b2c3d")), "")
            self.assertFalse(board.comment(root, "https://github.com/team/app/issues/1", "text"))
            with patch("akasha.coordinator.board.available", return_value=True):
                for action in (lambda: board.read(root), lambda: board.find(root, "date-filter-0a1b2c3d"),
                               lambda: board.publish(root, task("date-filter-0a1b2c3d")),
                               lambda: board.comments(root, "https://github.com/team/app/issues/1"),
                               lambda: board.comment(root, "https://github.com/team/app/issues/1", "text")):
                    with self.assertRaises(board.BoardError) as stopped:
                        action()
                    self.assertIn("gh auth status", str(stopped.exception))
                    self.assertIn("gh auth login", str(stopped.exception))

    def test_without_github_akasha_writes_no_issue(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        address = fake.add(board.body(task("t-1")))                    # origin was on GitHub before
        with patch("akasha.coordinator.board.gh", fake):
            self.assertEqual(board.publish(root, task("t-1", board=address, status="cancelled")), "")
            self.assertEqual(board.publish(root, task("t-2")), "")
        self.assertEqual((fake.calls, fake.issues[address]["state"], len(fake.issues)), ([], "OPEN", 1))

    def test_publish_examines_each_write(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        mine = task("date-filter-0a1b2c3d")
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.coordinator.board.available", return_value=True):
            address = board.publish(root, mine)
            self.assertEqual(board.parse(fake.issues[address]["body"]).id, mine.id)
            mine.status = "cancelled"
            board.publish(root, mine)
            self.assertEqual(fake.issues[address]["state"], "CLOSED")
            del fake.issues[address]                                       # a person deleted the issue
            with self.assertRaises(board.BoardError):
                board.publish(root, mine)

    def test_comments_tell_the_number_the_account_and_the_edits(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        address = fake.add("body", comments=[
            {"author": {"login": "Ops-A"}, "authorAssociation": "NONE", "body": "/approve spec r1",
             "createdAt": "2026-10-31T01:00:00Z", "includesCreatedEdit": True, "isMinimized": False,
             "url": "https://github.com/team/app/issues/1#issuecomment-123456"}])
        with patch("akasha.coordinator.board.gh", fake):
            self.assertEqual(board.posted(root, address, "/approve risk high"), 101)
            first, second = board.comments(root, address)
        self.assertEqual(first, board.Comment(123456, "Ops-A", "NONE", "2026-10-31T01:00:00Z", True, False,
                                              "/approve spec r1"))
        self.assertEqual((second.number, second.author, second.edited, second.body, second.writer),
                         (101, "dev-a", False, "/approve risk high", True))

    def test_github_tells_who_has_write_access(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        fake.permissions = {"reader-a": "read", "member-a": "read"}
        address = fake.add("body")
        for login, association, text in (("owner-a", "OWNER", "/resume"), ("dev-c", "COLLABORATOR", "/resume"),
                                         ("reader-a", "COLLABORATOR", "/resume"), ("member-a", "MEMBER", "/cancel"),
                                         ("dev-c", "MEMBER", "Looks good"), ("guest-a", "NONE", "/resume")):
            fake.say(address, login, text, association)
        with patch("akasha.coordinator.board.gh", fake):
            found = board.comments(root, address)
            self.assertEqual([comment.writer for comment in found], [True, True, False, False, False, False])
            board.comments(root, address)
        asked = [call[1] for call in fake.calls if call[0] == "api"]      # only for a decision comment, and only once
        self.assertEqual(asked, [f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission"
                                 for login in ("dev-c", "reader-a", "member-a")])

    def test_the_hooks_read_a_copy_of_the_board(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        fake.add(board.body(task("t-1", scope=["src/**"])))
        listed = lambda: [call for call in fake.calls if call[:2] == ("issue", "list")]      # noqa: E731
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.coordinator.board.available", return_value=True):
            self.assertEqual([item.id for item in board.cached(root)], ["t-1"])
            fake.add(board.body(task("t-2")))
            self.assertEqual([item.id for item in board.cached(root)], ["t-1"])          # the copy is not old yet
            self.assertEqual(len(listed()), 1)
            self.assertEqual([item.id for item in board.cached(root, max_age=0)], ["t-1", "t-2"])     # an old copy
            board.read(root)
            board.find(root, "t-2")
            self.assertEqual(len(listed()), 4)                                         # the commands read the board
            board.publish(root, task("t-3"))
            self.assertFalse((root / board.CACHE_FILE).exists())                       # a board write removes it
            self.assertEqual([item.id for item in board.cached(root)], ["t-1", "t-2", "t-3"])
        broken = FakeBoard(broken=True)
        with patch("akasha.coordinator.board.gh", broken), \
                patch("akasha.coordinator.board.available", return_value=True):
            board.forget(root)
            self.assertIsNone(board.cached(root))                                      # gh does not answer
            self.assertIsNone(board.cached(root))
            self.assertEqual(len(broken.calls), 1)                     # the next hook does not wait for gh again
            with patch("akasha.coordinator.board.FAILED_AGE", 0):
                self.assertIsNone(board.cached(root))                                  # later, it asks gh again
            self.assertEqual(len(broken.calls), 2)
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.coordinator.board.available", return_value=True):
            self.assertIsNone(board.cached(root))
            board.publish(root, task("t-4"))                                           # gh works: a board write
            self.assertEqual([item.id for item in board.cached(root)], ["t-1", "t-2", "t-3", "t-4"])
        self.assertIsNone(board.cached(root))                                          # without GitHub

    def test_the_session_start_reads_the_board_and_the_comments_at_once(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        address = fake.add(board.body(task("t-1")))
        fake.say(address, "ops-a", "/approve spec r1", "NONE")
        fake.add(board.body(task("t-2", status="done")), state="CLOSED")
        with patch("akasha.coordinator.board.gh", fake), \
                patch("akasha.coordinator.board.available", return_value=True):
            [(found, said)] = board.overview(root, timeout=3)
            self.assertEqual([item.id for item in board.cached(root)], ["t-1"])           # the copy of the hooks too
        self.assertEqual((found.id, found.board), ("t-1", address))
        self.assertEqual(said, [board.Comment(100, "ops-a", "NONE", "2026-10-31T00:00:00Z", False, False,
                                              "/approve spec r1")])
        self.assertEqual(fake.calls, [("issue", "list", "--label", "akasha", "--state", "open", "--limit", "500",
                                       "--json", "body,url,comments")])
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)), \
                patch("akasha.coordinator.board.available", return_value=True):
            self.assertIsNone(board.overview(root))

    def test_an_account_is_the_name_that_github_gives(self):
        root = Path(tempfile.mkdtemp(prefix="akasha-board-"))
        fake = FakeBoard()
        fake.accounts = {"ops-a": "Ops-A", "ops-b": "ops-b", "kim_acme": "kim_acme"}
        fake.permissions = {"ops-a": "read", "ops-b": "none"}
        with patch("akasha.coordinator.board.gh", fake), patch("akasha.repo.gh_repo", return_value="team/app"):
            self.assertEqual((board.account(root, "@OPS-A"), board.account(root, "nobody")), ("Ops-A", ""))
            self.assertEqual(board.account(root, "kim_acme"), "kim_acme")      # Enterprise Managed Users
            self.assertEqual(board.account(root, "a/../../repos"), "")          # not the shape of a GitHub name
            self.assertEqual(board.account(root, "Kim Minsu"), "")
            self.assertTrue(board.can_comment(root, "ops-b"))                    # a public repository
            fake.private = True
            self.assertEqual((board.can_comment(root, "ops-a"), board.can_comment(root, "ops-b")), (True, False))
        with patch("akasha.coordinator.board.gh", FakeBoard(broken=True)), \
                patch("akasha.coordinator.board.available", return_value=True), self.assertRaises(board.BoardError):
            board.account(root, "ops-a")


class ResourceTests(unittest.TestCase):
    """The preview ports of the person on this computer, in a reservations file of the test."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="akasha-ports-"))
        self.ports = Path(tempfile.mkdtemp(prefix="akasha-home-")) / ".akasha" / "ports.json"
        reservations = patch("akasha.coordinator.resources.PORTS", self.ports)
        reservations.start()
        self.addCleanup(reservations.stop)

    def held(self, root: Path, task_id: str) -> Task:
        """A task with a work copy in the copy of the repository at root."""
        work = root / ".akasha" / "work" / task_id
        work.mkdir(parents=True)
        mine = task(task_id, workcopy=str(work))
        tasks.save(root, mine)
        return mine

    def reserved(self) -> dict:
        return json.loads(self.ports.read_text(encoding="utf-8"))

    def test_two_tasks_with_the_same_first_port_get_their_own_ports(self):
        first, second = self.held(self.root, "task-000c"), self.held(self.root, "task-0022")
        other = Path(tempfile.mkdtemp(prefix="akasha-ports-"))                  # another clone on this computer
        with patch("akasha.coordinator.resources.busy", return_value=False):
            self.assertEqual((resources.port(self.root, first), resources.port(self.root, second)), (4236, 4237))
            self.assertEqual((first.port, second.port), (4236, 4237))
            self.assertEqual(resources.port(self.root, first), 4236)                    # again the same port
            self.assertEqual(resources.port(self.root, replace(first, port=0)), 4236)   # also from the reservation
            self.assertEqual(resources.port(other, self.held(other, "task-000c")), 4238)
            resources.release(self.root, second)
            self.assertEqual(second.port, 0)
            self.assertNotIn("task-0022", self.reserved()[os.path.normcase(str(self.root.resolve()))])
            Path(first.workcopy).rmdir()                  # the work copy went away: nothing needs the port now
            self.assertEqual(resources.port(self.root, second), 4236)
        self.assertEqual(len(self.reserved()), 2)

    def test_a_damaged_task_file_in_another_clone_keeps_its_port(self):
        other = Path(tempfile.mkdtemp(prefix="akasha-ports-"))                  # another clone on this computer
        folder = other / ".akasha" / "state" / "tasks"
        with patch("akasha.coordinator.resources.busy", return_value=False):
            self.assertEqual(resources.port(other, self.held(other, "task-000c")), 4236)
            self.assertEqual(resources.port(other, self.held(other, "task-0022")), 4237)
            (folder / "task-000c.json").write_text("[]\n", encoding="utf-8")       # a person damaged the files
            damaged = {**asdict(task("task-0022")), "workcopy": 5}
            (folder / "task-0022.json").write_text(json.dumps(damaged), encoding="utf-8")
            self.assertEqual(resources.port(self.root, self.held(self.root, "task-000c")), 4238)
        kept = self.reserved()[os.path.normcase(str(other.resolve()))]            # Akasha cannot read them
        self.assertEqual(kept, {"task-000c": 4236, "task-0022": 4237})
        with self.assertRaises(ValueError):
            tasks.load(other, "task-000c")
        self.assertEqual([found.id for found in tasks.all_tasks(other)], ["task-0022"])

    def test_a_port_that_a_program_uses_on_ipv6_is_skipped(self):
        try:
            listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        except OSError:
            self.skipTest("this computer has no IPv6")
        self.addCleanup(listener.close)
        try:
            listener.bind(("::1", 4236))
            listener.listen()
        except OSError:
            self.skipTest("this computer has no IPv6 on ::1, or a program uses the port 4236")
        self.assertTrue(resources.busy(4236))
        self.assertNotEqual(resources.port(self.root, self.held(self.root, "task-000c")), 4236)

    def test_the_reservations_have_a_lock(self):
        self.ports.parent.mkdir(parents=True)
        lock = self.ports.with_name("ports.json.lock")
        lock.write_text("", encoding="utf-8")
        with patch("akasha.coordinator.resources.LOCK_SECONDS", 0.2), self.assertRaises(RuntimeError) as held:
            resources.port(self.root, self.held(self.root, "task-000c"))
        self.assertIn("another Akasha command holds the lock", str(held.exception))
        old = time.time() - resources.STALE_SECONDS - 5                    # from a command that stopped
        os.utime(lock, (old, old))
        with patch("akasha.coordinator.resources.busy", return_value=False):
            self.assertEqual(resources.port(self.root, tasks.load(self.root, "task-000c")), 4236)
        self.assertFalse(lock.exists())

    def test_the_values_get_the_task_name_and_only_a_port_in_the_range(self):
        self.assertEqual(resources.fill("app_{task}", "date-filter-0a1b"), "app_date_filter_0a1b")
        self.assertEqual(resources.fill("--port {port}", "date-filter-0a1b", 4236), "--port 4236")
        for port in (0, 80, 4900, "4236 & del *", True, 4236.0):
            with self.assertRaises(ValueError):
                resources.fill("--port {port}", "date-filter-0a1b", port)


if __name__ == "__main__":
    unittest.main()
