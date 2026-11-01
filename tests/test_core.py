"""The core: which files other areas use, which changes of them wait for an administrator, and when an approval on
GitHub holds. Real git repositories; only the answer of GitHub is fake."""

import unittest
from unittest.mock import patch

from akasha import config, core
from tests.helpers import Repository, run

FMT = "def money(x):\n    return f'{x:,}'\n"


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        self.team = config.Team(admins=("admin-a",), own_procedure=("owner",))

    def tearDown(self):
        self.repo.close()

    def write(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def commit(self, files: dict[str, str] | None = None) -> str:
        self.write(files or {})
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "work")
        return run(self.root, "git", "rev-parse", "HEAD").strip()

    def users(self, path: str) -> set[str]:
        return core.Graph(self.root, "HEAD").users.get(path, set())

    def shared_fmt(self) -> None:
        self.commit({"lib/fmt.py": FMT, "a/x.py": "from lib import fmt\n", "b/y.py": "import lib.fmt\n"})

    def test_a_change_of_a_file_that_two_areas_import_is_core(self):
        self.shared_fmt()
        self.write({"lib/fmt.py": FMT.replace(":,", ":.2f")})
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {"lib/fmt.py": "used by 2 other areas"})
        self.assertEqual(core.planned(self.team, self.root, ["lib/**"]), {"lib/fmt.py": "used by 2 other areas"})
        self.assertEqual(core.planned(self.team, self.root, ["a/**"]), {})

    def test_a_new_line_in_a_core_file_is_free(self):
        self.shared_fmt()
        self.write({"lib/fmt.py": FMT + "\n\ndef percent(x):\n    return f'{x:.1%}'\n", "lib/new.py": "x = 1\n"})
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {})

    def test_a_file_of_one_area_is_free(self):
        self.commit({"a/inner.py": FMT, "a/x.py": "from a import inner\n", "a/z.py": "from .inner import money\n"})
        self.write({"a/inner.py": "def money(x):\n    return str(x)\n"})
        self.assertEqual(self.users("a/inner.py"), {"a/x.py", "a/z.py"})
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {})

    def test_imports_of_tests_do_not_count(self):
        self.commit({"lib/fmt.py": FMT, "a/x.py": "from lib.fmt import money\n",
                     "tests/test_fmt.py": "from lib import fmt\n", "b/fmt_test.py": "import lib.fmt\n",
                     "web/fmt.test.ts": "import { money } from '../lib/fmt'\n"})
        self.write({"lib/fmt.py": "def money(x):\n    return str(x)\n"})
        self.assertEqual(self.users("lib/fmt.py"), {"a/x.py"})
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {})

    def test_script_imports_resolve_relative_alias_and_index(self):
        self.commit({"src/utils/format.ts": "export const money = 1\n", "src/ui/index.ts": "export const B = 1\n",
                     "src/ui/App.tsx": "import './App.css'\n",
                     "src/pages/Home.tsx": "import { money } from '@/utils/format'\nimport { B } from '@/ui'\n"
                                           "import React from 'react'\nimport get from 'lodash/get'\n",
                     "src/pages/List.tsx": "import { money } from \"../utils/format.js\"\n",
                     "src/features/c/Card.jsx": "const ui = require('../../ui')\n"
                                                "export { money } from 'src/utils/format'\n"})
        self.assertEqual(self.users("src/utils/format.ts"),
                         {"src/pages/Home.tsx", "src/pages/List.tsx", "src/features/c/Card.jsx"})
        self.assertEqual(self.users("src/ui/index.ts"), {"src/pages/Home.tsx", "src/features/c/Card.jsx"})
        self.assertEqual(self.users("src/ui/App.tsx"), set())

    def test_a_scoped_package_is_no_file_of_the_repository(self):
        self.commit({"src/lib/common.ts": "export const c = 1\n", "src/app/x.ts": "export const x = 1\n",
                     "src/a/A.ts": "import { Injectable } from '@nestjs/common'\nimport { x } from '@app/app/x'\n",
                     "src/b/B.ts": "import { Injectable } from \"@nestjs/common\"\n"})
        self.assertEqual(self.users("src/lib/common.ts"), set())
        self.assertEqual(self.users("src/app/x.ts"), {"src/a/A.ts"})

    def test_python_modules_of_a_src_or_backend_folder_resolve(self):
        self.commit({"src/mypkg/__init__.py": "", "backend/config.py": "X = 1\n",
                     "src/a/x.py": "import mypkg\n", "src/b/y.py": "from mypkg import helper\n",
                     "backend/api/v.py": "from config import X\n", "backend/jobs/w.py": "import config\n"})
        self.assertEqual(self.users("src/mypkg/__init__.py"), {"src/a/x.py", "src/b/y.py"})
        self.assertEqual(self.users("backend/config.py"), {"backend/api/v.py", "backend/jobs/w.py"})

    def test_python_relative_and_from_imports_resolve(self):
        self.commit({"lib/__init__.py": "", "lib/fmt.py": FMT, "lib/other.py": "from . import fmt\n",
                     "lib/deep/z.py": "from ..fmt import money\n",
                     "a/x.py": "from lib import (\n    fmt,  # money\n)\n",
                     "b/y.py": "import os, lib.fmt as f; print(f)\n", "c/w.py": "from lib import nothing\n"})
        self.assertEqual(self.users("lib/fmt.py"), {"lib/other.py", "lib/deep/z.py", "a/x.py", "b/y.py"})
        self.assertEqual(self.users("lib/__init__.py"), {"c/w.py"})

    def test_areas_split_the_folders_of_one_project(self):
        self.commit({"src/shared/x.ts": "export const x = 1\n",
                     "src/features/a/A.tsx": "import { x } from '../../shared/x'\n",
                     "src/features/b/B.tsx": "import { x } from '@/shared/x'\n"})
        self.write({"src/shared/x.ts": "export const x = 2\n"})
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {})
        team = config.parse('[core]\nareas = ["src/features/*"]\n')
        self.assertEqual(core.area("src/features/a/A.tsx", team), "src/features/a")
        self.assertEqual(core.area("src/shared/x.ts", team), "src/shared")
        self.assertEqual(core.area("app.py", team), "app.py")
        self.assertEqual(core.changed(team, self.root, "HEAD"), {"src/shared/x.ts": "used by 2 other areas"})

    def test_a_path_of_core_is_core_only_for_changed_lines(self):
        team = config.parse('[core]\npaths = ["db/"]\n')
        self.write({"db/schema.sql": "create table a (x int);\ncreate table b (y int);\n"})
        self.assertEqual(core.changed(team, self.root, "HEAD"), {})
        self.write({"db/schema.sql": "create table a (x bigint);\n"})
        self.assertEqual(core.changed(team, self.root, "HEAD"), {"db/schema.sql": "a path of [core]"})
        self.assertEqual(core.planned(team, self.root, ["db/**"]), {"db/schema.sql": "a path of [core]"})

    def test_a_deleted_core_file_is_core(self):
        self.shared_fmt()
        (self.root / "lib" / "fmt.py").unlink()
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {"lib/fmt.py": "used by 2 other areas"})
        run(self.root, "git", "rm", "-q", "--cached", "lib/fmt.py")
        self.assertEqual(core.changed(self.team, self.root, "HEAD"), {"lib/fmt.py": "used by 2 other areas"})

    def test_the_exempt_people(self):
        self.assertTrue(core.exempt(self.team, "admin-a"))
        self.assertTrue(core.exempt(self.team, "owner"))
        self.assertFalse(core.exempt(self.team, "mate"))
        self.assertFalse(core.exempt(self.team, ""))

    def test_the_request_names_the_files_and_the_task(self):
        text = core.request("money-format", {"lib/fmt.py": "used by 2 other areas"})
        self.assertIn("- `lib/fmt.py`: used by 2 other areas", text)
        self.assertIn("`money-format`", text)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.repo = Repository()
        self.root = self.repo.root
        self.team = config.Team(admins=("admin-a", "admin-b"))
        (self.root / "lib").mkdir()
        self.approved = self.commit("lib/fmt.py", FMT)

    def tearDown(self):
        self.repo.close()

    def commit(self, name: str, text: str) -> str:
        (self.root / name).write_text(text, encoding="utf-8")
        run(self.root, "git", "add", "-A")
        run(self.root, "git", "commit", "-q", "-m", "work")
        return run(self.root, "git", "rev-parse", "HEAD").strip()

    def approver(self, *reviews: tuple[str, str, str]) -> str:
        nodes = [{"state": state, "author": {"login": login}, "commit": {"oid": oid}} for login, state, oid in reviews]
        answer = {"data": {"repository": {"pullRequest": {"reviews": {"nodes": nodes}}}}}
        with patch("akasha.core.gh_json", return_value=answer) as asked:
            who = core.approver(self.root, self.root, 7, self.team, ["lib/fmt.py"])
        self.assertIn("number=7", asked.call_args.args)
        return who

    def test_an_approval_holds_until_the_core_files_change(self):
        self.assertEqual(self.approver(("Admin-A", "APPROVED", self.approved)), "admin-a")
        self.commit("other.py", "x = 1\n")
        self.assertEqual(self.approver(("Admin-A", "APPROVED", self.approved)), "admin-a")
        self.commit("lib/fmt.py", FMT + "# later\n")
        self.assertEqual(self.approver(("Admin-A", "APPROVED", self.approved)), "")
        self.assertEqual(self.approver(("admin-a", "APPROVED", "0" * 40)), "")

    def test_a_later_request_for_changes_takes_the_approval_back(self):
        approved = ("admin-a", "APPROVED", self.approved)
        self.assertEqual(self.approver(approved, ("admin-a", "CHANGES_REQUESTED", self.approved)), "")
        self.assertEqual(self.approver(approved, ("admin-a", "DISMISSED", self.approved)), "")
        self.assertEqual(self.approver(approved, ("admin-a", "COMMENTED", self.approved)), "admin-a")
        self.assertEqual(self.approver(("admin-a", "CHANGES_REQUESTED", self.approved), approved), "admin-a")
        self.assertEqual(self.approver(approved, ("admin-b", "CHANGES_REQUESTED", self.approved)), "admin-a")

    def test_an_approval_of_a_teammate_does_not_count(self):
        self.assertEqual(self.approver(("mate", "APPROVED", self.approved)), "")

    def test_no_answer_of_github_is_no_approval(self):
        with patch("akasha.core.gh_json", return_value=None):
            self.assertEqual(core.approver(self.root, self.root, 7, self.team, ["lib/fmt.py"]), "")


if __name__ == "__main__":
    unittest.main()
