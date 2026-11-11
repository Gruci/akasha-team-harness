"""The map of the code: the public names of each file, where they are, and what they say about themselves.

A task that makes a function looks first at what the repository has. The map gives the names, the signatures, and
the first line of each description; never a body. It is what the code is now, not a model: a name that many files use
or that has a description is not good code for that reason. What to follow comes from the guides of the team.

Python is read with `ast` of the standard library, JavaScript and TypeScript with patterns. What Akasha cannot read
stays in the map by its kind (`unread`), and never counts as read.

The map of each file is kept by the id of its content in .docs/state/map.json (the blob id of git for a file that the
work copy did not change, a hash of the text else). A new version of the reader drops the copy. The server builds
without a copy."""

from __future__ import annotations

import ast
import hashlib
import json
import posixpath
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from akasha import core
from akasha.checks import matches
from akasha.config import STATE_DIR, Team
from akasha.repo import git, names, paths, write_whole

READER = 1                     # the version of the reader: a change of it drops the kept maps
CACHE = STATE_DIR / "map.json"
MOST = 12_000                  # characters of the map in the output of `akasha start`
FOUND = 20                     # the answers of `akasha find`
METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "websocket", "route", "api_route")
# Names that a framework fixes: they are no choice of the team, and tell nothing about what the code does
GIVEN = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "loader", "action", "Page", "Layout", "default",
         "generateMetadata", "generateStaticParams", "getServerSideProps", "getStaticProps", "getStaticPaths",
         "metadata", "config", "middleware", "main"}
JS_FUNCTION = re.compile(r"^export\s+(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*(\([^)]*\))",
                         re.M)
JS_CLASS = re.compile(r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M)
JS_ARROW = re.compile(r"^export\s+const\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(?:async\s+)?"
                      r"(?:function\s*)?(\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=\n]+?)?\s*=>", re.M)
JS_WRAPPED = re.compile(r"^export\s+const\s+([A-Z][\w$]*)\s*(?::[^=\n]+)?=\s*(?:React\.)?(?:memo|forwardRef|styled)\b",
                        re.M)
JS_PARTIAL = (("module.exports", re.compile(r"\bmodule\.exports\b|\bexports\.[A-Za-z_$]")),
              ("export * from", re.compile(r"^export\s+\*", re.M)))
JS_NAMED = re.compile(r"^export\s+(?:type\s+)?\{([^}]*)\}", re.M)          # export { a, b as c } [from "…"]
ADDRESS = re.compile(r"""['"`](/[A-Za-z0-9_\-./{}:$]*[A-Za-z0-9_}])['"`]""")
WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# Words that name one kind of work. The reader groups them only to count: a group is no rule, and words of one
# group can mean different work (one or many, a cache, a remote call, a file)
WORK = {"a read": ("get", "fetch", "load", "find", "read", "list", "query", "select", "retrieve", "search"),
        "a write": ("save", "store", "write", "put", "insert", "update", "set", "upsert"),
        "making a new thing": ("create", "make", "build", "new", "add", "generate"),
        "a removal": ("delete", "remove", "drop", "clear")}


@dataclass
class Symbol:
    name: str
    line: int
    kind: str                      # function, class, or component
    signature: str = ""
    doc: str = ""
    digest: str = ""               # of the body: Python only
    size: int = 0                  # the statements of the body: Python only
    returns: str = ""              # the return annotation: Python only
    gives: bool = True             # False when no `return <value>` and no `yield` is in the body: Python only


@dataclass
class FileMap:
    symbols: list[Symbol] = field(default_factory=list)
    routes: list[tuple[str, str, str, int]] = field(default_factory=list)      # method, address, handler, line
    addresses: list[str] = field(default_factory=list)                         # text like an address: JS and TS
    exports: list[str] = field(default_factory=list)       # the names that the file says it gives out: a plain
    #                                                        __all__ of Python, `export { a, b }` of TypeScript
    unread: str = ""               # why Akasha could not read all of it, or ""


def _words(name: str) -> list[str]:
    return [word.lower() for word in WORD.findall(name)]


def _first_line(text: str | None) -> str:
    for line in (text or "").strip().splitlines():
        line = line.strip(" *\t")
        if line and not line.startswith("@"):
            return line[:160]
    return ""


def _arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The parameters of a function, each default as `=…`: the map tells how to call it, not the values."""
    found = node.args
    plain = found.posonlyargs + found.args
    first_default = len(plain) - len(found.defaults)
    shown = [item.arg + ("=…" if at >= first_default else "") for at, item in enumerate(plain)]
    if found.vararg:
        shown.append("*" + found.vararg.arg)
    elif found.kwonlyargs:
        shown.append("*")
    shown += [item.arg + ("=…" if default is not None else "")
              for item, default in zip(found.kwonlyargs, found.kw_defaults)]
    if found.kwarg:
        shown.append("**" + found.kwarg.arg)
    return "(" + ", ".join(shown) + ")"


def _body(node: ast.AST) -> tuple[str, int]:
    """The digest and the size of the body of a function or a class, without its description."""
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    text = "\n".join(ast.dump(item, annotate_fields=False) for item in body)
    return hashlib.sha256(text.encode()).hexdigest()[:12], sum(1 for item in body for _ in ast.walk(item)
                                                               if isinstance(_, ast.stmt))


def _gives(node: ast.AST) -> bool:
    """True when the function can give a value: a `return <value>` or a `yield` of its own body. A body that only
    raises or is `...` (an abstract method, a stub) tells nothing, so it counts as giving one."""
    body = [item for item in getattr(node, "body", []) if not (isinstance(item, ast.Expr) and isinstance(
        getattr(item, "value", None), ast.Constant))]
    if not body or all(isinstance(item, (ast.Raise, ast.Pass)) for item in body):
        return True
    stack = list(body)
    while stack:
        item = stack.pop()
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue                                  # a return of an inner function is not of this one
        if isinstance(item, (ast.Yield, ast.YieldFrom)) or (isinstance(item, ast.Return) and item.value is not None):
            return True
        stack.extend(ast.iter_child_nodes(item))
    return False


def _text_of(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def read_python(text: str) -> FileMap:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return FileMap(unread="a Python syntax error")
    found = FileMap()
    listed, prefixes = None, {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) \
            else []
        value = getattr(node, "value", None)
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                items = [_text_of(item) for item in value.elts] if isinstance(value, (ast.List, ast.Tuple)) else [None]
                if all(item is not None for item in items):
                    listed = set(items)
                    found.exports = sorted(listed)
                else:
                    found.unread = "__all__ is made while the code runs"
            if isinstance(target, ast.Name) and isinstance(value, ast.Call):
                for keyword in value.keywords:               # router = APIRouter(prefix="/funds")
                    if keyword.arg == "prefix" and _text_of(keyword.value) is not None:
                        prefixes[target.id] = _text_of(keyword.value)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.ClassDef):
            signature = ""
        else:
            signature = _arguments(node)
            for mark in node.decorator_list:                  # @router.get("/x")
                call = mark if isinstance(mark, ast.Call) else None
                where = call.func if call else None
                if isinstance(where, ast.Attribute) and where.attr in METHODS and call.args \
                        and _text_of(call.args[0]) is not None:
                    owner = where.value.id if isinstance(where.value, ast.Name) else ""
                    address = (prefixes.get(owner, "").rstrip("/") + "/" + _text_of(call.args[0]).lstrip("/"))
                    found.routes.append((where.attr.upper(), address.rstrip("/") or "/", node.name, node.lineno))
        public = node.name in listed if listed is not None else not node.name.startswith("_")
        if public and node.name not in GIVEN:
            digest, size = _body(node)
            plain = not isinstance(node, ast.ClassDef)
            found.symbols.append(Symbol(node.name, node.lineno, "function" if plain else "class", signature,
                                        _first_line(ast.get_docstring(node)), digest, size,
                                        ast.unparse(node.returns) if plain and node.returns else "",
                                        _gives(node) if plain else True))
    return found


def _line(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


def _jsdoc(text: str, at: int) -> str:
    """The first line of the /** comment that ends right before the place `at`, or ""."""
    before = text[:at].rstrip()
    start = before.rfind("/**")
    if not before.endswith("*/") or start < 0 or "*/" in before[start:-2]:
        return ""
    return _first_line(before[start + 3:-2])


def read_script(path: str, text: str) -> FileMap:
    """JavaScript and TypeScript: the exported functions, classes, and components. Patterns, not a parser: a form
    that they do not read is named in `unread`."""
    found = FileMap(unread=", ".join(name for name, pattern in JS_PARTIAL if pattern.search(text)))
    seen = set()
    for pattern, kind in ((JS_FUNCTION, "function"), (JS_ARROW, "function"), (JS_CLASS, "class"),
                          (JS_WRAPPED, "component")):
        for hit in pattern.finditer(text):
            name = hit.group(1)
            if name in seen or name in GIVEN:
                continue
            seen.add(name)
            signature = hit.group(2) if kind == "function" else ""
            signature = " ".join(signature.split()) if signature.startswith("(") else f"({signature})" if signature \
                else ""
            screen = name[:1].isupper() and kind != "class" and path.endswith((".tsx", ".jsx"))
            found.symbols.append(Symbol(name, _line(text, hit.start()), "component" if screen else kind,
                                        signature[:200], _jsdoc(text, hit.start())))
    found.symbols.sort(key=lambda symbol: symbol.line)
    found.exports = sorted({item.split(" as ")[-1].strip() for names in JS_NAMED.findall(text)
                            for item in names.split(",") if item.strip()})
    found.addresses = sorted({hit for hit in ADDRESS.findall(text) if hit.count("/") >= 2 or len(hit) > 3})[:200]
    return found


def read_file(path: str, text: str) -> FileMap:
    return read_python(text) if path.endswith(core.PY) else read_script(path, text)


def _restore(data: dict) -> FileMap:
    return FileMap([Symbol(**item) for item in data.get("symbols", [])],
                   [tuple(item) for item in data.get("routes", [])], list(data.get("addresses", [])),
                   list(data.get("exports", [])), str(data.get("unread") or ""))


class Map:
    """The map of a work copy: path -> what the file holds."""

    def __init__(self, tree: Path, team: Team, keep: Path | None = None, commit: str = "") -> None:
        """`keep`: the main checkout, whose .docs/state holds the copy of the maps. None builds without a copy.
        `commit`: the map of that commit, in place of the work copy: the code that was there before a change."""
        self.tree, self.team, self.commit = tree, team, commit
        skip = team.record_roots + (team.work_dir,)
        if commit:
            blobs = _blobs_at(tree, commit, skip)
            listed, edited = list(blobs), set()
        else:
            listed = paths(tree, skip, others=True)
            edited = set(names(tree, "diff", "--name-only", "--no-renames", "HEAD")) | \
                set(names(tree, "ls-files", "--others", "--exclude-standard"))
            staged = names(tree, "ls-files", "-s")
            blobs = {entry.split("\t", 1)[1]: entry.split()[1] for entry in staged if "\t" in entry}
        listed = [path for path in listed if path.endswith(core.PY + core.JS) and not core.TEST.search(path)]
        kept = self._kept(keep)
        self.files: dict[str, FileMap] = {}
        ids, missing = {}, []
        for path in listed:
            ids[path] = blobs.get(path, "") if path not in edited else ""
            if ids[path] and ids[path] in kept:
                self.files[path] = _restore(kept[ids[path]])
            else:
                missing.append(path)
        texts = {} if not missing else _blob_texts(tree, {path: blobs[path] for path in missing}) if commit \
            else core._texts(tree, missing)
        for path in missing:
            if path not in texts:
                self.files[path] = FileMap(unread="the file is larger than 1 MB, or Akasha cannot read it")
                continue
            if not ids[path]:
                ids[path] = "text:" + hashlib.sha256(texts[path].encode("utf-8", errors="replace")).hexdigest()
            self.files[path] = _restore(kept[ids[path]]) if ids[path] in kept else read_file(path, texts[path])
        if keep is not None and missing:
            self._keep(keep, {ids[path]: asdict(found) for path, found in self.files.items() if ids.get(path)})
        self._graph: core.Graph | None = None

    @staticmethod
    def _kept(keep: Path | None) -> dict:
        if keep is None:
            return {}
        try:
            data = json.loads((keep / CACHE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data.get("files", {}) if isinstance(data, dict) and data.get("reader") == READER else {}

    @staticmethod
    def _keep(keep: Path, files: dict) -> None:
        try:
            (keep / CACHE).parent.mkdir(parents=True, exist_ok=True)
            write_whole(keep / CACHE, json.dumps({"reader": READER, "files": files}, ensure_ascii=False))
        except OSError:
            pass                                      # the copy only saves time

    @property
    def graph(self) -> core.Graph:
        if self._graph is None:
            self._graph = core.Graph(self.tree, self.commit or "HEAD", self.team.record_roots)
        return self._graph

    def area(self, path: str) -> str:
        return core.area(path, self.team)

    def areas(self) -> dict[str, tuple[int, int]]:
        """area -> (public names, files)."""
        found: dict[str, list[int]] = {}
        for path, held in self.files.items():
            count = found.setdefault(self.area(path), [0, 0])
            count[0] += len(held.symbols)
            count[1] += 1
        return {name: (count[0], count[1]) for name, count in sorted(found.items())}

    def under(self, place: str) -> dict[str, FileMap]:
        """The files of a folder, of a file, or of an area."""
        place = place.strip("/").replace("\\", "/")
        return {path: held for path, held in sorted(self.files.items())
                if not place or path == place or path.startswith(place + "/")}

    def unread(self) -> dict[str, list[str]]:
        """What Akasha could not read, by its kind: kind -> files."""
        found: dict[str, list[str]] = {}
        for path, held in sorted(self.files.items()):
            if held.unread:
                found.setdefault(held.unread, []).append(path)
        return found

    def routes(self, start: str = "") -> list[tuple[str, str, str, int, list[str]]]:
        """Each address of the server: method, address, the file of its handler and the handler, its line, and the
        screen files that hold the address as text (the same text, or the same end of two parts or more)."""
        users: dict[str, list[str]] = {}
        for path, held in self.files.items():
            for text in held.addresses:
                users.setdefault(_shape(text), []).append(path)
        found = []
        for path, held in sorted(self.files.items()):
            for method, address, handler, line in held.routes:
                if start and not address.startswith(start):
                    continue
                shape = _shape(address)
                screens = sorted({user for text, files in users.items() if _same_address(shape, text)
                                  for user in files})
                found.append((method, address, f"{path}::{handler}", line, screens))
        return sorted(found, key=lambda item: (item[1], item[0]))

    def shared_parts(self) -> list[tuple[str, int, int]]:
        """The component files that more than one area imports: path, the files that import it, their areas."""
        found = []
        for path, held in self.files.items():
            if not any(symbol.kind == "component" for symbol in held.symbols):
                continue
            users = self.graph.users.get(path, set())
            areas = {self.area(user) for user in users} - {self.area(path)}
            if areas:
                found.append((path, len(users), len(areas)))
        return sorted(found, key=lambda item: (-item[2], -item[1], item[0]))

    def find(self, words: list[str]) -> list[tuple[str, Symbol]]:
        """The public names that the words fit best: in the words of the name, the description, the signature, and
        the path."""
        wanted = [word.lower() for item in words for word in (_words(item) or [item])]
        scored = []
        for path, held in self.files.items():
            folder = set(_words(path))
            for symbol in held.symbols:
                name, doc = set(_words(symbol.name)), symbol.doc.lower()
                score = sum(4 * (word in name) + 2 * (word in doc) + (word in folder)
                            + (word in symbol.signature.lower()) for word in wanted)
                score += 3 * sum(1 for item in words if item.lower() in symbol.name.lower())
                if score:
                    scored.append((score, path, symbol))
        scored.sort(key=lambda item: (-item[0], item[1], item[2].line))
        return [(path, symbol) for _score, path, symbol in scored[:FOUND]]


def _blobs_at(tree: Path, commit: str, skip: tuple[str, ...]) -> dict[str, str]:
    """The files of a commit without the folders `skip`, each with the id of its content: path -> blob id. Git
    reads the commit into an index of its own (repo.paths_at tells why)."""
    from akasha.repo import _without
    with tempfile.TemporaryDirectory() as folder:
        env = {"GIT_INDEX_FILE": str(Path(folder) / "index")}
        read = git(tree, "read-tree", commit, env=env)
        if read.returncode:
            raise RuntimeError(f"git read-tree {commit} failed: {read.stderr.strip()[:300]}")
        staged = names(tree, "ls-files", "-s", *_without(skip), env=env)
    return {entry.split("\t", 1)[1]: entry.split()[1] for entry in staged if "\t" in entry}


def _blob_texts(tree: Path, blobs: dict[str, str]) -> dict[str, str]:
    """The text of each file by the id of its content, in one process of git, without the files larger than
    core.BIGGEST."""
    asked = list(blobs.items())
    done = subprocess.run(["git", "cat-file", "--batch"], cwd=tree, capture_output=True,
                          input="".join(f"{blob}\n" for _path, blob in asked).encode("utf-8"))
    output, at, texts = done.stdout, 0, {}
    for path, _blob in asked:
        end = output.find(b"\n", at)
        if end < 0:
            break
        header, at = output[at:end].split(), end + 1
        if len(header) < 3 or header[1] != b"blob":
            continue
        size = int(header[2])
        if size <= core.BIGGEST:
            texts[path] = output[at:at + size].decode("utf-8", errors="replace")
        at += size + 1
    return texts


def _shape(address: str) -> str:
    """An address without the names of its variable parts: /funds/{cd}, /funds/:cd, and /funds/${cd} are the same."""
    parts = [("{}" if part.startswith((":", "{", "$")) or "${" in part else part)
             for part in address.split("?")[0].strip("/").split("/")]
    return "/".join(parts)


def _same_address(route: str, text: str) -> bool:
    if route == text:
        return True
    one, other = route.split("/"), text.split("/")
    size = min(len(one), len(other))
    return size >= 2 and one[-size:] == other[-size:]


def line_of(path: str, symbol: Symbol, folder: str = "") -> str:
    shown = posixpath.relpath(path, folder) if folder else path
    return f"{shown}:{symbol.line} {symbol.name}{symbol.signature}" + (f" — {symbol.doc}" if symbol.doc else "")


def overview(found: Map) -> list[str]:
    lines = [f"{area}: {count} public names in {files} files" for area, (count, files) in found.areas().items()]
    for kind, files in found.unread().items():
        lines.append(f"not read ({kind}): {len(files)} files, for example {', '.join(files[:3])}")
    return lines or ["no Python, JavaScript, or TypeScript file"]


def listing(found: Map, place: str) -> list[str]:
    files = found.under(place)
    lines = [line_of(path, symbol) for path, held in files.items() for symbol in held.symbols]
    lines += [f"{path}: not read ({held.unread})" for path, held in files.items() if held.unread]
    return lines or [f"no public name under {place}"]


def _areas_of(found: Map, scope: list[str]) -> list[str]:
    """The areas that the planned files of a task are in. A pattern that fits no file yet names its fixed folder."""
    areas = []
    for item in scope:
        hits = [path for path in found.files if matches(path, item)]
        if not hits:
            fixed = item.split("*")[0].rstrip("/")
            fixed = fixed if item.endswith("/**") or "*" in item else posixpath.dirname(fixed)
            hits = [fixed + "/x"] if fixed else []
        areas += [found.area(path) for path in hits]
    return list(dict.fromkeys(areas))


def shown_map(found: Map, scope: list[str], most: int = MOST) -> list[str]:
    """The `map` lines of `akasha start`: the public names of the areas of the scope, in at most `most`
    characters. Over that, one line for each file, and the output says so."""
    lines = []
    left = most
    for area in _areas_of(found, scope):
        files = found.under(area)
        count = sum(len(held.symbols) for held in files.values())
        if not count:
            continue
        head = f"map — {area}: {count} public names in {len(files)} files · the code as it is now, not a model"
        full = [f"  {line_of(path, symbol, area)}" for path, held in files.items() for symbol in held.symbols]
        if sum(len(line) + 1 for line in full) > left:
            full = [f"  {posixpath.relpath(path, area)}: {len(held.symbols)} public names"
                    for path, held in files.items() if held.symbols]
            head += " · shortened to one line for each file"
            if sum(len(line) + 1 for line in full) > left:
                full = []
        lines += [head, *full]
        left -= sum(len(line) + 1 for line in full)
    if lines:
        lines.append("  `akasha map <folder>` shows each name · `akasha find <words>` searches names and descriptions")
    return lines


def verbs(found: Map, place: str = "") -> Counter:
    """The first word of each public function under a place."""
    return Counter(_words(symbol.name)[0] for held in found.under(place).values() for symbol in held.symbols
                   if symbol.kind == "function" and _words(symbol.name))


def usual_words(found: Map, area: str) -> list[str]:
    """What the names of nearby code tell about each kind of work, for the `names` line: the usual word of the area
    (three functions or more, one word for 80% of them), else of the repository (15 or more, 80%), else that the
    count alone shows no usual word, with the count as a fact. Akasha never calls the names mixed, and never tells
    to make one word of them: words of one group can mean different work."""
    here, everywhere = verbs(found, area), verbs(found)
    lines = []
    for work, words in WORK.items():
        near = {word: here[word] for word in words if here[word]}
        total = sum(near.values())
        if not total:
            continue
        top, most = max(near.items(), key=lambda item: item[1])
        counted = ", ".join(f"{word}_ {count}" for word, count in sorted(near.items(), key=lambda item: -item[1]))
        if total >= 3 and most * 5 >= total * 4:
            lines.append(f"{area}: the usual word for {work} here is {top}_ ({most} of {total})")
            continue
        far = {word: everywhere[word] for word in words if everywhere[word]}
        whole = sum(far.values())
        far_top, far_most = max(far.items(), key=lambda item: item[1])
        if total < 3 and whole >= 15 and far_most * 5 >= whole * 4:
            lines.append(f"{area}: the usual word for {work} in the repository is {far_top}_ ({far_most} of {whole})")
        elif total >= 3:
            lines.append(f"{area}: the count alone shows no usual word for {work} here ({counted}): one word for "
                         "the same work; when the work differs, the name shows the difference")
        else:
            lines.append(f"{area}: {work} here is named {counted}")
    return lines


def _definition_lines(team: Team, tree: Path, scope: list[str], title: str) -> list[str]:
    """The definitions of the team that the task touches: its planned files are their code, or its title holds
    their word."""
    from akasha import definitions
    if not team.definitions_on:
        return []
    try:
        items = definitions.parse(definitions.place(tree).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [definitions.line_of(item) for item in definitions.touching(items, scope, title, matches)]


def start_lines(team: Team, tree: Path, keep: Path | None, scope: list[str], title: str = "") -> list[str]:
    """What `akasha start` shows about the code, in this order: what to follow first (the guides of the team, the
    rules for names), then the code as it is now (the names of nearby code, the map, the shared components)."""
    from akasha import naming
    found = Map(tree, team, keep)
    files = [path for path in found.files if any(matches(path, item) for item in scope)] + list(scope)
    guides = list(dict.fromkeys(item for step in ("plan", "build") for item in team.guides.get(step, ())))
    lines = [f"guides — {' · '.join(guides)}"] if guides else []
    lines += naming.lines(files)
    lines += [f"definition — {line}" for line in _definition_lines(team, tree, scope, title)]
    for area in _areas_of(found, scope):
        lines += [f"names — {line}" for line in usual_words(found, area)]
    lines += shown_map(found, scope)
    screens = [path for path in files if path.endswith((".tsx", ".jsx"))
               or any(matches(path, item) for item in team.screen_paths)]
    parts = found.shared_parts()[:5] if screens else []
    if parts:
        lines.append("parts — found: " + " · ".join(f"{path} ({users} files in {areas} other areas import this "
                                                    "file)" for path, users, areas in parts)
                     + ". The count is how far a change reaches, not a model to follow")
    return lines
