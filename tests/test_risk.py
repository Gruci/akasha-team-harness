import unittest

from akasha.config import Team
from akasha.core.handover import render
from akasha.core.risk import assess, matches
from akasha.core.task import Task

TEAM = Team(risk={"high": ("**/auth/**", "**/migrations/**"), "medium": ("**/api/**",)},
            contracts={"orders-api": ("api/orders/**",)})


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


class HandoverTests(unittest.TestCase):
    def test_all_sections_and_what_is_not_verified(self):
        task = Task(id="date-filter-0a1b", title="Add a date filter", workflow="feature", stage="handover",
                    requester="ops-member", conditions=["Filter by the transaction date", "Keep the other filters"],
                    accepted={"Filter by the transaction date": True}, risk="medium",
                    risk_reasons=["src/api/search.py matches **/api/**"], checks={"tests": "PASS", "lint": "SKIP"})
        text = render(task, ["src/api/search.py"])
        for heading in ("## Request", "## Completion conditions and inspection", "## Risk level: medium",
                        "## Checks", "## Changed files", "## Not verified", "## Remaining risks"):
            self.assertIn(heading, text)
        self.assertIn("- [x] Filter by the transaction date", text)
        self.assertIn("- lint", text.split("## Not verified")[1])
        self.assertIn("- Keep the other filters", text.split("## Not verified")[1])
        self.assertIn("<!-- akasha-task: date-filter-0a1b -->", text)


if __name__ == "__main__":
    unittest.main()
