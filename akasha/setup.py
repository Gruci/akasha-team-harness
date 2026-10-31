"""The setup of a repository by an administrator, and the readiness of each person (doctor)."""

from __future__ import annotations

import shlex
import shutil
import sys
from pathlib import Path

from akasha import claude, codex, config, github, langs, repo
from akasha.config import CONFIG_FILE, STATE_DIR

NEXT_STEPS = ("Next: commit these files on a new branch, open a pull request, and merge it. Then, on the computer of "
              "an administrator of the GitHub repository, run `akasha setup --apply`.")


def first_config(root: Path) -> str:
    """The first akasha.toml: the person who sets up Akasha is the administrator, and the usual commands of the main
    language of the repository are the checks. The administrator corrects them before the merge."""
    me = repo.me(root) if repo.origin(root) else ""
    packs = langs.detect(root)
    pack = packs[0] if packs else None
    admins = f'"{me}"' if me else ""
    lines = ["# The team rules of Akasha. An administrator changes them with a pull request.", "",
             "[team]", f"admins = [{admins}]          # GitHub names: they set up GitHub and help when the AI is "
             "stuck",
             "reviewers = []          # GitHub names that review a change of a risky path", "",
             "[risk]", 'paths = []              # for example ["db/**", "**/migrations/**"]: a change waits for a '
             "reviewer", "",
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
              '# plan = ["docs/architecture.md"]    # ... before the plan, and the reviewer reads them too', ""]
    return "\n".join(lines)


def _ignore(root: Path, team: config.Team) -> bool:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    made = [line for pack in langs.detect(root) for line in pack.ignore]     # the files that tests and builds make
    wanted = list(dict.fromkeys([f"{STATE_DIR.as_posix()}/", f"{team.work_dir}/", *made]))
    missing = [line for line in wanted if line not in text.splitlines()]
    if missing:
        path.write_text(text.rstrip("\n") + ("\n" if text.strip() else "") + "\n".join(missing) + "\n",
                        encoding="utf-8")
    return bool(missing)


def _codeowners(root: Path, team: config.Team) -> str:
    if not (team.admins or team.reviewers):
        return ""
    path = next((root / name for name in github.CODEOWNERS_FILES if (root / name).is_file()),
                root / github.CODEOWNERS_FILES[0])
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    new = github.merge_block(old, github.codeowners(team))
    if new == old:
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
    return path.relative_to(root).as_posix()


def write_files(root: Path) -> list[str]:
    """Write the files of Akasha into the checkout. Return the files that changed, and the problems."""
    changed = []
    path = root / CONFIG_FILE
    if not path.is_file():
        path.write_text(first_config(root), encoding="utf-8")
        changed.append(CONFIG_FILE)
    team = config.load(root)
    if _ignore(root, team):
        changed.append(".gitignore")
    template = root / github.TEMPLATE_FILE
    if not template.is_file():
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text((github.TEMPLATES / "pull_request_template.md").read_text(encoding="utf-8"),
                            encoding="utf-8")
        changed.append(github.TEMPLATE_FILE)
    owners = _codeowners(root, team)
    changed += [owners] if owners else []
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
    if repo.origin(root) and not (root / CONFIG_FILE).is_file():
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
    report += [f"wrote {name}" for name in changed] or ["the files of Akasha are up to date"]
    if changed:
        report.append(NEXT_STEPS if not apply else "Next: commit these files on a new branch, open a pull request, "
                      "and merge it.")
    return report


def _tool(command: str) -> str:
    """The program of a command line, for example npm in `npm ci && npm run build`."""
    try:
        words = shlex.split(command.split("&&")[0])
    except ValueError:
        words = command.split()
    return words[0] if words else ""


def doctor(root: Path) -> list[tuple[bool, str]]:
    """What this person needs to work with Akasha in this repository, with the fix of each problem."""
    found: list[tuple[bool, str]] = []
    found.append((sys.version_info >= (3, 11), f"Python {sys.version.split()[0]} (Akasha needs 3.11 or higher)"))
    found.append((bool(shutil.which("git")), "git (install Git)"))
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
        repo.fetch(root, branch)
    if not config.on_server(root, branch) and not (root / CONFIG_FILE).is_file():
        found.append((False, f"{CONFIG_FILE} (an administrator sets up Akasha first)"))
        return found
    try:
        team = config.shared(root, branch)
    except config.ConfigError as error:
        return found + [(False, f"{CONFIG_FILE}: {error}")]
    for name in team.required_checks:
        check = team.checks.get(name)
        program = _tool(check.command) if check else ""
        if program and program not in (".", "./") and not program.startswith(("./", ".\\")):
            found.append((bool(shutil.which(program)), f"the program {program} of the check {name}"))
    if slug and github.is_admin(root):
        problems = github.status(root)
        found += [(False, f"server: {item}") for item in problems] or [(True, "server rules of the team")]
    return found
