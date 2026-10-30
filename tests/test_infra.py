import unittest

from akasha.config import Team
from akasha.infra import desired


class InfraTests(unittest.TestCase):
    def test_codeowners_follow_the_risk_and_approval_rules(self):
        team = Team(developers=("@lead",), administrators=("@admin",),
                    risk={"high": ("**/auth/**",), "medium": ("**/api/**",)},
                    approval={"high": ("developer",), "medium": ("developer", "administrator")})
        lines = desired.codeowners(team).splitlines()
        self.assertIn("**/auth/** @lead", lines)
        self.assertIn("**/api/** @admin @lead", lines)
        self.assertIn("/akasha.toml @admin", lines)
        self.assertIn("/.github/ @admin", lines)

    def test_files_and_protection(self):
        files = desired.files(Team())
        self.assertEqual(set(files), {".github/workflows/akasha.yml", ".github/pull_request_template.md",
                                      ".github/CODEOWNERS"})
        self.assertIn("Take the team config from the default branch", files[".github/workflows/akasha.yml"])
        wanted = desired.protection()
        self.assertEqual(wanted["required_status_checks"], {"strict": True, "contexts": ["akasha"]})
        self.assertTrue(wanted["required_pull_request_reviews"]["require_code_owner_reviews"])

    def test_drift(self):
        self.assertEqual(desired.drift(None), ["the default branch has no branch protection"])
        correct = {"required_status_checks": {"strict": True, "contexts": ["akasha"]},
                   "required_pull_request_reviews": {"required_approving_review_count": 1,
                                                     "require_code_owner_reviews": True},
                   "allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
        self.assertEqual(desired.drift(correct), [])
        weak = {"required_status_checks": {"strict": False, "checks": [{"context": "lint"}]},
                "allow_force_pushes": {"enabled": True}}
        problems = desired.drift(weak)
        self.assertIn("the check akasha is not required", problems)
        self.assertIn("force pushes are permitted", problems)
        self.assertIn("code owners do not have to approve", problems)


if __name__ == "__main__":
    unittest.main()
