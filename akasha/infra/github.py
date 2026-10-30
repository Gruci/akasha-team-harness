"""Read and change the repository settings on GitHub with the gh command."""

from __future__ import annotations

import json
from pathlib import Path

from akasha.core.workcopy import git
from akasha.infra import desired
from akasha.repo import gh


def repository(root: Path) -> tuple[str, str] | None:
    """(owner/name, default branch) of the GitHub repository, or None without GitHub."""
    viewed = gh(root, "repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    if viewed.returncode:
        return None
    data = json.loads(viewed.stdout)
    return data["nameWithOwner"], (data.get("defaultBranchRef") or {}).get("name") or "main"


def protection(root: Path, slug: str, branch: str) -> dict | None:
    read = gh(root, "api", f"repos/{slug}/branches/{branch}/protection")
    return json.loads(read.stdout) if read.returncode == 0 else None


def status(root: Path) -> list[str]:
    """The problems of the repository settings. An empty list means that the settings are correct."""
    found = repository(root)
    if found is None:
        return ["Akasha cannot read the GitHub repository — make sure that gh is installed and logged in"]
    slug, branch = found
    problems = desired.drift(protection(root, slug, branch))
    git(root, "fetch", "-q", "origin", branch)
    for target, text in desired.files(_team(root)).items():          # the server uses the default branch
        shown = git(root, "show", f"origin/{branch}:{target}")
        if shown.returncode or shown.stdout.replace("\r\n", "\n") != text:
            problems.append(f"{target} on {branch} is missing or different from akasha.toml")
    return problems


def apply(root: Path, approved_by: str) -> list[str]:
    """Write the repository files and set branch protection. An administrator must approve first."""
    team = _team(root)
    named = {person.lstrip("@") for person in team.administrators}
    if not approved_by or (named and approved_by.lstrip("@") not in named):
        raise PermissionError("an administrator that akasha.toml names must approve a change to the repository settings")
    for target, text in desired.files(team).items():
        path = root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    found = repository(root)
    if found is None:
        return ["Akasha wrote the files, but cannot reach GitHub to set branch protection"]
    slug, branch = found
    done = gh(root, "api", "--method", "PUT", f"repos/{slug}/branches/{branch}/protection", "--input", "-",
              payload=desired.protection())
    if done.returncode:
        return [f"GitHub refused the branch protection: {done.stderr.strip()[:300]}"]
    return []


def _team(root: Path):
    from akasha import config
    return config.load(root)
