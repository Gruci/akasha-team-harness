"""The review of the plan by another AI: nine written items, one row each. A PASS mark counts only when each item
passed, and the answer stays in review.md. Real git repositories, without GitHub."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from akasha import flow, pr, review
from akasha.task import load
from tests.helpers import Repository, rows

QUIET = {key: "" for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDECODE")}


class ReviewItemTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        for patcher in (patch("webbrowser.open"), patch.dict(os.environ, QUIET)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.task, _notes = flow.start(self.root, "Date filter", name="date-filter")
        self.records = Path(self.task.workcopy) / ".akasha" / "tasks" / self.task.id
        (self.records / "plan.md").write_text("# Plan\n- change app.py\n", encoding="utf-8")

    def tearDown(self):
        self.repo.close()

    def answer(self, table: str, verdict: str = "PASS"):
        sha = review.plan_digest(load(self.root, self.task.id))
        told = review.on_subagent_stop(self.root, {"agent_type": "akasha-reviewer", "last_assistant_message":
                                                   f"{table}\n\nNotes:\n- none\n\nAKASHA-REVIEW: {self.task.id} {sha} "
                                                   f"{verdict}"})
        return load(self.root, self.task.id), told

    def test_a_pass_with_each_item_passes_and_stays_in_the_records(self):
        task, told = self.answer(rows())
        self.assertTrue(review.passed(task))
        self.assertEqual(set(task.review["items"]), set(review.ITEMS["plan"]))
        kept = (self.records / review.REVIEW).read_text(encoding="utf-8")
        self.assertIn("| R9 | PASS | read it |", kept)
        self.assertIn("Round 1 · PASS", kept)
        self.assertIn("R1–R9 PASS, see review.md", "\n".join(pr.meta(task)))
        self.assertIn("gave PASS", told)

    def test_a_pass_without_a_row_for_each_item_is_changes(self):
        table = "\n".join(line for line in rows().splitlines() if "R3" not in line)
        task, told = self.answer(table)
        self.assertFalse(review.passed(task))
        self.assertEqual(task.review["verdict"], "CHANGES")
        self.assertIn("no verdict for R3", task.review["problem"])
        self.assertIn("did not count", told)
        self.assertIn("did not count (no verdict for R3)", review.told(task))
        self.assertIn("the PASS mark did not count", "\n".join(pr.meta(task)))

    def test_a_pass_over_a_failed_item_is_changes(self):
        task, _told = self.answer(rows(R4="FAIL"))
        self.assertEqual((task.review["verdict"], task.review["problem"]), ("CHANGES", "R4 failed"))

    def test_only_some_items_may_be_na(self):
        task, _told = self.answer(rows(R9="N/A", R5="N/A"))
        self.assertTrue(review.passed(task))
        self.assertIn("(N/A R5, R9)", "\n".join(pr.meta(task)))
        task, _told = self.answer(rows(R3="N/A"))
        self.assertIn("R3 cannot be N/A", task.review["problem"])

    def test_a_changes_mark_names_the_failed_items(self):
        task, _told = self.answer(rows(R2="FAIL", R6="FAIL"), verdict="CHANGES")
        self.assertEqual(task.review["verdict"], "CHANGES")
        self.assertNotIn("problem", task.review)
        self.assertIn("failed: R2, R6", "\n".join(pr.meta(task)))
        self.assertEqual(task.review["rounds"], 1)

    def test_the_rows_can_name_the_item_and_change_their_case(self):
        table = rows().replace("| R1 |", "| R1 Preview |").replace("| PASS |", "| pass |")
        task, _told = self.answer(table)
        self.assertTrue(review.passed(task))

    def test_a_quick_task_has_its_own_items(self):
        self.assertEqual(review.ITEMS["quick"], ("Q1", "Q2", "Q3"))
        self.assertEqual(review.problem(load(self.root, self.task.id), review.verdicts(rows("quick"))),
                         "no verdict for R1, R2, R3, R4, R5, R6, R7, R8, R9")


if __name__ == "__main__":
    unittest.main()
