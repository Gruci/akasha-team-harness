"""An agent task: an agent account ([team] agents) works from the request of a person, without a preview, and the
person approves the result before the merge. Real git repositories, and the GitHub of the landing tests."""

import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import agent, approval, checks, config, flow, hooks, land, pr, review, watch
from akasha.guard import check_edit
from akasha.task import Task, all_local, block, load, save
from tests.helpers import TEAM, Repository
from tests.test_land import answers, view

AGENT_TEAM = TEAM.replace('admins = ["admin-a", "admin-b"]\n', 'admins = ["admin-a", "admin-b"]\nagents = ["mis-bot"]\n')
REQUEST = "수탁고 배치가 어제 실패했어요. 원인은 빈 응답이에요. app.py 에서 빈 응답을 건너뛰게 고쳐 주세요."
QUIET = {key: "" for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE")}


class AgentConfigTests(unittest.TestCase):
    def test_the_agent_accounts_are_github_names(self):
        team = config.parse('[team]\nadmins = ["lead"]\nagents = ["@MIS-Bot"]\n')
        self.assertEqual(team.agents, ("mis-bot",))
        self.assertTrue(agent.account(team, "mis-bot"))
        self.assertFalse(agent.account(team, "lead"))
        self.assertFalse(agent.account(config.parse(""), "mis-bot"))

    def test_an_agent_account_is_never_an_administrator(self):
        """An administrator is free of the locked files and of the core approval: an agent account never is."""
        for text in ('[team]\nadmins = ["bot"]\nagents = ["bot"]\n', '[team]\nown_procedure = ["Bot"]\nagents = ["bot"]\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.parse(text)

    def test_the_pull_request_names_the_person_through_the_agent_account(self):
        task = Task(id="t", title="T", kind="agent")
        self.assertIn("- Result: not approved yet", pr.meta(task))
        self.assertIn("Kind: agent task", pr.meta(task)[0])
        task.approval = {"by": "홍길동", "through": "mis-bot", "at": "now", "words": "머지", "change_sha": "abc",
                         "source": "result"}
        self.assertIn("홍길동 through @mis-bot", "\n".join(pr.meta(task)))
        task.approval["by"] = "mis-bot"
        self.assertIn("Result approved by @mis-bot at", "\n".join(pr.meta(task)))


class AgentLanding(unittest.TestCase):
    """An agent task that is ready to land, and the GitHub of the landing tests."""
    rules = "akasha"
    protected = False

    def setUp(self):
        self.repo = Repository(AGENT_TEAM + f'\n[server]\nrules = "{self.rules}"\n')
        self.root = self.repo.root
        for target in ("webbrowser.open", "time.sleep"):
            patch(target, return_value=None).start()
        patch.dict(os.environ, QUIET).start()
        self.gh = patch("akasha.repo.gh", side_effect=self.github).start()
        patch("akasha.pr.gh", self.gh).start()
        self.me = patch("akasha.repo.me", return_value="mis-bot").start()
        patch("akasha.repo.origin", return_value="o/r").start()
        patch("akasha.board.available", return_value=True).start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.repo.close()

    def github(self, _root, *args, **_kwargs):
        import subprocess
        return subprocess.CompletedProcess([], 0, "", "")

    def calls(self, word: str) -> list:
        return [call.args for call in self.gh.call_args_list if word in call.args]

    def own_merges(self) -> list:
        return [call for call in self.calls("merge") if "--match-head-commit" in call]

    def records(self, task) -> Path:
        return Path(task.workcopy) / ".akasha" / "tasks" / task.id

    def started(self, request: str = REQUEST):
        agent.keep_prompt(self.root, "", request)
        with patch("akasha.board.available", return_value=False):
            task, _notes = flow.start(self.root, "배치 빈 응답 건너뛰기", name="empty-reply")
        return task

    def ready(self):
        """The request kept, the plan reviewed, the change built and checked on this computer."""
        task = self.started()
        records = self.records(task)
        (records / "plan.md").write_text("plan", encoding="utf-8")
        review.note(self.root, load(self.root, task.id), "PASS", review.plan_digest(load(self.root, task.id)),
                    "reviewer")
        (records / "summary.md").write_text("## 문제\n빈 응답\n## 조치\n건너뛴다\n", encoding="utf-8")
        (Path(task.workcopy) / "app.py").write_text("print('skip empty')\n", encoding="utf-8")
        task = load(self.root, task.id)
        task.number, task.pr = 7, "https://github.com/o/r/pull/7"
        save(self.root, task)
        self.check(task.id)
        return load(self.root, task.id)

    def check(self, task_id: str):
        with patch("akasha.repo.gh_json", side_effect=answers()):
            result, _notes = flow.check(self.root, task_id)
        self.assertTrue(all(value == "PASS" for value in result.status.values()), result.details)

    def land(self, task, wait=0):
        head = load(self.root, task.id).checks["commit"]
        with patch("akasha.pr.view", return_value=view(head)), \
                patch("akasha.repo.gh_json", side_effect=answers(protected=self.protected)):
            return land.land(self.root, task.id, wait=wait)

    def answer(self, task, words: str):
        approval.on_prompt(self.root, self.root, words)
        return flow.approve(self.root, task.id)


class AgentStartTests(AgentLanding):
    def test_the_request_is_the_prompt_word_for_word(self):
        task = self.started()
        self.assertEqual((task.kind, task.status), ("agent", "approved"))
        self.assertIn(REQUEST, (self.records(task) / agent.REQUEST).read_text(encoding="utf-8"))

    def test_no_task_without_a_fresh_prompt_of_this_session(self):
        with patch("akasha.board.available", return_value=False), self.assertRaises(ValueError):
            flow.start(self.root, "no request", name="none")
        agent.keep_prompt(self.root, "", REQUEST)
        kept = json.loads((self.root / agent.PROMPT).read_text(encoding="utf-8"))
        (self.root / agent.PROMPT).write_text(json.dumps({**kept, "at": time.time() - 700}), encoding="utf-8")
        with patch("akasha.board.available", return_value=False), self.assertRaises(ValueError):
            flow.start(self.root, "old request", name="old")
        agent.keep_prompt(self.root, "session-a", REQUEST)
        with patch("akasha.board.available", return_value=False), \
                patch("akasha.approval.session", return_value="session-b"), self.assertRaises(ValueError):
            flow.start(self.root, "other session", name="other")

    def test_an_agent_account_makes_no_quick_task(self):
        agent.keep_prompt(self.root, "", REQUEST)
        with patch("akasha.board.available", return_value=False), self.assertRaises(ValueError):
            flow.start(self.root, "quick", name="quick", fast=True)

    def test_only_the_prompts_of_an_agent_account_are_kept(self):
        payload = {"prompt": REQUEST, "session_id": "s"}
        self.me.return_value = "a-person"
        hooks.on_prompt(self.root, self.root, payload)
        self.assertFalse((self.root / agent.PROMPT).exists())
        self.me.return_value = "mis-bot"
        hooks.on_prompt(self.root, self.root, payload)
        self.assertEqual(agent.kept_request(self.root, "s"), REQUEST)
        self.assertEqual(agent.kept_request(self.root, "t"), "")

    def test_a_person_makes_no_agent_task(self):
        self.me.return_value = "a-person"
        agent.keep_prompt(self.root, "", REQUEST)
        with patch("akasha.board.available", return_value=False):
            task, _notes = flow.start(self.root, "a person", name="person")
        self.assertEqual(task.kind, "full")

    def test_the_code_changes_only_after_the_review_of_the_plan(self):
        task = self.started()
        path = Path(task.workcopy) / "app.py"
        team = flow.rules(self.root)

        def reason():
            return check_edit(path, self.root, all_local(self.root), True, flow.gate, False,
                              checks.locked(team, "mis-bot"))
        self.assertIn("not ready to build", reason() or "")
        (self.records(task) / "plan.md").write_text("plan", encoding="utf-8")
        task = load(self.root, task.id)
        review.note(self.root, task, "PASS", review.plan_digest(task), "reviewer")
        self.assertIsNone(reason())
        locked = Path(task.workcopy) / "db" / "schema.sql"
        self.assertIn("only an administrator", check_edit(locked, self.root, all_local(self.root), True, flow.gate,
                                                          False, checks.locked(team, "mis-bot")) or "")


class AgentLandTests(AgentLanding):
    def setUp(self):
        super().setUp()
        self.task = self.ready()

    def test_the_landing_asks_the_person_and_does_not_merge(self):
        state, lines = self.land(self.task)
        self.assertEqual(state, land.ASK)
        self.assertIn("akasha result", lines[-1])
        self.assertFalse(self.own_merges())
        task = load(self.root, self.task.id)
        self.assertEqual((task.status, task.checks["asked"]), ("landing", task.checks["commit"]))

    def test_the_result_before_the_landing_asked_is_refused(self):
        with self.assertRaises(ValueError):
            flow.result(self.root, self.task.id)

    def test_the_approved_result_merges(self):
        self.land(self.task)
        text = flow.result(self.root, self.task.id)
        self.assertIn("빈 응답", text)
        self.assertIn("https://github.com/o/r/compare/", text)
        self.assertIn("- app.py", text)
        _task, message = self.answer(self.task, "[akasha-from: 홍길동] 네, 머지해 주세요")
        self.assertIn("akasha land", message)
        task = load(self.root, self.task.id)
        self.assertEqual({key: task.approval[key] for key in ("by", "through", "source")},
                         {"by": "홍길동", "through": "mis-bot", "source": "result"})
        self.assertEqual(task.approval["change_sha"], agent.digest(task))
        state, _lines = self.land(self.task)
        self.assertNotEqual(state, land.ASK)
        self.assertTrue(self.own_merges())

    def test_no_approval_without_a_message_after_the_result(self):
        self.land(self.task)
        approval.on_prompt(self.root, self.root, "earlier words")                     # before the result
        flow.result(self.root, self.task.id)
        with self.assertRaises(ValueError):
            flow.approve(self.root, self.task.id)

    def test_a_change_after_the_approval_asks_again(self):
        self.land(self.task)
        flow.result(self.root, self.task.id)
        self.answer(self.task, "좋아요")
        (Path(self.task.workcopy) / "app.py").write_text("print('skip empty, log it')\n", encoding="utf-8")
        self.check(self.task.id)
        self.assertIn("did not approve this version", agent.missing(load(self.root, self.task.id)))
        state, _lines = self.land(self.task)
        self.assertEqual(state, land.ASK)
        self.assertFalse(self.own_merges())

    def test_the_next_step_waits_for_the_person(self):
        self.land(self.task)
        self.assertIn("akasha result", flow.next_step(load(self.root, self.task.id)))
        flow.result(self.root, self.task.id)
        self.assertIn("Wait for the message of the person", flow.next_step(load(self.root, self.task.id)))
        self.answer(self.task, "좋아요")
        self.assertIn("Land the task", flow.next_step(load(self.root, self.task.id)))


class AgentAutoMergeTests(AgentLanding):
    """GitHub protects the branch and merges with its auto-merge: never before the person approved the result."""
    rules = "github"
    protected = True

    def test_the_auto_merge_waits_for_the_approval(self):
        task = self.ready()
        state, _lines = self.land(task)
        self.assertEqual(state, land.ASK)
        self.assertFalse([call for call in self.calls("merge") if "--auto" in call])
        flow.result(self.root, task.id)
        self.answer(task, "좋아요")
        self.land(task)
        self.assertTrue([call for call in self.calls("merge") if "--auto" in call])


class AgentWatchTests(unittest.TestCase):
    team = config.parse('[team]\nadmins = ["a"]\nagents = ["bot"]\n[ci]\nrequired = ["checks"]\n')
    good = [{"name": "checks", "conclusion": "success"}]

    def reason(self, author: str, task: Task) -> str:
        pulls = [{"number": 5, "merged_at": "x", "head": {"sha": "h", "ref": "akasha/t"}, "user": {"login": author},
                  "body": block(task)}]

        def api(_root, path):
            if path.endswith("/pulls"):
                return pulls
            return {"check_runs": self.good} if "check-runs" in path else {"statuses": []}
        with patch("akasha.watch._api", api), patch("akasha.repo.names", return_value=["app.py"]), \
                patch("akasha.config.shown", return_value="[team]\n"):
            return watch._reason(Path.cwd(), "o/r", self.team, "s")

    def test_reasons(self):
        approved = {"by": "홍길동", "through": "bot", "change_sha": "abc", "source": "result"}
        done = Task(id="t", title="T", kind="agent", approval=approved, review={"verdict": "PASS"})
        self.assertEqual(self.reason("bot", done), "")
        self.assertIn("is not an agent account", self.reason("me", done))
        self.assertIn("without an approved result", self.reason("bot", Task(id="t", title="T", kind="agent",
                                                                            review={"verdict": "PASS"})))
        full = Task(id="t", title="T", approval={"by": "bot", "source": "prompt"}, review={"verdict": "PASS"})
        self.assertIn("was not an agent task", self.reason("bot", full))


if __name__ == "__main__":
    unittest.main()
