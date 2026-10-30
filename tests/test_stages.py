import tempfile
import unittest
from pathlib import Path

from akasha import config
from akasha.core import stages
from akasha.core.task import Task, all_tasks, load, new_id, save


def feature() -> config.Workflow:
    return config.load(Path(tempfile.gettempdir())).workflows["feature"]


class StageTests(unittest.TestCase):
    def setUp(self):
        self.flow = feature()
        self.task = Task(id="t-1", title="Date filter", workflow="feature", stage="request")

    def test_a_task_waits_until_the_conditions_are_clear(self):
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), ["conditions_clear"])
        self.task.conditions = ["Filter by the transaction date"]
        self.task.open_questions = ["Must customers without permission be visible?"]
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), ["conditions_clear"])
        self.task.open_questions = []
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), [])
        self.assertEqual(self.task.stage, "specification")

    def test_the_specification_needs_the_impact_analysis_and_the_gate_roles(self):
        self.task.stage, self.task.risk = "specification", "high"
        self.task.approvals = {"requester": "ops-member"}
        context = stages.Context(approval_roles=("developer",))
        self.assertEqual(stages.advance(self.task, self.flow, context), ["impact_assessed", "risk_approvals"])
        self.task.impact = {key: "none" for key in stages.IMPACT_KEYS}
        self.task.impact["rollback"] = " "
        self.assertEqual(stages.advance(self.task, self.flow, context), ["impact_assessed", "risk_approvals"])
        self.task.impact["rollback"] = "Revert the commit. The change has no data."
        self.task.approvals["developer"] = "dev-lead"
        self.assertEqual(stages.advance(self.task, self.flow, context), [])

    def test_checks_and_scope(self):
        self.task.stage = "build"
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context(outside_scope=("db/schema.sql",))),
                         ["scope_respected"])
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), [])
        context = stages.Context(required_checks=("tests", "secrets"))
        self.task.checks = {"tests": "PASS", "secrets": "SKIP"}
        self.assertEqual(stages.advance(self.task, self.flow, context), ["checks_pass"])
        self.task.checks["secrets"] = "PASS"
        self.assertEqual(stages.advance(self.task, self.flow, context), [])

    def test_the_inspection_needs_the_product_map_and_the_server_rules(self):
        self.task.stage, self.task.conditions = "inspection", ["Filter by the transaction date"]
        self.task.accepted = {"Filter by the transaction date": True}
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), ["map_current", "infra_ready"])
        self.task.map_note = "The change adds no feature, screen, table, or API."
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context(infra_ready=True)), [])
        self.assertEqual(self.task.stage, "handover")

    def test_the_task_is_done_when_the_pull_request_merged(self):
        self.task.stage, self.task.pull_request = "handover", "https://example/pull/1"
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context()), ["merged"])
        self.assertEqual(stages.advance(self.task, self.flow, stages.Context(merged=True)), [])
        self.assertEqual(self.task.status, "done")
        self.assertEqual(stages.blockers(self.task, self.flow, stages.Context()), ["the task is done"])

    def test_three_failed_repairs_stop_the_task(self):
        self.assertFalse(stages.record_failure(self.task, "test_orders failed"))
        self.assertFalse(stages.record_failure(self.task, "test_orders failed"))
        self.assertTrue(stages.record_failure(self.task, "test_orders failed"))
        self.assertEqual(self.task.status, "stopped")
        self.assertIn("A developer must examine the problem", self.task.notes[-1])

    def test_task_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            task = Task(id=new_id("Add a date filter!"), title="Add a date filter", workflow="feature", stage="request")
            self.assertRegex(task.id, r"^add-a-date-filter-[0-9a-f]{4}$")
            save(root, task)
            self.assertEqual(load(root, task.id), task)
            self.assertEqual([item.id for item in all_tasks(root)], [task.id])
            with self.assertRaises(LookupError):
                load(root, "missing")
            (root / ".akasha" / "state" / "tasks" / "damaged.json").write_text("", encoding="utf-8")
            self.assertEqual([item.id for item in all_tasks(root)], [task.id])     # one damaged file stops nothing


if __name__ == "__main__":
    unittest.main()
