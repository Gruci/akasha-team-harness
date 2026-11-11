"""The pins of a repository: whether the versions of its runtime, its libraries, and its base images are fixed.

When they float, the same commit installs other things on another day. Mostly nobody decided that: nobody knew.
Akasha makes an administrator know and decide. It stops nothing by default, and it never chooses a version.

What it reads, one list and its pair at a time (a lock of the frontend fixes nothing of the server):

- a list of libraries (`requirements*.txt`, `pyproject.toml`, `package.json`) and the lock in the same folder. With
  the lock, a range (`^`, `>=`) is fixed, and only a library without any version counts. Without it, each line that
  is not exact (`==`, or one exact version) counts;
- the base images of `Dockerfile*`: an image without a tag, or with a tag without a number (`latest`, `slim`),
  floats. A tag without a patch version or a digest (`python:3.11-slim`) is only named.

`[pins] policy` of akasha.toml holds the answer of the administrator: no value (not answered: the doctor tells),
"observe" (known, and left), "new" (what is there stays, and no change adds more), "all" (each one is fixed). The
check is a rule of the consistency check, with the policy of the base branch. Where the policy protects, a file that
Akasha cannot read fails: it is no pass.

It does not judge whether a lock is old, and it does not see what a deployment really installs."""

from __future__ import annotations

import json
import posixpath
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field

POLICIES = ("observe", "new", "all")
LOCKS = {"requirements": (), "pyproject.toml": ("uv.lock", "poetry.lock", "pdm.lock"),
         "package.json": ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock")}
ALL_LOCKS = tuple(name for names in LOCKS.values() for name in names)
REQUIREMENTS = re.compile(r"(^|/)requirements[^/]*\.txt$")
DOCKERFILE = re.compile(r"(^|/)Dockerfile[^/]*$|\.dockerfile$", re.I)
_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(.*)$")
_EXACT = re.compile(r"^(===?)\s*[^,;*\s]+\s*(;.*)?$")
_NUMBER = re.compile(r"\d")
_PATCH = re.compile(r"\d+\.\d+\.\d+")
_ONE_VERSION = re.compile(r"^v?\d+(\.\d+)*([.-][0-9A-Za-z.]+)?$")
Read = Callable[[str], "str | None"]


@dataclass
class Listing:
    """One list of libraries, or one Dockerfile, and what floats in it."""
    path: str
    kind: str                                  # libraries, or images
    total: int = 0
    lock: str = ""                             # the lock beside a list of libraries
    floating: list[str] = field(default_factory=list)         # the entries that are not fixed
    named: list[str] = field(default_factory=list)            # images without a patch version or a digest: a notice
    unread: str = ""                           # why Akasha could not read it

    @property
    def line(self) -> str:
        """One line for a person."""
        if self.unread:
            return f"{self.path}: Akasha could not confirm it ({self.unread})"
        if self.kind == "images":
            parts = ([f"{len(self.floating)} of {self.total} base images float ({', '.join(self.floating[:3])})"]
                     if self.floating else [f"{self.total} base images have a version"])
            if self.named:
                parts.append(f"{', '.join(self.named[:3])} has no patch version or digest")
            return f"{self.path}: " + "; ".join(parts)
        beside = f"the lock {posixpath.basename(self.lock)} is beside it" if self.lock else "no lock file is beside it"
        if not self.floating:
            return f"{self.path}: each of {self.total} libraries is fixed ({beside})"
        what = "have no version" if self.lock else "have no exact version"
        return f"{self.path}: {len(self.floating)} of {self.total} libraries {what}, and {beside}"


def _requirement(line: str) -> tuple[str, bool] | None:
    """A line of requirements: (the library, True when its version is exact), or None for a line that is no
    library."""
    line = line.split(" #")[0].strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("-"):                   # an option of pip; -r and -c are read apart; -e . is the project
        return None
    if "://" in line or line.startswith("git+"):
        name = line.split("#egg=")[-1] if "#egg=" in line else line
        mark = line.split("#")[0].rsplit("@", 1)
        fixed = len(mark) == 2 and "/" not in mark[1] and bool(_NUMBER.search(mark[1]))    # a tag or a commit
        return name, fixed
    found = _NAME.match(line)
    if not found:
        return None
    return found.group(1).lower(), bool(_EXACT.match(found.group(3).strip()))


def requirements(path: str, read: Read, seen: frozenset = frozenset()) -> Listing:
    """A requirements file, with the files that it takes in with -r. A constraints file (-c) fixes what it names."""
    text = read(path)
    found = Listing(path, "libraries")
    if text is None:
        found.unread = "the file is not there"
        return found
    entries: dict[str, bool] = {}
    limits: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        option, _, value = line.partition(" ")
        if option in ("-r", "--requirement", "-c", "--constraint") and value.strip():
            other = posixpath.normpath(posixpath.join(posixpath.dirname(path), value.strip()))
            if other in seen:
                continue
            taken = requirements(other, read, seen | {path})
            if taken.unread:
                found.unread = f"{other}: {taken.unread}"
            elif option in ("-c", "--constraint"):
                limits |= {name for name in _names(other, read) if name not in taken.floating}
            else:
                entries.update({name: name not in taken.floating for name in _names(other, read)})
            continue
        entry = _requirement(line)
        if entry:
            entries[entry[0]] = entry[1]
    found.total = len(entries)
    found.floating = sorted(name for name, fixed in entries.items() if not fixed and name not in limits)
    return found


def _names(path: str, read: Read) -> list[str]:
    return [entry[0] for line in (read(path) or "").splitlines() if (entry := _requirement(line.strip()))]


def _lock_of(path: str, kind: str, exists: Callable[[str], bool]) -> str:
    folder = posixpath.dirname(path)
    return next((posixpath.join(folder, name) for name in LOCKS[kind] if exists(posixpath.join(folder, name))), "")


def package(path: str, read: Read, exists: Callable[[str], bool]) -> Listing:
    found = Listing(path, "libraries", lock=_lock_of(path, "package.json", exists))
    try:
        data = json.loads(read(path) or "")
        entries = {name: str(spec) for key in ("dependencies", "devDependencies", "optionalDependencies")
                   for name, spec in (data.get(key) or {}).items()}
    except (ValueError, AttributeError):
        found.unread = "it is no JSON that Akasha can read"
        return found
    found.total = len(entries)
    for name, spec in sorted(entries.items()):
        spec = spec.strip()
        nothing = spec in ("", "*", "latest", "x") or (("/" in spec or ":" in spec) and "#" not in spec
                                                      and not spec.startswith(("npm:", "workspace:", "file:")))
        if nothing or (not found.lock and not _ONE_VERSION.match(spec)
                       and not spec.startswith(("workspace:", "file:"))):
            found.floating.append(name)
    return found


def pyproject(path: str, read: Read, exists: Callable[[str], bool]) -> Listing:
    found = Listing(path, "libraries", lock=_lock_of(path, "pyproject.toml", exists))
    try:
        data = tomllib.loads(read(path) or "")
    except tomllib.TOMLDecodeError:
        found.unread = "it is no TOML that Akasha can read"
        return found
    project = data.get("project") or {}
    listed = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        listed += list(group)
    entries = {entry[0]: entry[1] for line in listed if isinstance(line, str) and (entry := _requirement(line))}
    versions = {entry[0]: bool(_NAME.match(line).group(3).split(";")[0].strip()) for line in listed
                if isinstance(line, str) and (entry := _requirement(line)) and _NAME.match(line)}
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        spec = spec.get("version", "") if isinstance(spec, dict) else str(spec)
        entries[name.lower()] = bool(_ONE_VERSION.match(spec.strip()))
        versions[name.lower()] = spec.strip() not in ("", "*")
    found.total = len(entries)
    found.floating = sorted(name for name, exact in entries.items()
                            if (not versions.get(name, False)) or (not found.lock and not exact))
    return found


def dockerfile(path: str, read: Read) -> Listing:
    found = Listing(path, "images")
    text = read(path)
    if text is None:
        found.unread = "the file is not there"
        return found
    stages, defaults = set(), {}
    for line in text.splitlines():
        words = line.split("#")[0].split()
        if len(words) >= 2 and words[0].upper() == "ARG":
            name, _, value = words[1].partition("=")
            defaults[name] = value.strip("\"'")
        if len(words) < 2 or words[0].upper() != "FROM":
            continue
        image = next((word for word in words[1:] if not word.startswith("--")), "")
        earlier = image in stages                     # an earlier stage of the same file: no image of outside
        if len(words) >= 4 and words[-2].upper() == "AS":
            stages.add(words[-1])
        if earlier or image == "scratch":
            continue
        missing = [name for name in re.findall(r"\$\{?(\w+)", image) if not defaults.get(name)]
        if missing:
            found.unread = f"the image {image} takes {missing[0]}, which has no default in the file"
            continue
        image = re.sub(r"\$\{?(\w+)\}?", lambda hit: defaults[hit.group(1)], image)
        found.total += 1
        name, _, digest = image.partition("@")
        tag = name.rsplit(":", 1)[1] if ":" in name.rsplit("/", 1)[-1] else ""
        if digest:
            continue
        if not tag or not _NUMBER.search(tag):
            found.floating.append(image)
        elif not _PATCH.search(tag):
            found.named.append(image)
    return found


def observe(files: list[str], read: Read) -> list[Listing]:
    """Each list of libraries and each Dockerfile among the files of a repository, with what floats in it. A
    requirements file that another one takes in with -r is part of that one."""
    present = set(files)
    found, inner = [], set()
    for path in sorted(files):
        name = posixpath.basename(path)
        if REQUIREMENTS.search(path):
            for line in (read(path) or "").splitlines():
                option, _, value = line.strip().partition(" ")
                if option in ("-r", "--requirement", "-c", "--constraint") and value.strip():
                    inner.add(posixpath.normpath(posixpath.join(posixpath.dirname(path), value.strip())))
            found.append(requirements(path, read))
        elif name == "package.json" and "node_modules/" not in path:
            found.append(package(path, read, present.__contains__))
        elif name == "pyproject.toml":
            listing = pyproject(path, read, present.__contains__)
            if listing.total or listing.unread:
                found.append(listing)
        elif DOCKERFILE.search(path):
            found.append(dockerfile(path, read))
    return [listing for listing in found if listing.path not in inner and (listing.total or listing.unread)]


def notice(found: list[Listing]) -> str:
    """One line for the doctor of a repository whose administrator did not answer yet, or "" when nothing floats."""
    loose = [listing for listing in found if listing.floating or listing.unread]
    if not loose:
        return ""
    first = loose[0]
    more = f" (and {len(loose) - 1} more: `akasha map --report`)" if len(loose) > 1 else ""
    return (f"{first.line}{more}. A build can install other versions each time. An administrator decides: `akasha "
            "setup` ([pins] policy)")


def problems(policy: str, before: list[Listing], now: list[Listing], changed: list[str],
             removed: list[str]) -> list[str]:
    """Why the change does not keep the pins of the team, or []. "new": the change adds no floating library and no
    floating base image, and takes no lock away. "all": nothing floats in the lists that are there."""
    if policy not in ("new", "all"):
        return []
    found = []
    old = {listing.path: listing for listing in before}
    for listing in now:
        if policy == "new" and listing.path not in changed:
            continue
        if listing.unread:
            found.append(f"{listing.path}: Akasha could not confirm its versions ({listing.unread}), and [pins] policy "
                         f"= \"{policy}\" protects them. Write it in a form that Akasha reads, or an administrator "
                         "chooses \"observe\"")
            continue
        was = set(old[listing.path].floating) if listing.path in old and policy == "new" else set()
        loose = [name for name in listing.floating if name not in was]
        if not loose:
            continue
        if listing.kind == "images":
            found.append(f"{listing.path}: the base image {', '.join(loose[:3])} floats. Name a version, for "
                         "example python:3.12.7-slim, or a digest")
        elif listing.lock:
            found.append(f"{listing.path}: {', '.join(loose[:5])} has no version. Give each one a version or a "
                         "range: the lock fixes what installs")
        else:
            found.append(f"{listing.path}: {', '.join(loose[:5])} has no exact version, and no lock file is beside "
                         "the list. Write name==version, or add the lock of the package tool in this change")
    for path in removed:
        if posixpath.basename(path) in ALL_LOCKS:
            found.append(f"{path}: the change takes away a lock file, which fixed what installs. Keep it, or an "
                         "administrator changes [pins] policy")
    return found
