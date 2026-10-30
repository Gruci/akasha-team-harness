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
        self.assertEqual(team.approval, {"high": ("developer",)})
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
                     '[approval]\nhigh = ["boss"]\n', '[workflows]\nenabled = ["none"]\n', 'broken = [\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.load(self.repo(text))

    def test_team_workflow_replaces_the_built_in_one(self):
        root = self.repo()
        folder = root / config.TEAM_WORKFLOWS
        folder.mkdir(parents=True)
        (folder / "small.toml").write_text('name = "small"\n[[stages]]\nid = "build"\nexit = []\n', encoding="utf-8")
        self.assertEqual([stage.id for stage in config.load(root).workflows["small"].stages], ["build"])
        (folder / "bad.toml").write_text('name = "bad"\n[[stages]]\nid = "x"\nexit = ["magic"]\n', encoding="utf-8")
        with self.assertRaises(config.ConfigError):
            config.load(root)

    def test_each_exit_condition_has_a_test_function(self):
        self.assertEqual(set(stages.CONDITIONS), set(config.EXIT_CONDITIONS))
        self.assertEqual(set(stages.EXPLAIN), set(config.EXIT_CONDITIONS))


if __name__ == "__main__":
    unittest.main()
