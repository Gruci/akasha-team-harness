"""The core of a repository: the files that other areas of the code use, and the files of [core] paths.

A teammate's task adds code freely. A change of existing lines of a core file waits for the approval of an
administrator on GitHub, because other screens use that code and nobody of them saw the change. Akasha finds the
users in the imports of Python, JavaScript, and TypeScript, and of Java, Kotlin, and Go (an import names a class or
a package there: Akasha follows it to a file of that package). In other languages only [core] paths count."""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from akasha.checks import matches
from akasha.config import Team
from akasha.repo import git, gh_json, names, origin, paths, paths_at

PY = (".py",)
JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
OTHER = (".java", ".kt", ".kts", ".go")       # an import names a class or a package, not a file
READ = PY + JS + OTHER                        # the languages whose names and imports Akasha reads
DOTTED_IMPORT = re.compile(r"^[ \t]*import[ \t]+(?:static[ \t]+)?([A-Za-z_][\w.]*)", re.M)     # Java, Kotlin
GO_BLOCK = re.compile(r"^import[ \t]*\((.*?)\)", re.M | re.S)
GO_LINE = re.compile(r'^import[ \t]+(?:[\w.]+[ \t]+)?"([^"\n]+)"', re.M)
QUOTED = re.compile(r'"([^"\n]+)"')
PY_FROM = re.compile(r"^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]*)", re.M)
PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([^\n]+)", re.M)
JS_IMPORT = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"]([^'"\n]+)['"]""")
TEST = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*$|_test\.(py|go)$|\.(test|spec)\.[cm]?[jt]sx?$")
COMMENT = re.compile(r"#[^\n]*")
BIGGEST = 1_000_000            # bytes: a larger file is data, not code
REVIEWS = ("query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest("
           "number:$number){reviews(last:100){nodes{state author{login} commit{oid}}}}}}")


def _key(path: str) -> str:
    """The name that an import uses for the file: the path without the extension of code, and the folder for an
    index. Other extensions stay, so that "./App.css" is not the file App.tsx."""
    stem, extension = posixpath.splitext(path)
    stem = stem if extension in READ else path
    return posixpath.dirname(stem) if posixpath.basename(stem) in ("__init__", "index") else stem


def _texts(tree: Path, paths: list[str]) -> dict[str, str]:
    """The text of each file, without the files larger than BIGGEST. Git gives the files that the work copy did not
    change in one process: on Windows a virus scanner makes each opening of a new file slow."""
    edited = set(names(tree, "diff", "--name-only", "--no-renames", "HEAD"))
    edited |= set(names(tree, "ls-files", "--others", "--exclude-standard"))
    texts = {}
    for path in paths:
        file = tree / path
        if path in edited and file.is_file() and file.stat().st_size <= BIGGEST:
            texts[path] = file.read_text(encoding="utf-8", errors="replace")
    asked = [path for path in paths if path not in edited]
    if not asked:
        return texts
    done = subprocess.run(["git", "cat-file", "--batch"], cwd=tree, capture_output=True,
                          input="".join(f"HEAD:{path}\n" for path in asked).encode("utf-8"))
    output, at = done.stdout, 0
    for path in asked:
        end = output.find(b"\n", at)
        if end < 0:
            break
        header, at = output[at:end].split(), end + 1
        if len(header) < 3 or header[1] != b"blob":
            continue                                          # "<name> missing"
        size = int(header[2])
        if size <= BIGGEST:
            texts[path] = output[at:at + size].decode("utf-8", errors="replace")
        at += size + 1
    return texts


def _aliases(tree: Path) -> list[tuple[str, list[str]]]:
    """The import aliases of tsconfig.json and jsconfig.json at the top (compilerOptions.paths): the start of an
    import -> the folders that it stands for. A file that Akasha cannot read gives none."""
    found = []
    for name in ("tsconfig.json", "jsconfig.json"):
        try:
            text = (tree / name).read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"/\*.*?\*/|^\s*//[^\n]*", "", text, flags=re.S | re.M)       # comments
            options = json.loads(re.sub(r",(\s*[}\]])", r"\1", text)).get("compilerOptions") or {}
        except (OSError, ValueError, AttributeError):
            continue
        base = str(options.get("baseUrl") or ".")
        for alias, targets in (options.get("paths") or {}).items():
            if isinstance(targets, list) and alias.rstrip("*"):
                found.append((alias.rstrip("*"), [posixpath.normpath(posixpath.join(base, str(target).rstrip("*")))
                                                 for target in targets]))
    return found


class Graph:
    """Which files import each file. Imports by tests do not count: a test is no screen."""

    def __init__(self, tree: Path, base: str, skip: tuple[str, ...] = ()) -> None:
        """`skip`: the folders of the records of the tasks. They hold no code, and the archive grows with each task."""
        listed = set(paths(tree, skip, others=True))
        known = listed | set(paths_at(tree, base, skip))                          # also files the task deleted
        self.exact: dict[str, str] = {}
        tails: dict[str, set[str]] = defaultdict(set)
        folders: dict[str, set[str]] = defaultdict(set)
        for path in sorted(known):
            if path.endswith(READ):
                key = _key(path)
                self.exact[key] = path
                parts = key.split("/")
                for start in range(1, len(parts)):             # src layouts and aliases: "utils/format", "ui"
                    tails["/".join(parts[start:])].add(path)
            if path.endswith(OTHER) and not TEST.search(path):
                parts = posixpath.dirname(path).split("/")
                for start in range(len(parts)):                # a package: "com/shop/orders", "services/orders/api"
                    folders["/".join(parts[start:])].add(posixpath.dirname(path))
        # The end of a folder path that only one folder has -> the first file of that folder
        first = {}
        for path in sorted(known):
            if path.endswith(OTHER) and not TEST.search(path):
                first.setdefault(posixpath.dirname(path), path)
        self.packages = {tail: first[next(iter(found))] for tail, found in folders.items()
                         if tail and len(found) == 1}
        unique = {tail: next(iter(paths)) for tail, paths in tails.items() if len(paths) == 1}
        self.tails = {tail: path for tail, path in unique.items() if "/" in tail}
        self.singles = {tail: path for tail, path in unique.items() if "/" not in tail}   # an alias or Python
        self.aliases = _aliases(tree)
        self.users: dict[str, set[str]] = defaultdict(set)
        code = sorted(path for path in listed if path.endswith(READ) and not TEST.search(path))
        for path, text in _texts(tree, code).items():
            for used in self._imports(path, text):
                if used != path:
                    self.users[used].add(path)

    def _find(self, key: str) -> str | None:
        return self.exact.get(key) or self.tails.get(key)

    def _module(self, key: str) -> str | None:
        """A Python module. One name is also a module of a src or backend folder on the path, for example mypkg."""
        return self._find(key) or (self.singles.get(key) if "/" not in key else None)

    def _imports(self, path: str, text: str) -> set[str]:
        found = set()
        if path.endswith(PY):
            for module, listed in PY_FROM.findall(text):
                base = self._python(path, module)
                listed = COMMENT.sub("", listed).strip("()").replace("\n", " ")
                items = [item.split()[0] for item in listed.split(",") if item.split()]
                hits = {self._module(f"{base}/{item}" if base else item) for item in items} - {None}
                found |= hits or ({self._module(base)} - {None})
            for line in PY_IMPORT.findall(text):
                line = COMMENT.sub("", line).split(";")[0]
                found |= {self._module(item.split()[0].replace(".", "/")) for item in line.split(",") if item.split()}
        elif path.endswith(OTHER):
            if path.endswith(".go"):
                specs = GO_LINE.findall(text) + [spec for block in GO_BLOCK.findall(text)
                                                 for spec in QUOTED.findall(block)]
            else:
                specs = [name.replace(".", "/") for name in DOTTED_IMPORT.findall(text)]
            found |= {self._package(spec) for spec in specs}
        else:
            for spec in JS_IMPORT.findall(text):
                found.add(self._script(path, spec))
        return found - {None}

    def _package(self, spec: str) -> str | None:
        """The file that an import of Java, Kotlin, or Go leads to: the file of the class, else the first file of
        the package. `spec`: the import with / between its parts. Only the end of the import that one folder of the
        repository has counts, so a library is no file."""
        hit = self._find(spec)
        if hit and hit.endswith(OTHER):
            return hit
        parts = spec.split("/")
        for whole in (parts, parts[:-1]):              # a package, or a member of a package (a function, a *)
            for start in range(len(whole)):
                tail = "/".join(whole[start:])
                if len(whole) - start >= 2 and tail in self.packages:
                    return self.packages[tail]
        return None

    @staticmethod
    def _python(path: str, module: str) -> str:
        dots = len(module) - len(module.lstrip("."))
        rest = module.lstrip(".").replace(".", "/")
        if not dots:
            return rest
        folder = posixpath.dirname(path)
        for _ in range(dots - 1):
            folder = posixpath.dirname(folder)
        return posixpath.join(folder, rest) if rest else folder

    def _script(self, path: str, spec: str) -> str | None:
        if spec.startswith("."):
            return self._find(_key(posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))))
        for start, folders in self.aliases:              # the paths of tsconfig.json: "@app/*" -> "src/app/*"
            if spec.startswith(start):
                for folder in folders:
                    hit = self._find(_key(posixpath.normpath(posixpath.join(folder, spec[len(start):]))))
                    if hit:
                        return hit
        if "/" not in spec:
            return None                                      # a package, for example react
        first, rest = spec.split("/", 1)
        if self._find(_key(spec)):
            return self._find(_key(spec))
        if first in ("@", "~", "src") or first.startswith("#"):
            return self._find(_key(rest)) or self.singles.get(_key(rest))      # an alias: "@/ui", "~/utils/format"
        if first.startswith("@"):                            # a scoped package, or an alias such as "@app/utils/x"
            return self.tails.get(_key(rest))                # one name, as in @nestjs/common, is a package
        return None                                          # a package with a path, for example lodash/get


def area(path: str, team: Team) -> str:
    """The area of a file: the folder of the first pattern of [core] areas that holds it, else its first two
    folders."""
    folders = path.split("/")[:-1]
    for pattern in team.core_areas:
        size = pattern.count("/") + 1
        if len(folders) >= size and matches("/".join(folders[:size]), pattern):
            return "/".join(folders[:size])
    return "/".join(folders[:2]) or path


def reason(path: str, team: Team, graph: Graph) -> str:
    """Why the file is core, or ""."""
    if any(matches(path, item) for item in team.core_paths):
        return "a path of [core]"
    others = {area(user, team) for user in graph.users.get(path, ())} - {area(path, team)}
    return f"used by {len(others)} other areas" if len(others) >= team.core_used_by else ""


def exempt(team: Team, me: str) -> bool:
    """The administrators and the people who keep the own procedure change the core without an approval."""
    return bool(me) and me in team.admins + team.own_procedure


def changed(team: Team, tree: Path, base: str) -> dict[str, str]:
    """The core files whose existing lines the work copy changed or deleted since the base commit, with the reason.
    A file with only new lines is free."""
    edited = []
    for line in names(tree, "diff", "--numstat", "--no-renames", base):
        parts = line.split("\t")
        if len(parts) == 3 and parts[1] != "0":           # "-" is a binary file: it counts as a change
            edited.append(parts[2])
    if not edited:
        return {}
    graph = Graph(tree, base, team.record_roots)
    return {path: why for path in edited if (why := reason(path, team, graph))}


def planned(team: Team, tree: Path, scope: list[str]) -> dict[str, str]:
    """The core files among the files that the task plans to change."""
    files = [path for path in paths(tree, team.record_roots) if any(matches(path, item) for item in scope)]
    if not files:
        return {}
    graph = Graph(tree, "HEAD", team.record_roots)
    return {path: why for path in files if (why := reason(path, team, graph))}


def approver(root: Path, tree: Path, number: int, team: Team, files: list[str]) -> str:
    """The administrator whose approval on GitHub holds for the core changes of the work copy now, or "". An approval
    holds while the core files are the same as in the approved commit. A later "request changes" of the same
    administrator takes it back."""
    if not files:
        return ""
    owner, _, name = origin(root).partition("/")
    found = gh_json(root, "api", "graphql", "-f", f"query={REVIEWS}", "-f", f"owner={owner}", "-f", f"name={name}",
                    "-F", f"number={number}")
    found = found if isinstance(found, dict) else {}
    nodes = (((found.get("data") or {}).get("repository") or {}).get("pullRequest") or {}).get("reviews") or {}
    latest: dict[str, dict] = {}
    for node in nodes.get("nodes") or []:
        login = str((node.get("author") or {}).get("login") or "").lower()
        if login in team.admins and node.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = node
    for login, node in latest.items():
        commit = str((node.get("commit") or {}).get("oid") or "")
        if node.get("state") == "APPROVED" and commit \
                and git(tree, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0 \
                and git(tree, "diff", "--quiet", commit, "HEAD", "--", *files).returncode == 0:
            return login
    return ""


def request(task_id: str, files: dict[str, str]) -> str:
    """The text that asks the administrators for the approval."""
    listing = "\n".join(f"- `{path}`: {why}" for path, why in files.items())
    return (f"The task changes the structure of the product: existing lines of code that other areas use, the "
            f"sheet of an area (the map), or a contract.\n\n{listing}\n\nExamine the change of these files: does each "
            "caller keep working, is a new area the right place for that work, and does a new arrow between two areas "
            "go the right way? Then approve the pull request on GitHub (Review changes → Approve). Akasha lands task "
            f"`{task_id}` after the approval. A change of these files after the approval needs a new one.")
