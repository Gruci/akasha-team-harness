"""The setup of a repository by an administrator, and the readiness of each person (doctor)."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from akasha import checks, claude, codex, config, github, langs, repo
from akasha.config import CONFIG_FILE, STATE_DIR
from akasha.task import all_local

NEXT_STEPS = ("Next: answer the questions of the setup in akasha.toml and run `akasha setup` again. An administrator "
              "of the GitHub repository runs `akasha setup --apply` on their computer. Then commit these files on a "
              "new branch, open a pull request, wait for its checks, and merge it.")
HOOK_SCRIPT = Path(__file__).resolve().parents[1] / "hook.sh"      # in the plugin: the hooks find Python with it
PERSONAL = (".claude/settings.local.json", "CLAUDE.local.md")      # the own agent settings of each person: not in git


def first_config(root: Path) -> str:
    """The first akasha.toml: the person who sets up Akasha is the administrator, and the usual commands of the main
    language of the repository are the checks. The administrator corrects them before the merge."""
    me = repo.me(root) if repo.origin(root) else ""
    packs = langs.detect(root)
    pack = packs[0] if packs else None
    admins = f'"{me}"' if me else ""
    folder = "worktrees" if _ignored(root, "worktrees/x") else config.WORK_DIR     # a worktree folder of the team
    lines = ["# The team rules of Akasha. An administrator changes them with a pull request.", "",
             "[team]", f"admins = [{admins}]          # GitHub names: they set up and maintain Akasha, and help when "
             "the AI is stuck",
             "own_procedure = []      # GitHub names that keep the own procedure of the repository outside Akasha", "",
             "[risk]", 'paths = []              # for example ["db/**", "deploy/**"]: only an administrator changes '
             "them", "",
             "[checks]"]
    required = ["secrets"] + (["tests"] if pack and pack.tests else [])
    lines.append("required = [" + ", ".join(f'"{name}"' for name in required) + "]")
    if pack and pack.setup:
        lines.append(f'# setup = "{pack.setup}"    # prepares each new work copy, and runs in the check of Akasha')
    if pack and pack.tests:
        lines += ["", "[checks.tests]", f'command = "{pack.tests}"']
    lines += ["", "[ci]", '# required = ["build"]   # the checks of your own CI that GitHub must see pass. Without it, '
              "Akasha adds its own check", "", "[guides]",
              '# preview = ["docs/design.md"]       # team files that the AI reads before the preview',
              '# plan = ["docs/architecture.md"]    # ... before the plan, and the AI that checks the plan reads them '
              "too", "",
              "[work]", f'folder = "{folder}"' + " " * max(1, 22 - len(folder)) + "# the work copies of the tasks: a "
              "folder that git ignores",
              f'branch_prefix = "{config.BRANCH_PREFIX}"',
              f'records = "{config.RECORDS_DIR}"     # the preview, the plan, and the summary of each task go into git '
              "here: choose a folder that the own checkers of the team skip", ""]
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


def write_files(root: Path) -> list[str]:
    """Write the files of Akasha into the checkout. Return the files that changed, and the problems."""
    changed = []
    path = config.place(root)
    if not path.is_file():
        path.write_text(first_config(root), encoding="utf-8")
        changed.append(path.relative_to(root).as_posix())
    team = config.load(root)
    if _ignore(root, team):
        changed.append(".gitignore")
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
    return changed + codex.write(root) + claude.write(root)


def run(root: Path, apply: bool = False) -> list[str]:
    branch = repo.default_branch(root)
    if repo.origin(root) and not config.place(root).is_file():
        repo.fetch(root, branch)
        if config.on_server(root, branch):
            return [f"{branch} on the server already uses Akasha. Do not set it up again: pull it, git pull origin "
                    f"{branch}"]
    report = []
    if apply:
        rules, problems = github.apply(root)
        report.append(f"GitHub: server rules {rules}. " + ("GitHub stops a merge before the checks pass."
                      if rules == "github" else "GitHub cannot protect the default branch on this plan: Akasha "
                      "merges after the checks on each computer, and the watch reports a change that went around "
                      "them. For protection before each merge, move to GitHub Pro or Team, or make the repository "
                      "public, then run `akasha setup --apply` again."))
        report += [f"GitHub: {item}" for item in problems]
    changed = write_files(root)
    if not apply and repo.origin(root) and config.load(root).server_rules != "akasha" and \
            github.protected(root, config.load(root)) is False:
        # Until an administrator turns the protection on, nothing on GitHub stops a merge: Akasha and the watch do
        config.set_server_rules(root, "akasha")
        changed = list(dict.fromkeys(changed + [config.place(root).relative_to(root).as_posix()] + write_files(root)))
        report.append(f"GitHub does not protect {branch} now, so Akasha merges after its own examination, and the "
                      "watch reports a change that went around it. `akasha setup --apply` turns the protection on "
                      "where the plan of GitHub allows it.")
    report += [f"wrote {name}" for name in changed] or ["the files of Akasha are up to date"]
    main = repo.main_root(root)
    in_task = main is not None and any(task.workcopy and Path(task.workcopy).resolve() == root.resolve()
                                       for task in all_local(main))
    if changed and in_task:
        report.append("Next: these files are in the work copy of the task. Run `akasha check <task>`, then land it.")
    elif changed:
        report.append(NEXT_STEPS if not apply else "Next: commit these files on a new branch, open a pull request, "
                      "wait for its checks, and merge it.")
    return report


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
    if team.unknown:
        found.append((False, f"Akasha is older than {CONFIG_FILE}, which has {', '.join(team.unknown[:3])} (update "
                             "the plugin: /plugin marketplace update akasha, then /plugin update akasha@akasha)"))
    for name in team.required_checks:
        ready = _check_ready(root, name, team.checks.get(name), "join" in team.guides)
        found += [ready] if ready else []
    if slug and github.is_admin(root):
        problems = github.status(root)
        found += [(False, f"server: {item}") for item in problems] or [(True, "server rules of the team")]
    return found
