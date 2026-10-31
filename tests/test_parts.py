"""The parts around the task: the board, the review mark, the approval words, the files of Codex and Claude Code,
the GitHub files, and the watch."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import approval, board, claude, codex, config, github, review, watch
from akasha.task import Task, block, parse_block


class ApprovalWordTests(unittest.TestCase):
    def test_short_approvals(self):
        for text in ("승인", "승인합니다!", "ㅇㅇ", "네", "좋아 진행해", "ok, go ahead", "LGTM", "이대로 진행"):
            with self.subTest(text=text):
                self.assertTrue(approval.is_approval(text))

    def test_feedback_is_not_an_approval(self):
        for text in ("승인 말고 버튼 색 바꿔", "좋아 근데 제목은 고쳐", "승인?", "아니", "no", "not yet",
                     "좋아요 그런데 표 하나 더 추가해 줘", "진행 상황 알려줘 그리고 이 부분 다시 설명해 줄래요 길게"):
            with self.subTest(text=text):
                self.assertFalse(approval.is_approval(text))


class TaskBlockTests(unittest.TestCase):
    def test_the_block_goes_and_comes_back_without_the_local_path(self):
        task = Task(id="a", title="end --> of comment", scope=["x/**"], workcopy="C:/secret/path",
                    approval={"by": "me"}, stats={"review_rounds": 2})
        text = f"summary\n\n{block(task)}\n"
        self.assertNotIn("C:/secret", text)
        again = parse_block(text)
        self.assertEqual((again.title, again.scope, again.approval, again.workcopy),
                         ("end --> of comment", ["x/**"], {"by": "me"}, ""))


class DigestTests(unittest.TestCase):
    """A real run: the preview had CRLF on one computer and LF on the next (core.autocrlf), and the approval did not
    match after a handoff (2026-10-31)."""

    def test_the_line_ends_do_not_change_the_digest(self):
        from akasha.task import digest
        with tempfile.TemporaryDirectory() as folder:
            one, two = Path(folder) / "a.html", Path(folder) / "b.html"
            one.write_bytes(bytes([60, 112, 62, 13, 10]) * 2)        # <p> with CRLF
            two.write_bytes(bytes([60, 112, 62, 10]) * 2)            # <p> with LF
            self.assertEqual(digest(one), digest(two))
            self.assertEqual(digest(Path(folder) / "missing"), "")


class BoardTests(unittest.TestCase):
    items = [{"number": 3, "title": "Tax", "url": "u3", "headRefName": "akasha/tax", "isDraft": True,
              "author": {"login": "Kim"}, "assignees": [], "files": [{"path": "billing/tax.py"}],
              "body": block(Task(id="tax", title="Tax", scope=["billing/**"]))},
             {"number": 4, "title": "Mine", "url": "u4", "headRefName": "akasha/mine", "isDraft": False,
              "author": {"login": "me"}, "assignees": [{"login": "me"}], "files": [], "body": "no block"}]

    def test_reads_the_open_pull_requests(self):
        entries = board._entries(self.items)
        self.assertEqual([entry.task.id for entry in entries], ["tax", "akasha/mine"])
        self.assertEqual((entries[0].holder, entries[0].person), ("", "kim"))
        lines = board.lines(entries, "me")
        self.assertIn("(you)", lines[1])
        self.assertIn("free · draft", lines[0])

    def test_overlaps_by_plan_and_by_changed_files(self):
        entries = board._entries(self.items)
        mine = Task(id="new", title="New", scope=["billing/invoice.py"])
        self.assertEqual(len(board.overlaps(mine, [], entries)), 1)
        other = Task(id="new", title="New", scope=["web/**"])
        self.assertEqual(board.overlaps(other, ["billing/tax.py"], entries)[0][:2], "#3")
        self.assertEqual(board.overlaps(other, ["web/a.py"], entries), [])


class ReviewMarkTests(unittest.TestCase):
    def test_reads_the_last_answer_from_a_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "t.jsonl"
            lines = [{"message": {"role": "user", "content": "go"}},
                     {"message": {"role": "assistant", "content": [{"type": "text", "text": "AKASHA-REVIEW: a "
                                                                    "0123456789ab PASS"}]}}]
            path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
            self.assertIn("PASS", review._last_text(str(path)))


class FileTests(unittest.TestCase):
    def test_codex_hooks_keep_the_hooks_of_the_team(self):
        team = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}]}}
        text = codex.hooks_text("\ufeff" + json.dumps(team))
        again = codex.hooks_text(text)
        self.assertEqual(text, again)
        data = json.loads(text)
        commands = [hook["command"] for group in data["hooks"]["PreToolUse"] for hook in group["hooks"]]
        self.assertEqual(commands[0], "mine")
        self.assertEqual(sum("-m akasha hook" in command for command in commands), 1)
        self.assertIn("UserPromptSubmit", data["hooks"])
        self.assertIsNone(codex.hooks_text("not json"))

    def test_agents_md_keeps_the_text_of_the_team(self):
        text = codex.agents_text("# Team\n\nOur rules.\n")
        self.assertEqual(codex.agents_text(text), text)
        self.assertTrue(text.startswith("# Team"))

    def test_claude_settings_turn_the_plugin_on_and_keep_the_rest(self):
        text = claude.settings_text(json.dumps({"hooks": {"Stop": []}, "enabledPlugins": {"x@y": True}}))
        data = json.loads(text)
        self.assertEqual(data["hooks"], {"Stop": []})
        self.assertTrue(data["enabledPlugins"]["akasha@akasha"] and data["enabledPlugins"]["x@y"])
        self.assertEqual(data["extraKnownMarketplaces"]["akasha"]["source"]["repo"], "Gruci/akasha-team-harness")
        self.assertIsNone(claude.settings_text("[1, 2]"))


class GitHubFileTests(unittest.TestCase):
    def test_the_files_follow_the_team(self):
        own_ci = config.parse('[ci]\nrequired = ["checks"]\n[server]\nrules = "akasha"\n')
        self.assertEqual(list(github.workflows(own_ci)), [github.WATCH_FILE])
        self.assertEqual(github.leftovers(own_ci), [github.CHECK_FILE])
        plain = config.parse('[ci]\nruns-on = ["self-hosted", "Windows"]\n')
        files = github.workflows(plain)
        self.assertEqual(list(files), [github.CHECK_FILE])
        self.assertIn('runs-on: ["self-hosted", "Windows"]', files[github.CHECK_FILE])
        for text in list(files.values()) + list(github.workflows(own_ci).values()):
            self.assertNotIn("@@", text)
        self.assertEqual(github.protection(own_ci)["required_status_checks"]["contexts"], ["checks"])

    def test_codeowners_block(self):
        team = config.parse('[team]\nadmins = ["a"]\nreviewers = ["b", "c"]\n[risk]\npaths = ["db/**"]\n')
        owners = github.codeowners(team)
        self.assertIn("db/** @b @c", owners)
        self.assertIn("/akasha.toml @a", owners)
        merged = github.merge_block("* @team\n", owners)
        self.assertTrue(merged.startswith("* @team") and merged.endswith("# akasha:end\n"))
        self.assertEqual(github.merge_block(merged, owners), merged)


class WatchTests(unittest.TestCase):
    team = config.parse('[team]\nadmins = ["a"]\nreviewers = ["b"]\n[risk]\npaths = ["db/**"]\n[ci]\n'
                        'required = ["checks"]\n')

    def answers(self, pulls, runs, reviews=()):
        def api(_root, path):
            if path.endswith("/pulls"):
                return pulls
            if "check-runs" in path:
                return {"check_runs": runs}
            if path.endswith("/status"):
                return {"statuses": []}
            return list(reviews)
        return api

    def test_reasons(self):
        merged = [{"number": 5, "merged_at": "x", "head": {"sha": "h"}}]
        good = [{"name": "checks", "conclusion": "success"}]
        root = Path.cwd()
        with patch("akasha.watch._api", self.answers([], good)):
            self.assertIn("did not come", watch._reason(root, "o/r", self.team, "s"))
        with patch("akasha.watch._api", self.answers(merged, [])):
            self.assertIn("before checks passed", watch._reason(root, "o/r", self.team, "s"))
        with patch("akasha.watch._api", self.answers(merged, good)), \
                patch("akasha.repo.names", return_value=["db/x.sql"]):
            self.assertIn("without the review", watch._reason(root, "o/r", self.team, "s"))
        approved = [{"user": {"login": "B"}, "state": "APPROVED"}]
        with patch("akasha.watch._api", self.answers(merged, good, approved)), \
                patch("akasha.repo.names", return_value=["db/x.sql"]):
            self.assertEqual(watch._reason(root, "o/r", self.team, "s"), "")


if __name__ == "__main__":
    unittest.main()
