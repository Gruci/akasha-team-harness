"""Run the required checks of the team in a work copy, and in the checkout of the server check.

Each command runs in the shell of the operating system: cmd.exe on Windows, /bin/sh on macOS and Linux."""

from __future__ import annotations

import fnmatch
import locale
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from akasha import config, secrets, version
from akasha.config import CONFIG_FILE, Check, Team
from akasha.repo import GROUP, git, names, stop

TIMEOUT_SECONDS = 1800
WINDOWS = os.name == "nt"
PASSING = ("PASS", "NOT_NEEDED")         # NOT_NEEDED: the change touches no file that the check examines
ADMIN_PATHS = (CONFIG_FILE, ".github/**", "CODEOWNERS", "docs/CODEOWNERS")    # the rules of Akasha, the GitHub files
ADMIN_ONLY = "admin_only"                # the check that a teammate's task leaves the administrators' files alone
FOLDERS = "folders"                      # the check that [work] records and archive stay as the team set them


@dataclass
class Result:
    status: dict[str, str] = field(default_factory=dict)     # check -> PASS, FAIL, SKIP, or NOT_NEEDED
    details: dict[str, str] = field(default_factory=dict)    # check -> the end of its output


def matches(path: str, pattern: str) -> bool:
    """A file pattern: * also matches /, and a leading **/ also matches a file at the top."""
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return fnmatch.fnmatchcase(path, pattern)


def locked(team: Team, me: str) -> tuple[str, ...]:
    """The file patterns that only an administrator changes: the rules of Akasha, the GitHub files, and the paths of
    [risk], such as the database and the deployment. An administrator approves only a change of existing lines of core
    code, and no person reviews the rest of a task: so the administrators maintain these files, and a person who
    keeps the own procedure of the repository changes them too."""
    return () if me and me in team.admins + team.own_procedure else ADMIN_PATHS + team.risk_paths


def locked_files(team: Team, me: str, changed: list[str], own: tuple[str, ...] = ()) -> list[str]:
    """The changed files that only an administrator changes: the files of `locked`, and the archive of the other
    tasks. `own`: the records folders of this task, also in the archive. The archive is the record of what the team
    merged: a task adds its own folder, and changes no other."""
    patterns = locked(team, me)
    if not patterns:
        return []
    top = team.archive_dir.rstrip("/") + "/"
    return [path for path in changed if any(matches(path, item) for item in patterns)
            or (path.startswith(top) and not any((path + "/").startswith(folder.rstrip("/") + "/") for folder in own))]


def folders_problem(team: Team, root: Path, base: str) -> str:
    """Why the change cannot move the folders of the records, or "". `team`: the rules of the base. [work] records
    and archive are set once, when Akasha comes into the repository. After a change of the archive folder, each new
    work copy would hold the old archive again, and Akasha would need a list of the old folders to leave them out.
    So Akasha has no way to move them. One change is free: the task of an administrator that raises [team] version
    to a new major version sets the folders again, and moves the old records in the same task, because a major
    version can give the folders another meaning (1.x kept the records of merged tasks in the records folder)."""
    if config.shown(root, base) is None:
        return ""                                      # the base has no Akasha yet: this change brings it in
    try:
        new = config.load(root)
    except (config.ConfigError, OSError):
        return ""
    from akasha import version
    if team.version and new.version and version.number(new.version)[:1] > version.number(team.version)[:1]:
        return ""                                      # a new major version: the folders can mean other things
    for key, old, now in (("records", team.records_dir, new.records_dir), ("archive", team.archive_dir, new.archive_dir)):
        if old != now:
            return (f"[work] {key} is {old} in the team rules, and this change makes it {now}. The folders of the "
                    "records are set once, when Akasha comes into the repository: Akasha has no way to move "
                    f"them. Put {key} = \"{old}\" back")
    return ""


def touches(files: list[str], patterns: tuple[str, ...]) -> list[str]:
    return [path for path in files if any(matches(path, item) for item in patterns)]


def changed_files(tree: Path, base: str) -> list[str]:
    """The files that changed in the work copy since the base commit, also new files that git does not track."""
    changed = names(tree, "diff", "--name-only", "--no-renames", base) if base else []
    return sorted(set(changed) | set(names(tree, "ls-files", "--others", "--exclude-standard")))


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def shell(command: str, folder: Path) -> tuple[str, str]:
    """Run one command: PASS or FAIL, and the end of its output."""
    if WINDOWS and command.startswith("./"):
        command = ".\\" + command[2:]
    process = subprocess.Popen(command, shell=True, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               **GROUP)
    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        stop(process)
        process.communicate()
        return "FAIL", f"the command did not stop in {TIMEOUT_SECONDS} seconds: {command}"
    return ("PASS" if process.returncode == 0 else "FAIL"), _short(_decode(output).strip())


def _short(text: str, size: int = 3000) -> str:
    """The start and the end of a long output: a check can name its failure early and sum up at the end."""
    return text if len(text) <= size else f"{text[:size // 3]}\n…\n{text[-(size * 2 // 3):]}"


def secrets_status(tree: Path, changed: list[str]) -> tuple[str, str]:
    hits = []
    for name in changed:
        path = tree / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits += [f"{name}:{line} {kind}" for line, kind in secrets.find(text)]
    return ("FAIL", "\n".join(hits)) if hits else ("PASS", "")


def needed(check: Check, changed: list[str], run_all_when: tuple[str, ...]) -> bool:
    patterns = check.only_when + run_all_when
    return not check.only_when or any(matches(path, item) for path in changed for item in patterns)


def command(check: Check) -> str:
    return check.command_windows if WINDOWS and check.command_windows else check.command


def run(team: Team, tree: Path, changed: list[str], only: tuple[str, ...] = ()) -> Result:
    """Run each required check, or only the checks `only`. A required check without a command is SKIP, and SKIP is
    not a pass."""
    result = Result()
    for name in team.required_checks:
        if only and name not in only:
            continue
        if name == "secrets":
            status, detail = secrets_status(tree, changed)
        elif name not in team.checks:
            status, detail = "SKIP", f"{CONFIG_FILE} has no command for the check {name}"
        elif not needed(team.checks[name], changed, team.run_all_when):
            status, detail = "NOT_NEEDED", "no changed file matches only_when"
        elif not (tree / team.checks[name].cwd).is_dir():
            status, detail = "FAIL", f"the folder {team.checks[name].cwd} of the check {name} does not exist"
        else:
            status, detail = shell(command(team.checks[name]), tree / team.checks[name].cwd)
        result.status[name], result.details[name] = status, detail
    return result


def passed(status: dict[str, str]) -> bool:
    return bool(status) and all(item in PASSING for item in status.values())


def _head_version(root: Path) -> str:
    """The version of the team in the pull request itself: the task of an administrator that raises it installs the
    new version in its own workflows, while the rules still come from the base branch."""
    try:
        return config.load(root).version
    except config.ConfigError:
        return ""


def _leave_archive_out(team: Team, root: Path, changed: list[str]) -> str:
    """Before the checks of the team run on the server: take the archive of the other tasks out of the checkout, so
    that no checker of the team reads the records of each task that ever merged. The records of this pull request
    stay. Return a problem, or "". The checkout of the server fetched all files before: this saves no download."""
    from akasha import work
    from akasha.task import record_folders
    top = team.archive_dir.rstrip("/")
    if git(root, "cat-file", "-e", f"HEAD:{top}").returncode:
        return ""                                      # no archive yet
    own = tuple(sorted(folder for folder in record_folders(team, changed) if folder.startswith(top + "/")))
    try:
        work.sparse(root, top, own)
    except RuntimeError as error:
        return f"{error}. The checks of the team did not run"
    return work.restore(root)


def ci(team: Team, root: Path, base: str, author: str = "", head: str = "") -> Result:
    """The server check: the checks on the files that the pull request changes. The setup command runs first. A
    pull request of a quick task also passes the quick check: its change must be a quick change (quick.py). A pull
    request of a task without a screen passes the screen check: its change touches no screen file (screen.py). The
    Akasha that runs must be the version of the team, else the server runs other rules than the computers."""
    found = version.server_problem((team.version, _head_version(root)))
    if found:
        return Result({version.CHECK: "FAIL"}, {version.CHECK: found})
    changed = names(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD")
    found = folders_problem(team, root, base) or _leave_archive_out(team, root, changed)
    if found:
        return Result({FOLDERS: "FAIL"}, {FOLDERS: found})
    if team.setup:
        status, detail = shell(team.setup, root)
        if status != "PASS":
            return Result({"setup": status}, {"setup": detail})
    result = run(team, root, changed)
    from akasha import quick, screen              # they use this module
    found = quick.server(team, root, base, changed)
    if found:
        result.status["quick"], result.details["quick"] = found
    found = screen.server(team, changed, root)
    if found:
        result.status[screen.CHECK], result.details[screen.CHECK] = found
    from akasha import consistency, evidence      # they use this module
    result.status[evidence.CHECK], result.details[evidence.CHECK] = evidence.server(team, root, base, changed,
                                                                                    author, head)
    start = git(root, "merge-base", base, "HEAD").stdout.strip()
    if start and config.shown(root, base) is not None:
        # The same function as `akasha check`. The plan comes from the records of the task of the pull request
        plan, is_task = evidence.plan_of(team, root, base, changed, head)
        from akasha import codemap, product
        maps = codemap.Pair(root, team, None, start)
        admin = author.lower() in team.admins + team.own_procedure
        try:
            status, why, notes = consistency.examine(team, root, start, None, plan, candidates=is_task, admin=admin,
                                                     maps=maps)
        except (RuntimeError, OSError) as error:
            status, why, notes = "FAIL", f"Akasha could not compare the code: {error}", []
        result.status[consistency.CHECK] = status
        result.details[consistency.CHECK] = "\n".join([why, *notes]).strip()
        # The checks of the product: the same functions as `akasha check`
        # A pull request that is no task has no plan and no preview: the checks of the plan and of the proof are
        # NOT_NEEDED for it
        shown, own = evidence.preview_of(team, root, base, changed, head) if is_task else (None, ())
        status_of, details, notes = product.run(product.Change(team, root, start, changed, maps, admin,
                                                               plan if is_task else None, shown, own))
        for name, status in status_of.items():
            result.status[name] = status
            result.details[name] = "\n".join([details[name], *(notes if status == "FAIL" else [])]).strip()
        real, why = product.integration(team, changed, result.status)
        if real != "NOT_NEEDED":
            result.status[product.INTEGRATION], result.details[product.INTEGRATION] = real, why
    return result
