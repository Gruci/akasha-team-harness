"""The setup of a repository by an administrator, and the readiness of each person (doctor)."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from akasha import VERSION, checks, claude, codex, config, github, langs, repo, version, work
from akasha.config import CONFIG_FILE, STATE_DIR, Team
from akasha.task import all_local

NEXT_STEPS = ("Next: answer the questions of the setup in akasha.toml and run `akasha setup` again. An administrator "
              "of the GitHub repository runs `akasha setup --apply` on their computer. Then commit these files on a "
              "new branch, open a pull request, wait for its checks, and merge it.")
HOOK_SCRIPT = Path(__file__).resolve().parents[1] / "hook.sh"      # in the plugin: the hooks find Python with it
PERSONAL = (".claude/settings.local.json", "CLAUDE.local.md")      # the own agent settings of each person: not in git


@dataclass(frozen=True)
class Choice:
    """The answers of an administrator at the first setup."""
    new: bool = False                      # a repository that starts now: the definitions and the structure guide
    stack: tuple[str, ...] = ()            # the languages, for example ("python", "typescript")
    areas: str = ""                        # the folder of one area, for example "domains/*"
    entries: tuple[str, ...] = ()          # the entry files of an area, for example ("api.py", "index.ts")


ARCHITECTURE = "docs/architecture.md"
TEMPLATES = Path(__file__).parent / "templates"


def _checks(packs: list) -> tuple[list[str], list[str]]:
    """The required checks of the packs and their tables: the tests and the lint of each language, each with the
    files of that language in only_when. A pull request without a file of a language does not run its checks; the
    first file of the language starts them."""
    required, tables = [], []
    for pack in packs:
        for kind, command in (("tests", pack.tests), ("lint", pack.lint)):
            if not command:
                continue
            name = kind if len(packs) == 1 else f"{pack.name}-{kind}"
            required.append(name)
            only = ", ".join(f'"{item}"' for item in pack.patterns)
            tables += ["", f"[checks.{name}]", f'command = "{command}"', f"only_when = [{only}]"]
    return required, tables


def first_config(root: Path, choice: Choice = Choice()) -> str:
    """The first akasha.toml: the person who sets up Akasha is the administrator, and the usual commands of each
    language of the repository are the checks. The administrator corrects them before the merge."""
    me = repo.me(root) if repo.origin(root) else ""
    packs = langs.chosen(root, choice.stack)
    pack = packs[0] if packs else None
    admins = f'"{me}"' if me else ""
    folder = config.WORK_DIR                                     # Claude Code enters a work copy there without asking
    lines = ["# The team rules of Akasha. An administrator changes them with a pull request.", "",
             "[team]", f"admins = [{admins}]          # GitHub names: they set up and maintain Akasha, and help when "
             "the AI is stuck",
             "own_procedure = []      # GitHub names that keep the own procedure of the repository outside Akasha",
             f'version = "{VERSION}"' + " " * max(1, 24 - len(f'version = "{VERSION}"')) + "# the Akasha of the team: "
             "each computer, the CI, and the watch run only this version. An administrator changes it", "",
             "[risk]"]
    # The standard of a new repository is not for a task to change: the structure guide, and the rules of the lint
    kept = [ARCHITECTURE, *(item for each in packs for item in each.rules)] if choice.new else []
    lines += ["paths = [" + ", ".join(f'"{item}"' for item in kept) + "]" + " " * (3 if kept else 14)
              + '# for example ["db/**", "deploy/**"]: only an administrator changes them', "", "[checks]"]
    named, tables = _checks(packs)
    lines.append("required = [" + ", ".join(f'"{name}"' for name in ["secrets", *named]) + "]")
    if pack and pack.setup:
        lines.append(f'# setup = "{pack.setup}"    # prepares each new work copy, and runs in the check of Akasha')
    lines += tables
    lines += ["", "[ci]", '# required = ["build"]   # the checks of your own CI that GitHub must see pass, beside '
              "the check of Akasha", "", "[guides]",
              '# preview = ["docs/design.md"]       # team files that the AI reads before the preview']
    if choice.new:
        lines += [f'plan = ["{ARCHITECTURE}"]      # the AI reads the structure guide before each plan',
                  f'review = ["{ARCHITECTURE}"]    # and the AI that checks the plan judges the plan against it', "",
                  "[definitions]",
                  "on = true               # each business value and each feature for the outside has one "
                  "meaning: akasha.definitions.toml", ""]
        entries = ", ".join(f'"{choice.areas}/{name}"' for name in choice.entries)
        if choice.areas and choice.entries:
            lines += ["[core]", f'areas = ["{choice.areas}"]', "", "[boundaries.areas]",
                      f'private = ["{choice.areas}/**"]   # the files of an area', f"public = [{entries}]"
                      "   # are open to the outside only through these entries", ""]
        else:
            lines += ["# Answer with the administrator: which folder is one area, and which file is its entry? Then",
                      '# [core]', '# areas = ["domains/*"]', "# [boundaries.areas]",
                      '# private = ["domains/*/**"]', '# public = ["domains/*/api.py"]', ""]
        lines += ['# [pins]', '# policy = "all"        # each version of a library and of a base image is fixed, '
                  "once the package tool is chosen", ""]
    else:
        lines += ['# plan = ["docs/architecture.md"]    # ... before the plan, and the AI that checks the plan '
                  "reads them too", ""]
    if not choice.new:
        lines += ["# The map of the product. Name the folder of one area, then run `akasha map --draft` in this task: "
                  "it writes a", "# sheet (area.toml) for each area, and new code then goes into the area that keeps "
                  "that work.", '# [core]', '# areas = ["domains/*"]', "# [boundaries.areas]",
                  '# private = ["domains/*/**"]', '# public = ["domains/*/api.py"]', ""]
    lines += [
        "[size]", f"function = {config.SIZE_FUNCTION}          # lines of one function that a change makes or makes "
        "longer. 0: no limit",
        f"file = {config.SIZE_FILE}              # lines of one file of code: a longer file does not grow",
        f"task = {config.SIZE_TASK}             # lines of code that one task changes: a larger change goes in "
        "parts", "",
        "# [ops]                  # what a change needs to go live safely (the check ops)",
        '# migrations = ["db/migrations/**"]   # a new line there that removes a table or a column fails',
        '# env = [".env.example"]              # a new setting that this file does not name fails', "",
        "# [models]               # the model of each agent, when the team chooses one",
        '# work = "sonnet"        # akasha-worker: the preview, the plan, and the build',
        '# review = "opus"        # akasha-reviewer: never weaker than the worker', ""]
    lines += [
        "[work]", f'folder = "{folder}"' + " " * max(1, 22 - len(folder)) + "# the work copies of the tasks: a "
        "folder that git ignores",
        f'branch_prefix = "{config.BRANCH_PREFIX}"',
        f'records = "{config.RECORDS_DIR}"     # the records of a task in work: the preview, the plan, the '
        "summary. They are in the branch of the task",
        f'archive = "{config.ARCHIVE_DIR}"   # the landing moves the records of a merged task here, and they go '
        "into git. Choose both folders now: Akasha refuses a later change. The own checkers of the team skip "
        "them", ""]
    return "\n".join(lines)


def _ignored(root: Path, path: str) -> bool:
    return repo.git(root, "check-ignore", "-q", path).returncode == 0


def _ignore(root: Path, team: config.Team) -> bool:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    made = [line for pack in langs.detect(root) for line in pack.ignore]     # the files that tests and builds make
    wanted = list(dict.fromkeys([f"{STATE_DIR.as_posix()}/", f"{team.work_dir}/", *PERSONAL, *made]))
    missing = [line for line in wanted if line not in text.splitlines()
               and not (line.endswith("/") and _ignored(root, f"{line}x"))]      # the team ignores it already
    if missing:
        path.write_text(text.rstrip("\n") + ("\n" if text.strip() else "") + "\n".join(missing) + "\n",
                        encoding="utf-8")
    return bool(missing)


def record_notes(root: Path, team: config.Team) -> list[str]:
    """What stops the records of the tasks in this repository, with the fix: a rule of .gitignore that hides them
    from git, and a build of Docker that takes them in."""
    found = []
    for key, folder in (("records", team.records_dir), ("archive", team.archive_dir)):
        if _ignored(root, f"{folder}/a-task/plan.md"):
            found.append(f".gitignore hides [work] {key} ({folder}) from git, so the records of the tasks would not "
                         f"go into git. Add the line `!/{folder}/` after the rule that hides it (git names the rule: "
                         f"git check-ignore -v {folder}/a-task/plan.md), or choose another folder")
    ignore = root / ".dockerignore"
    if ignore.is_file():
        lines = {line.strip().strip("/") for line in ignore.read_text(encoding="utf-8", errors="replace").splitlines()}
        tops = {folder.split("/")[0] for folder in (team.records_dir, team.archive_dir, STATE_DIR.as_posix())}
        missing = sorted(top for top in tops if top not in lines and f"{top}/**" not in lines)
        if missing:
            found.append(f"note: .dockerignore does not leave out {', '.join(missing)}, so a build that copies the "
                         "repository takes the records of the tasks and the state of Akasha into the image. Add "
                         + ", ".join(f"`{top}/`" for top in missing))
    return found


def _archive_ignore(root: Path, team: config.Team) -> bool:
    """Write <archive>/.ignore once: a search tool that reads .ignore files (ripgrep) skips the archive in a
    checkout that holds it, for example where a person turned the sparse rules off. Only the setup makes this file:
    a file that each landing changed would make the landings of one day conflict. True when it wrote it."""
    name = f"{team.archive_dir}/.ignore"
    if repo.git(root, "cat-file", "-e", f"HEAD:{name}").returncode == 0 or (root / name).is_file():
        return False
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text("# Akasha: the records of merged tasks are no input of a new task\n*\n", encoding="utf-8")
    if repo.git(root, "add", "--sparse", "--", name).returncode:      # the checkout can leave the archive out
        repo.git(root, "add", "--", name)
    return True


def _standard(root: Path, choice: Choice) -> list[str]:
    """The files of a repository that starts now: the empty list of the definitions, with a correct first example
    in its head, and the structure guide from its template. The AI writes no sentence of the guide: the rules are
    fixed text, and the administrator answers the blanks. Return the files that it wrote."""
    from akasha import definitions
    wrote = []
    listed = definitions.place(root)
    if not listed.is_file():
        listed.write_text(definitions.HEAD, encoding="utf-8")
        wrote.append(listed.relative_to(root).as_posix())
    guide = root / ARCHITECTURE
    if not guide.is_file():
        card = (TEMPLATES / "structure.md").read_text(encoding="utf-8")
        rules = card.split("\n\n", 2)[2].split("\n\nSources:")[0]
        entries = ", ".join(f"`{choice.areas}/{name}`" for name in choice.entries)
        text = (TEMPLATES / "architecture.md").read_text(encoding="utf-8").format(
            card=rules, areas=f"`{choice.areas}`" if choice.areas else "TODO", entries=entries or "TODO")
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text(text, encoding="utf-8")
        wrote.append(ARCHITECTURE)
    return wrote


def open_answers(root: Path) -> int:
    """The blanks of the structure guide that still wait for an administrator."""
    try:
        return (root / ARCHITECTURE).read_text(encoding="utf-8", errors="replace").count("TODO")
    except OSError:
        return 0


def write_files(root: Path, choice: Choice = Choice()) -> list[str]:
    """Write the files of Akasha into the checkout, at the version of the team. Return the files that changed, and the
    problems. Only an empty version takes this Akasha: an administrator changes the version of the team by hand."""
    changed = []
    path = config.place(root)
    if not path.is_file():
        path.write_text(first_config(root, choice), encoding="utf-8")
        changed.append(path.relative_to(root).as_posix())
        if choice.new:
            changed += _standard(root, choice)
    elif choice.new or choice.stack:
        raise ValueError(f"{path.name} is there already: --new and --stack are for the first setup. Change the "
                         "rules of the team in a task of an administrator")
    team = config.load(root)
    if not team.version:                    # an akasha.toml of Akasha 1.1.2 or older: this Akasha is the first pin
        config.set_value(root, "team", "version", VERSION)
        changed += [] if changed else [path.relative_to(root).as_posix()]
        team = config.load(root)
    if _ignore(root, team):
        changed.append(".gitignore")
    if _archive_ignore(root, team):
        changed.append(f"{team.archive_dir}/.ignore")
    for name, text in github.workflows(team).items():
        target = root / name
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            changed.append(name)
    for name in github.leftovers(team):
        target = root / name
        if target.is_file() and target.read_text(encoding="utf-8").startswith("# Akasha installs"):
            target.unlink()
            changed.append(f"{name} (removed: the team does not need it now)")
    return changed + codex.write(root, team.version) + claude.write(root, team.version)


def run(root: Path, apply: bool = False, choice: Choice = Choice()) -> list[str]:
    branch = repo.default_branch(root)
    if repo.origin(root) and not config.place(root).is_file():
        repo.fetch(root, branch)
        if config.on_server(root, branch):
            return [f"{branch} on the server already uses Akasha. Do not set it up again: pull it, git pull origin "
                    f"{branch}"]
    report = []
    # Before any file: a version without a release tag cannot install on the CI (once, also when write_files runs twice)
    wanted = (config.load(root).version if config.place(root).is_file() else "") or VERSION
    problem = version.release_problem(root, wanted) if repo.origin(root) else ""
    if problem:
        raise ValueError(problem)
    if apply:
        rules, problems = github.apply(root)
        report.append(f"GitHub: server rules {rules}. " + ("GitHub stops a merge before the checks pass."
                      if rules == "github" else "GitHub cannot protect the default branch on this plan: Akasha "
                      "merges after the checks on each computer, and the watch reports a change that went around "
                      "them. For protection before each merge, move to GitHub Pro or Team, or make the repository "
                      "public, then run `akasha setup --apply` again."))
        report += [f"GitHub: {item}" for item in problems]
    first = not config.place(root).is_file()
    changed = write_files(root, choice)
    if first and choice.new:
        report += _new_notes(root, choice)
    if not apply and repo.origin(root) and config.load(root).server_rules != "akasha" and \
            github.protected(root, config.load(root)) is False:
        # Until an administrator turns the protection on, nothing on GitHub stops a merge: Akasha and the watch do
        config.set_server_rules(root, "akasha")
        changed = list(dict.fromkeys(changed + [config.place(root).relative_to(root).as_posix()] + write_files(root)))
        report.append(f"GitHub does not protect {branch} now, so Akasha merges after its own examination, and the "
                      "watch reports a change that went around it. `akasha setup --apply` turns the protection on "
                      "where the plan of GitHub allows it.")
    report += [f"wrote {name}" for name in changed] or ["the files of Akasha are up to date"]
    report += record_notes(root, config.load(root))
    team = config.load(root)
    if not team.pins_policy:                          # an administrator answers once: [pins] policy
        found = pin_listings(root, team)
        if any(item.floating or item.unread for item in found):
            report += [f"versions — {item.line}" for item in found]
            report.append("versions — nothing fixes these versions: the same commit can install other things "
                          "on another day, and a deployment that goes back installs other versions than "
                          "before. Ask the administrator, and write the answer into akasha.toml: [pins] policy "
                          "= \"observe\" (known, and left), \"new\" (what is there stays, and no change adds "
                          "more), or \"all\" (each one is fixed; a raise of a version is then a task). A "
                          "library that others install keeps its ranges: choose \"observe\" there")
    note = work.leave_out(repo.main_root(root) or root, config.load(root).archive_dir)
    report += [note] if note else []
    if wanted != VERSION:
        report.append(f"The team uses Akasha {wanted}, and this computer runs {VERSION}: the files pin {wanted}, and "
                      f"the workflows and the agent instructions (AGENTS.md, CLAUDE.md, .codex/hooks.json) come from "
                      f"{VERSION}. After the merge each computer moves to {wanted}. When `akasha doctor` then names old "
                      "server rules, run `akasha setup` again in a task.")
    main = repo.main_root(root)
    in_task = main is not None and any(task.workcopy and Path(task.workcopy).resolve() == root.resolve()
                                       for task in all_local(main))
    if changed and in_task:
        report.append("Next: these files are in the work copy of the task. Run `akasha check <task>`, then land it.")
    elif changed:
        report.append(NEXT_STEPS if not apply else "Next: commit these files on a new branch, open a pull request, "
                      "wait for its checks, and merge it.")
    return report


def pin_listings(root: Path, team: config.Team) -> list:
    """The lists of libraries and the Dockerfiles of the checkout, with what floats in each (pins.py)."""
    from akasha import pins

    def read(path: str) -> str | None:
        try:
            return (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    return pins.observe(repo.paths(root, team.record_roots + (team.work_dir,), others=True), read)


def _new_notes(root: Path, choice: Choice) -> list[str]:
    """What the administrator of a repository that starts now still answers."""
    packs = langs.chosen(root, choice.stack)
    notes = [f"new — {ARCHITECTURE} holds the rules of the structure and {open_answers(root)} blanks (TODO). Ask "
             "the administrator each one, and write the answers there: the AI writes no rule of its own. Only an "
             "administrator changes this file later"]
    if not (choice.areas and choice.entries):
        notes.append("new — the boundaries are not on yet: answer which folder is one area and which file is its "
                     "entry ([core] areas, [boundaries.areas]), or run the setup with --areas and --entries")
    if any(pack.name == "typescript" for pack in packs):
        notes.append("new — the lint of TypeScript needs a config of ESLint in the repository. Propose to the "
                     "administrator: @typescript-eslint/naming-convention, react/jsx-handler-names, and "
                     "complexity, in eslint.config.*")
    if any(pack.name == "python" for pack in packs):
        notes.append("new — the lint of Python is `ruff check --extend-select N` (the names). Ask whether the "
                     "team also wants the rule of complexity (C901): its limit is of the team, in ruff.toml")
    if not packs:
        notes.append("new — Akasha found no language. Name it: `akasha setup --new --stack python,typescript`, "
                     "else the repository starts without a test and a lint as required checks")
    notes.append("new — the first task that adds a library also adds the lock of its package tool. Propose "
                 "[pins] policy = \"all\" once the tool is chosen")
    return notes


def _tool(command: str) -> str:
    """The program of a command line, for example npm in `npm ci && npm run build`."""
    try:
        words = shlex.split(command.split("&&")[0])
    except ValueError:
        words = command.split()
    return words[0] if words else ""


def _python() -> tuple[bool, str]:
    """The Python that the hooks use. In the plugin, the hooks find it with hook.sh, which can differ from this one."""
    if not HOOK_SCRIPT.is_file():
        return sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} (Akasha needs 3.11 or higher)"
    try:
        done = subprocess.run(["sh", str(HOOK_SCRIPT), "--python"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False, "sh, which runs the hooks (install Git; on Windows it brings Git Bash)"
    found = done.stdout.strip()
    return done.returncode == 0, (f"Python for the hooks: {found}" if done.returncode == 0 else
                                  "Python 3.11 or higher for the hooks (install it so that `py -3`, `python3`, or "
                                  "`python` finds it, then restart the agent app)")


def _check_ready(root: Path, name: str, check: config.Check | None, guide: bool) -> tuple[bool, str] | None:
    """Whether this computer can run a check of the team: its `ready` command passes, else its program is there."""
    where = " (follow [guides] join of akasha.toml)" if guide else ""
    if check and check.ready:
        status, detail = checks.shell(check.ready, root / check.cwd)
        last = detail.strip().splitlines()[-1][:120] if status != "PASS" and detail.strip() else ""
        return status == "PASS", f"the check {name} can run here{where}" + (f": {last}" if last else "")
    program = _tool(checks.command(check)) if check else ""
    if program and program not in (".", "./") and not program.startswith(("./", ".\\")):
        return _runs(program), f"the program {program} of the check {name}{where}"
    return None


def _runs(program: str) -> bool:
    """True when the program is on PATH, and a Python also answers `--version`: the shortcut of the Microsoft Store
    named python is on PATH, but does not run. (`npm` is npm.cmd on Windows, and `go` has no `--version`.)"""
    found = shutil.which(program)
    if not found or Path(program).stem.lower() not in ("python", "python3", "py"):
        return bool(found)
    try:
        return subprocess.run([found, "--version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _hook_programs(root: Path) -> list[str]:
    """The programs that the own hooks of the repository run first, for example python or node."""
    try:
        data = json.loads((root / claude.SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = []
    for groups in (data.get("hooks") or {}).values() if isinstance(data, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
                program = _tool(str(hook.get("command") or "")) if isinstance(hook, dict) else ""
                if re.fullmatch(r"[A-Za-z][\w.-]*", program) and program not in ("sh", "bash", "echo", "cd"):
                    found.append(program)
    return list(dict.fromkeys(found))


def doctor(root: Path) -> list[tuple[bool, str]]:
    """What this person needs to work with Akasha in this repository, with the fix of each problem."""
    found: list[tuple[bool, str]] = [_python()]
    found.append((bool(shutil.which("git")), "git (install Git)"))
    named = repo.git(root, "config", "user.name").stdout.strip() and repo.git(root, "config", "user.email").stdout.strip()
    found.append((bool(named), "the name and the e-mail of git (git config --global user.name / user.email)"))
    has_gh = bool(shutil.which("gh"))
    found.append((has_gh, "GitHub CLI gh (install it: https://cli.github.com)"))
    slug = repo.origin(root)
    found.append((bool(slug), f"origin on GitHub ({slug or 'not GitHub'})"))
    if has_gh and slug:
        me = repo.me(root)
        found.append((bool(me), f"GitHub login ({me or 'run: gh auth login'})"))
        push = bool((github.repository(root).get("permissions") or {}).get("push"))
        found.append((push, "write access to the repository (else an administrator adds you as a collaborator)"))
    branch = repo.default_branch(root)
    if slug:
        fetched = repo.fetch(root, branch)
        error = fetched.stderr.strip().splitlines()[-1][:160] if fetched.returncode and fetched.stderr.strip() else ""
        found.append((fetched.returncode == 0, f"git can read {branch} from origin" + (
            f" ({error}; a login problem: gh auth setup-git; a certificate problem: see [guides] join)" if error
            else "")))
    found += [(_runs(program), f"the program {program} that the own hooks of the repository run (install it, and put "
               "it first on PATH)") for program in _hook_programs(root)]
    if repo.git(root, "ls-files", "--error-unmatch", ".claude/settings.local.json").returncode == 0:
        found.append((False, "the personal settings .claude/settings.local.json are in git, so each teammate gets "
                             "them (an administrator removes them from git: git rm --cached)"))
    if not config.on_server(root, branch) and not config.place(root).is_file():
        found.append((False, f"{CONFIG_FILE} (an administrator sets up Akasha first: `akasha setup` writes it)"))
        return found
    try:
        team = config.shared(root, branch)
    except config.ConfigError as error:
        return found + [(False, f"{CONFIG_FILE}: {error}")]
    if team.version:
        found.append((not version.mismatch(team.version, root=root), version.mismatch(team.version, root=root) or
                      (f"Akasha {VERSION}, the version of the team" if team.version == VERSION else
                       f"Akasha {VERSION}, with the same rules as {team.version}, the version of the team")))
        if team.unknown and team.version == VERSION:
            found.append((False, f"{CONFIG_FILE} has {', '.join(team.unknown[:3])}, which Akasha {VERSION}, the "
                                 "version of the team, does not know (an administrator removes them, or raises "
                                 "[team] version)"))
    elif team.unknown:
        found.append((False, f"Akasha is older than {CONFIG_FILE}, which has {', '.join(team.unknown[:3])} (update "
                             "the plugin: /plugin marketplace update akasha, then /plugin update akasha@akasha)"))
    for name in team.required_checks:
        ready = _check_ready(root, name, team.checks.get(name), "join" in team.guides)
        found += [ready] if ready else []
    found += [(note.startswith("note:"), note) for note in record_notes(root, team)]
    main = repo.main_root(root) or root
    note = work.leave_out(main, team.archive_dir)     # a checkout that nobody set up leaves the archive out now
    if note:
        found.append((True, f"note: {note}"))
    elif not work.is_sparse(main) and repo.git(main, "cat-file", "-e", f"HEAD:{team.archive_dir}").returncode == 0:
        found.append((True, f"note: this checkout holds the archive of the merged tasks ({team.archive_dir}): each "
                            "search of a session finds their records. To leave it out: git sparse-checkout set "
                            f"--no-cone '/*' '!/{team.archive_dir}/'"))
    admin = bool(slug) and github.is_admin(root)
    if admin:
        problems = github.status(root)
        found += [(False, f"server: {item}") for item in problems] or [(True, "server rules of the team")]
    if slug and has_gh:                               # a notice, not a problem: each person sees what holds a merge
        guarded = github.protected(root, team)
        if guarded is True:
            found.append((True, f"GitHub stops a merge into {branch} before the checks of the team pass"))
        elif guarded is False:
            watch = ", and the watch reports a merge that went around them" if team.server_rules == "akasha" else ""
            found.append((True, f"note: GitHub does not protect {branch}. The rules hold for a merge through "
                                f"`akasha land`{watch}. Two computers that merge at the same moment can merge the "
                                "second task without its checks on the first: the line of the landings makes it "
                                "rare, and only the protection of GitHub stops it"))
    blanks = open_answers(root)
    if blanks and ARCHITECTURE in team.guides.get("plan", ()):
        found.append((True, f"note: {ARCHITECTURE} has {blanks} blanks (TODO) that wait for an administrator: "
                            "the AI follows the structure guide, and has nothing to follow there"))
    from akasha import report
    tracked = repo.paths(root, team.record_roots + (team.work_dir,))
    found += [(True, f"note: {line.removeprefix('observed — ')}") for line in report.unchecked(team, tracked)]
    if not team.pins_policy:                          # each person sees it, until an administrator answered
        from akasha import pins
        said = pins.notice(pin_listings(root, team))
        if said:
            found.append((True, f"note: {said}"))
    if admin and team.required_checks == ("secrets",):
        found.append((True, "note: the only required check is secrets. Put the tests, the lint, and the type check of "
                            f"the team in [checks] required of {CONFIG_FILE}: then each person and each agent engine "
                            "runs the same checks, on the computer and on the server"))
    return found + product_notes(root, team, tracked)


def product_notes(root: Path, team: Team, tracked: list[str]) -> list[tuple[bool, str]]:
    """What the checks of the product cannot hold yet in this repository (product.py): a note for each one, with
    what an administrator does about it. They are notes: a team turns each rule on when it is ready."""
    from akasha import githooks, hooks, sheets
    found = [(True, said if on else f"note: {said}") for on, said in githooks.state(root, hooks.command())]
    notes = []
    if not team.core_areas:
        notes.append(f"the product has no map: {CONFIG_FILE} names no areas. Name the folder of one area ([core] "
                     "areas, for example \"domains/*\"), then run `akasha map --draft` in a task: new code then goes "
                     "into the area that keeps that work")
    elif not sheets.drawn(team, tracked):
        notes.append("the map of the product is not drawn: no area has a sheet (area.toml). An administrator runs "
                     "`akasha map --draft` in a task and corrects each purpose")
    if team.core_areas and not team.boundaries:
        notes.append("the areas have no boundary: any file imports any file of another area. Name the entry of an "
                     "area in [boundaries.areas] (private, public)")
    real = [name for name in team.required_checks if name in team.checks and team.checks[name].kind == "integration"]
    if team.data_paths and not real:
        notes.append("no required check runs against a real store: a change of the files of [preview] data is proven "
                     "only by tests that never run its queries. Mark such a check with kind = \"integration\" in "
                     "[checks.<name>]")
    if team.deploy_workflow and not team.deploy_verify:
        notes.append("nothing examines the product after a deployment: [deploy] verify is a command that passes when "
                     "the change works live, for example a request to the health address")
    if not (team.size_function or team.size_file or team.size_task):
        notes.append("each limit of [size] is off: a function, a file, and a task can grow without a signal")
    return found + [(True, f"note: {said}") for said in notes]
