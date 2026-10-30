import unittest

from akasha.config import Team
from akasha.core.handover import commit_body, pull_request_body
from akasha.core.risk import assess, matches
from akasha.core.task import Task, new_id
from akasha.validators.briefing import examine

TEAM = Team(risk={"high": ("**/auth/**", "**/migrations/**"), "medium": ("**/api/**",)},
            contracts={"orders-api": ("api/orders/**",)})

BRIEFING = """## Why

Operations people cannot find customers by date. The search now has a date filter.

## What changed

- The customer search takes a start date and an end date.

## Scope

- Covers the transaction date only.
- Leaves out the sign-up date, which is a follow-up.

## Blast Radius

The change touches only the customer search query. The query keeps its index, so the speed stays the same.
"""


class RiskTests(unittest.TestCase):
    def test_patterns_also_match_the_top_of_the_repository(self):
        self.assertTrue(matches("auth/login.py", "**/auth/**"))
        self.assertTrue(matches("src/auth/login.py", "**/auth/**"))
        self.assertFalse(matches("src/author.py", "**/auth/**"))

    def test_levels(self):
        self.assertEqual(assess(["README.md"], TEAM).level, "low")
        self.assertEqual(assess(["src/api/search.py"], TEAM).level, "medium")
        high = assess(["src/api/search.py", "db/migrations/0002.sql"], TEAM)
        self.assertEqual(high.level, "high")
        self.assertIn("db/migrations/0002.sql matches **/migrations/**", high.reasons)

    def test_a_public_contract_raises_low_to_medium(self):
        result = assess(["api/orders/schema.json"], Team(contracts=TEAM.contracts))
        self.assertEqual((result.level, result.contracts), ("medium", ("orders-api",)))


class BriefingTests(unittest.TestCase):
    def test_a_correct_briefing(self):
        self.assertEqual(examine(BRIEFING), [])

    def test_the_rules(self):
        cases = {
            "## Verification": BRIEFING + "\n## Verification\n\n- It works.\n",
            "add the section ## Scope": BRIEFING.replace("## Scope", "## Notes"),
            "in this order": BRIEFING.replace("## Why", "## Blast Radius", 1),
            "bold lead-ins": BRIEFING.replace("- The customer", "- **Search:** the customer"),
            "no text before": "Based on the request.\n\n" + BRIEFING,
            "commit hash": BRIEFING.replace("date filter.", "date filter from 3f2a9c1."),
            "branch history": BRIEFING.replace("date filter.", "date filter, based on main."),
            "25 words or fewer": BRIEFING.replace("a date filter.", "a date filter " + "and more " * 12 + "."),
            "needs 1 to 2 sentences": BRIEFING.replace("stays the same.", "stays the same. One. Two."),
            "lines or fewer": BRIEFING.replace("## Scope", "\n" * 30 + "## Scope"),
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in problem for problem in examine(text)), examine(text))

    def test_a_task_name_is_not_a_commit_hash(self):
        names = ["add-a-date-filter-1f3a9c0b", "task-0b7c2e91"] + [new_id("Add a date filter") for _ in range(200)]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(examine(BRIEFING.replace("date filter.", f"date filter of {name}.")), [])
        self.assertIn("remove the commit hash — the reader has the diff",
                      examine(BRIEFING.replace("date filter.", "date filter of task-0b7c2e91 from 3f2a9c1.")))


class HandoverTests(unittest.TestCase):
    def test_verification_comes_from_the_real_results(self):
        task = Task(id="date-filter-0a1b", title="Add a date filter", workflow="feature", stage="handover",
                    conditions=["Filter by the transaction date", "Keep the other filters"],
                    accepted={"Filter by the transaction date": True, "Keep the other filters": True},
                    checks={"secrets": "PASS", "tests": "PASS"}, briefing=BRIEFING.strip(),
                    board="https://github.com/team/app/issues/12")
        body = commit_body(task, "main", {"tests": "npm test --silent"})
        self.assertTrue(body.startswith("## Why"))
        self.assertIn("passed on the latest main: secrets, tests (`npm test --silent`).", body)
        self.assertIn("accepted 2 of 2 completion conditions", body)
        self.assertLessEqual(len(body.splitlines()), 40)
        text = pull_request_body(task, "main", {})
        self.assertIn("Closes #12", text)
        self.assertIn("<!-- akasha-task: date-filter-0a1b -->", text)
        task.accepted = {}
        self.assertIn("no inspection by the requester", commit_body(task, "main", {}))


if __name__ == "__main__":
    unittest.main()
