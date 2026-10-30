import unittest

from akasha.config import Team
from akasha.infra import desired


class InfraTests(unittest.TestCase):
    def test_codeowners_follow_the_gates_and_keep_the_rules_with_the_administrators(self):
        team = Team(developers=("@lead",), administrators=("@admin",),
                    risk={"high": ("**/auth/**",), "medium": ("**/api/**",)},
                    approval={"high": ("developer",), "medium": ("developer", "administrator")})
        lines = desired.codeowners(team).splitlines()
        self.assertEqual((lines[0], lines[-1]), (desired.START, desired.END))
        self.assertIn("**/auth/** @lead", lines)
        self.assertIn("**/api/** @admin @lead", lines)
        self.assertIn("/akasha.toml @admin", lines)
        self.assertIn("/.akasha/workflows/ @admin", lines)
        self.assertFalse(any(line.startswith("/.akasha/context") or line == "/.akasha/ @admin" for line in lines))
        plain = Team(developers=("lead",), risk={"high": ("**/auth/**",)}, approval={"high": ("developer",)})
        self.assertIn("**/auth/** @lead", desired.codeowners(plain).splitlines())
        no_gate = Team(developers=("lead",), risk={"high": ("**/auth/**",)})
        self.assertNotIn("**/auth/** @lead", desired.codeowners(no_gate).splitlines())

    def test_the_block_keeps_the_lines_of_the_team(self):
        block = desired.codeowners(Team(administrators=("admin",)))
        merged = desired.merge("* @team-leads\n", block)
        self.assertTrue(merged.startswith("* @team-leads\n"))
        self.assertTrue(merged.endswith(block))                         # the last matching line wins
        self.assertEqual(desired.block(merged), block)
        again = desired.merge(merged, desired.codeowners(Team(administrators=("other",))))
        self.assertEqual(again.count(desired.START), 1)
        self.assertIn("* @team-leads", again)

    def test_protection_and_settings(self):
        wanted = desired.protection()
        self.assertEqual(wanted["required_status_checks"], {"strict": True, "contexts": ["akasha"]})
        self.assertEqual(wanted["required_pull_request_reviews"],
                         {"required_approving_review_count": 0, "require_code_owner_reviews": True})
        self.assertIn("Take the team config from the default branch", desired.workflow())
        self.assertIn("refs/heads/", desired.workflow())
        self.assertEqual(desired.settings_drift({"allow_auto_merge": False, "allow_squash_merge": True}),
                         ["the repository setting allow_auto_merge is off"])
        self.assertEqual(desired.settings_drift({}), [])                # hidden settings are not problems

    def test_drift(self):
        self.assertEqual(desired.drift(None), ["the default branch has no branch protection"])
        correct = {"required_status_checks": {"strict": True, "contexts": ["akasha"]},
                   "required_pull_request_reviews": {"required_approving_review_count": 0,
                                                     "require_code_owner_reviews": True},
                   "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
        self.assertEqual(desired.drift(correct), [])
        weak = {"required_status_checks": {"strict": False, "checks": [{"context": "lint"}]},
                "allow_force_pushes": {"enabled": True}}
        problems = desired.drift(weak)
        self.assertIn("the check akasha is not required", problems)
        self.assertIn("force pushes are permitted", problems)
        self.assertIn("code owners do not have to approve", problems)
        partial = {"required_status_checks": {"contexts": ["akasha"]}, "partial": True}
        self.assertEqual(desired.drift(partial), [])                     # a person without administrator rights


if __name__ == "__main__":
    unittest.main()
