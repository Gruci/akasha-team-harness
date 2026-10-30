import subprocess
import tempfile
import unittest
from pathlib import Path

from akasha import config
from akasha.core import stages


class ConfigTests(unittest.TestCase):
    def repo(self, text: str | None = None) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        if text is not None:
            (root / config.CONFIG_FILE).write_text(text, encoding="utf-8")
        return root

    def test_defaults_without_a_config_file(self):
        team = config.load(self.repo())
        self.assertEqual(set(team.workflows), {"feature", "fix", "small"})
        self.assertEqual(team.approval, {})                 # the agent engine decides; a person gate is a choice
        self.assertEqual(team.required_checks, ("secrets",))

    def test_full_config(self):
        team = config.load(self.repo(
            '[roles]\ndevelopers = ["@lead"]\n[risk]\nhigh = ["**/auth/**"]\n[checks]\nrequired = ["tests"]\n'
            'tests = "python -m pytest -q"\n[contracts]\norders = ["api/orders/**"]\n'
            '[workflows]\nenabled = ["feature"]\n'))
        self.assertEqual(team.developers, ("@lead",))
        self.assertEqual(team.commands, {"tests": "python -m pytest -q"})
        self.assertEqual(list(team.workflows), ["feature"])
        self.assertEqual(team.contracts["orders"], ("api/orders/**",))

    def test_incorrect_shapes_are_refused(self):
        for text in ('[colors]\nx = 1\n', '[roles]\nowners = []\n', '[risk]\nhigh = "auth"\n',
                     '[approval]\nhigh = ["boss"]\n', '[workflows]\nenabled = ["none"]\n', 'broken = [\n',
                     '[server]\nrules = "someone"\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.load(self.repo(text))

    def test_the_setup_records_who_enforces_the_server_rules(self):
        root = self.repo('[roles]\nadministrators = ["admin"]\n')
        self.assertEqual(config.load(root).server_rules, "github")
        config.set_server_rules(root, "akasha")
        self.assertEqual(config.load(root).server_rules, "akasha")
        config.set_server_rules(root, "github")
        text = (root / config.CONFIG_FILE).read_text(encoding="utf-8")
        self.assertEqual((text.count("[server]"), text.count("rules =")), (1, 1))
        self.assertEqual(config.load(root).administrators, ("admin",))

    def test_team_workflow_replaces_the_built_in_one(self):
        root = self.repo()
        folder = root / config.TEAM_WORKFLOWS
        folder.mkdir(parents=True)
        (folder / "small.toml").write_text('name = "small"\n[[stages]]\nid = "build"\nexit = []\n', encoding="utf-8")
        self.assertEqual([stage.id for stage in config.load(root).workflows["small"].stages], ["build"])
        (folder / "bad.toml").write_text('name = "bad"\n[[stages]]\nid = "x"\nexit = ["magic"]\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(root)

    def test_the_rules_on_the_server_come_from_a_git_ref(self):
        root = self.repo('[roles]\ndevelopers = ["lead-a"]\n[workflows]\nenabled = ["small", "fix"]\n')
        for args in (("init", "-q"), ("config", "user.email", "test@example.com"), ("config", "user.name", "Test")):
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "first"], cwd=root, check=True)
        first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
        folder = root / config.TEAM_WORKFLOWS
        folder.mkdir(parents=True)
        (folder / "small.toml").write_text('name = "small"\n[[stages]]\nid = "build"\nexit = []\n', encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "rules"], cwd=root, check=True)
        (root / config.CONFIG_FILE).write_text('[roles]\ndevelopers = ["lead-b"]\n', encoding="utf-8")   # not merged
        (folder / "small.toml").unlink()
        server = config.shared(root, "HEAD")
        self.assertEqual((server.developers, list(server.workflows)), (("lead-a",), ["small", "fix"]))
        self.assertEqual([stage.id for stage in server.workflows["small"].stages], ["build"])
        for local in (config.load(root), config.shared(root, ""), config.shared(root, first)):    # first: no file
            self.assertEqual((local.developers, len(local.workflows["small"].stages)), (("lead-b",), 3))
        self.assertTrue(config.on_server(root, "HEAD"))
        self.assertFalse(config.on_server(root, first))
        (root / config.CONFIG_FILE).write_text('[colors]\nx = 1\n', encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "broken"], cwd=root, check=True)
        with self.assertRaises(config.ConfigError) as refused:
            config.shared(root, "HEAD")
        self.assertIn("the team config on HEAD", str(refused.exception))

    def test_each_exit_condition_has_a_test_function(self):
        self.assertEqual(set(stages.CONDITIONS), set(config.EXIT_CONDITIONS))
        self.assertEqual(set(stages.EXPLAIN), set(config.EXIT_CONDITIONS))


if __name__ == "__main__":
    unittest.main()
