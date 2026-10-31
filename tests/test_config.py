import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from akasha import config
from akasha.core import stages
from akasha.validators import runner


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
        self.assertEqual(team.checks, {"tests": config.Check("python -m pytest -q")})     # the format of 1.0.0
        self.assertEqual((team.setup, team.run_all_when), ("", config.RUN_ALL_WHEN))
        self.assertEqual(list(team.workflows), ["feature"])
        self.assertEqual(set(team.defined), {"feature", "fix", "small"})      # for the tasks that started before
        self.assertEqual(team.contracts["orders"], ("api/orders/**",))

    def test_incorrect_shapes_are_refused(self):
        for text in ('[colors]\nx = 1\n', '[roles]\nowners = []\n', '[risk]\nhigh = "auth"\n',
                     '[approval]\nhigh = ["boss"]\n', '[workflows]\nenabled = ["none"]\n', 'broken = [\n',
                     '[server]\nrules = "someone"\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.load(self.repo(text))

    def test_named_checks(self):
        team = config.load(self.repo(
            '[checks]\nrequired = ["secrets", "static", "pytest", "front", "lint"]\n'
            'setup = "pip install -r requirements.txt"\nlint = "ruff check ."\nrun_all_when = ["requirements*.txt"]\n'
            '[checks.static]\ncommand = "python -X utf8 static_check.py"\n'
            '[checks.pytest]\ncommand = "python -m pytest -q"\nonly_when = ["**/*.py", "tests/**"]\n'
            "[checks.front]\ncommand = \"npm ci && npm run build\"\ncwd = './frontend\\app'\n"
            'only_when = ["frontend/**"]\ncommand_windows = "npm ci & npm run build"\n'))
        self.assertEqual(team.required_checks, ("secrets", "static", "pytest", "front", "lint"))
        self.assertEqual((team.setup, team.run_all_when), ("pip install -r requirements.txt", ("requirements*.txt",)))
        self.assertEqual(team.checks, {
            "lint": config.Check("ruff check ."),
            "static": config.Check("python -X utf8 static_check.py"),
            "pytest": config.Check("python -m pytest -q", only_when=("**/*.py", "tests/**")),
            "front": config.Check("npm ci && npm run build", cwd="frontend/app", only_when=("frontend/**",),
                                  command_windows="npm ci & npm run build"),
        })
        top = config.load(self.repo('[checks.static]\ncommand = "x"\ncwd = "."\n[checks]\nrun_all_when = []\n'))
        self.assertEqual((top.checks["static"].cwd, top.run_all_when), ("", ()))

    def test_the_file_patterns_of_the_checks_get_the_form_of_git_paths(self):
        # A pattern that matches no changed file turns a required check off: NOT_NEEDED is a pass.
        team = config.load(self.repo(
            "[checks]\nrequired = ['front']\nrun_all_when = ['.\\requirements.txt', './']\n"
            "[checks.front]\ncommand = 'x'\ncwd = 'frontend'\n"
            "only_when = ['./frontend/**', 'frontend\\src\\**', 'docs/', '**/*.ts']\n"))
        self.assertEqual(team.checks["front"].only_when, ("frontend/**", "frontend/src/**", "docs/**", "**/*.ts"))
        self.assertEqual(team.run_all_when, ("requirements.txt", "**"))
        for pattern in ("./frontend/**", "frontend\\src\\**", "frontend/"):
            with self.subTest(pattern=pattern):
                check = config.load(self.repo(f"[checks.front]\ncommand = 'x'\nonly_when = ['{pattern}']\n"))
                self.assertTrue(runner.needed(check.checks["front"], ["frontend/src/app.js"], ()))

    def test_the_formats_of_1_0_0_still_load(self):
        empty = config.load(self.repo('[checks]\nrequired = []\n'))     # no check is not a pass, so the default
        self.assertEqual((empty.required_checks, empty.checks), (("secrets",), {}))
        command = f"'\"{sys.executable}\" -c \"print(1)\"'"
        root = self.repo(f'[checks]\nrequired = ["secrets", "setup"]\nsetup = {command}\n')
        setup = config.load(root)
        self.assertEqual(setup.checks["setup"], config.Check(setup.setup))     # 1.0.0 ran it as a check
        self.assertEqual(runner.run(setup, root, []).status, {"secrets": "PASS", "setup": "PASS"})
        self.assertEqual(config.load(self.repo(f"[checks]\nsetup = {command}\n")).checks, {})

    def test_incorrect_checks_are_refused(self):
        for text in ('[checks.secrets]\ncommand = "x"\n', '[checks.setup]\ncommand = "x"\n',
                     '[checks.required]\ncommand = "x"\n', '[checks.run_all_when]\ncommand = "x"\n',
                     '[checks]\nsecrets = "x"\n', '[checks]\nstatic = "python static_check.py"\n',
                     '[checks]\ntests = ""\n', '[checks]\nlint = 1\n', '[checks]\nrequired = [""]\n',
                     '[checks]\nrun_all_when = "akasha.toml"\n', '[checks."my check"]\ncommand = "x"\n',
                     '[checks.static]\ncwd = "src"\n', '[checks.static]\ncommand = "x"\nshell = "bash"\n',
                     '[checks.static]\ncommand = "x"\ncwd = "../other"\n',
                     '[checks.static]\ncommand = "x"\ncwd = "/srv"\n', '[checks.static]\ncommand = "x"\ncwd = "C:/app"\n',
                     '[checks.static]\ncommand = "x"\nonly_when = []\n',
                     '[checks.static]\ncommand = "x"\nonly_when = "src/**"\n',
                     '[checks.static]\ncommand = "x"\ncommand_windows = ""\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.load(self.repo(text))
        with self.assertRaises(config.ConfigError) as refused:
            config.load(self.repo('[checks.secrets]\ncommand = "x"\n'))
        self.assertIn("secrets cannot be the name of a check", str(refused.exception))

    def test_the_map_folder_is_a_folder_in_the_repository(self):
        self.assertEqual(config.load(self.repo()).map_dir, ".akasha/context/map")
        for text in ('[context]\nmap = "docs/features/"\n', "[context]\nmap = 'docs\\features'\n",
                     '[context]\nmap = "./docs/features"\n'):
            with self.subTest(text=text):
                self.assertEqual(config.load(self.repo(text)).map_dir, "docs/features")
        self.assertEqual(config.load(self.repo('[context]\nmap = "docs/console-map"\n')).map_dir, "docs/console-map")
        for value in ('"/docs/features"', '"C:/docs"', '"c:docs"', '"../features"', '"docs/../../features"', '"."',
                      '""', '" "', "1", '"docs/aux"', '"CON/map"', '"docs/nul.d"', '"lpt1"'):    # also Windows names
            with self.subTest(value=value), self.assertRaises(config.ConfigError):
                config.load(self.repo(f"[context]\nmap = {value}\n"))
        with self.assertRaises(config.ConfigError):
            config.load(self.repo('[context]\nfolder = "docs"\n'))

    def test_the_work_folder_and_the_branch_prefixes(self):
        team = config.load(self.repo())
        self.assertEqual((team.work_dir, team.branch_prefix, team.wip_prefix),
                         (".akasha/work", "akasha/", "akasha-wip/"))
        own = config.load(self.repo("[work]\nfolder = 'tools\\worktrees\\'\nbranch_prefix = \"feat/\"\n"
                                    'wip_prefix = "wip/feat-"\n'))
        self.assertEqual((own.work_dir, own.branch_prefix, own.wip_prefix), ("tools/worktrees", "feat/", "wip/feat-"))
        for value in ('"/srv/work"', '"C:/work"', '"../work"', '"tools/../../work"', '"."', '""', '"aux"', 1,
                      '".git/work"', '".GIT"', '".akasha"', '".akasha/state/work"', '".akasha/context/work"',
                      '".akasha/workflows/work"', '".akasha/Context"'):      # the folders of git and of Akasha
            with self.subTest(folder=value), self.assertRaises(config.ConfigError):
                config.load(self.repo(f"[work]\nfolder = {value}\n"))
        with self.assertRaises(config.ConfigError) as refused:            # the map folder of the team
            config.load(self.repo('[context]\nmap = "docs/map"\n[work]\nfolder = "docs"\n'))
        self.assertIn("[work] folder docs cannot be docs/map, in it, or around it", str(refused.exception))
        for value in ('""', '" "', "1", '"feat /"', '"feat~"', '"feat^"', '"feat:"', '"a..b/"', '"-feat/"', '"/feat"',
                      '"feat//"', '".feat/"', '"feat.lock/"', '"feat@{"', '"fe*at/"', '"feat?"', '"feat["',
                      '"feat\\\\"', '"feat\\t"'):
            with self.subTest(prefix=value), self.assertRaises(config.ConfigError):
                config.load(self.repo(f"[work]\nbranch_prefix = {value}\n"))
        for branch, wip in (("x/", "x/"), ("akasha/", "akasha/wip/"), ("Feat/", "feat/"), ("wip/", "wip/old-"),
                            ("akasha-wip/", "wip/"), ("Akasha-", "wip/"), ("feat/", "Akasha/"),
                            ("feat/", "akasha/wip/")):         # the default prefixes of the older tasks count too
            with self.subTest(branch=branch, wip=wip), self.assertRaises(config.ConfigError) as refused:
                config.load(self.repo(f'[work]\nbranch_prefix = "{branch}"\nwip_prefix = "{wip}"\n'))
            self.assertIn("one cannot start with the other", str(refused.exception))
        with self.assertRaises(config.ConfigError) as refused:
            config.load(self.repo('[work]\nbranch_prefix = "akasha-wip/"\nwip_prefix = "wip/"\n'))
        self.assertIn("branch_prefix akasha-wip/ and the default wip_prefix akasha-wip/", str(refused.exception))
        with self.assertRaises(config.ConfigError):
            config.load(self.repo('[work]\nprefix = "feat/"\n'))

    def test_the_machine_and_the_python_of_the_server_check(self):
        team = config.load(self.repo())
        self.assertEqual((team.runs_on, team.python), (("ubuntu-latest",), "3.12"))
        one = config.load(self.repo('[ci]\nruns-on = " windows-latest "\npython = "3.11"\n'))
        self.assertEqual((one.runs_on, one.python), (("windows-latest",), "3.11"))
        own = config.load(self.repo('[ci]\nruns-on = ["self-hosted", "windows", "x64"]\npython = "3.13.1"\n'))
        self.assertEqual((own.runs_on, own.python), (("self-hosted", "windows", "x64"), "3.13.1"))
        for text in ('[ci]\npython = "3.10"\n', '[ci]\npython = "3.9"\n', '[ci]\npython = 3.12\n',
                     '[ci]\npython = "3.x"\n', '[ci]\npython = "latest"\n', '[ci]\nruns-on = ""\n',
                     '[ci]\nruns-on = []\n', '[ci]\nruns-on = ["linux", ""]\n', '[ci]\nruns-on = 1\n',
                     '[ci]\nruns-on = "linux # x"\n', '[ci]\nruns-on = ["linux\\nsteps: []"]\n',
                     '[ci]\nmachine = "linux"\n'):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.load(self.repo(text))
        with self.assertRaises(config.ConfigError) as refused:
            config.load(self.repo('[ci]\npython = "3.10"\n'))
        self.assertIn("3.11 or higher", str(refused.exception))

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
