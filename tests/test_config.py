import tempfile
import unittest
from pathlib import Path

from akasha import config
from akasha.config import ConfigError


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        team = config.parse("")
        self.assertEqual(team.required_checks, ("secrets",))
        self.assertEqual(team.status_checks, ("akasha",))
        self.assertEqual(team.server_rules, "github")
        self.assertEqual(team.work_dir, ".akasha/work")

    def test_a_full_team_config(self):
        team = config.parse("""
[team]
admins = ["@Admin-A"]
reviewers = ["rev-b"]
[risk]
paths = ["db/", "**/migrations/**"]
[checks]
required = ["secrets", "tests", "front"]
setup = "npm ci"
tests = "pytest -q"
[checks.front]
command = "npm run build"
cwd = "frontend"
only_when = ["frontend/"]
[ci]
required = ["checks"]
[guides]
preview = ["design/UX.md"]
[work]
folder = "worktrees"
branch_prefix = "feat/"
""")
        self.assertEqual(team.admins, ("admin-a",))
        self.assertEqual(team.risk_paths, ("db/**", "**/migrations/**"))
        self.assertEqual(team.checks["tests"].command, "pytest -q")
        self.assertEqual(team.checks["front"].only_when, ("frontend/**",))
        self.assertEqual(team.status_checks, ("checks",))
        self.assertEqual(team.guides["preview"], ("design/UX.md",))
        self.assertEqual((team.work_dir, team.branch_prefix), ("worktrees", "feat/"))

    def test_mistakes_are_refused(self):
        for text in ('[nope]\nx = 1', '[team]\nowners = []', '[checks]\nfoo = "x"', '[checks.secrets]\ncommand = "x"',
                     '[ci]\npython = "3.10"', '[work]\nfolder = ".akasha/state"', '[work]\nfolder = "../x"',
                     '[work]\nbranch_prefix = "a b/"', '[server]\nrules = "maybe"', '[checks.a]\ncwd = "x"'):
            with self.subTest(text=text), self.assertRaises(ConfigError):
                config.parse(text)

    def test_set_server_rules_keeps_the_other_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "akasha.toml").write_text('[team]\nadmins = ["a"]\n', encoding="utf-8")
            config.set_server_rules(root, "akasha")
            config.set_server_rules(root, "github")
            text = (root / "akasha.toml").read_text(encoding="utf-8")
            self.assertIn('admins = ["a"]', text)
            self.assertEqual(text.count("rules ="), 1)
            self.assertEqual(config.load(root).server_rules, "github")


if __name__ == "__main__":
    unittest.main()
