import unittest

from akasha.coordinator import board, overlap, resources
from akasha.core.task import Task


def task(task_id: str, **values) -> Task:
    return Task(id=task_id, title=task_id, workflow="feature", stage="request", **values)


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
        self.assertIn("the earlier task merges first", found[0].message())

    def test_a_task_does_not_overlap_itself(self):
        mine = task("a", feature="x", scope=["src/**"])
        self.assertEqual(overlap.find(mine, [mine]), [])


class BoardTests(unittest.TestCase):
    def test_the_scope_block_goes_and_comes_back(self):
        mine = task("date-filter-0a1b", feature="customer-search-filter", scope=["src/search/**"], risk="medium")
        parsed = board.parse(board.body(mine))
        self.assertEqual((parsed.id, parsed.feature, parsed.scope, parsed.risk),
                         ("date-filter-0a1b", "customer-search-filter", ["src/search/**"], "medium"))
        self.assertIsNone(board.parse("an issue without a block"))
        self.assertIsNone(board.parse("```akasha-scope\nnot json\n```"))


class ResourceTests(unittest.TestCase):
    def test_each_task_gets_its_own_names(self):
        first, second = resources.port("date-filter-0a1b"), resources.port("invoice-pdf-9f3c")
        self.assertEqual(first, resources.port("date-filter-0a1b"))
        self.assertTrue(resources.PORT_FIRST <= first < resources.PORT_FIRST + resources.PORT_COUNT)
        self.assertNotEqual(first, second)
        self.assertEqual(resources.fill("app_{task}", "date-filter-0a1b"), "app_date_filter_0a1b")
        self.assertEqual(resources.fill("--port {port}", "date-filter-0a1b"), f"--port {first}")


if __name__ == "__main__":
    unittest.main()
