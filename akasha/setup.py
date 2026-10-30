"""Set up Akasha in a repository: the team config, the files that Codex reads, and the GitHub settings."""

from __future__ import annotations

from pathlib import Path

from akasha import config
from akasha.engine import codex
from akasha.infra import github
from akasha.validators import langs

IGNORED = (".akasha/state/", ".akasha/work/")
PRODUCT_MAP = """# Product map

Akasha keeps this map. The agent engine reads it before each impact analysis and updates it before each handover.
Write one section for each feature, in Simplified Technical English.

<!-- The section of one feature:
## <Feature name>
- Purpose: what the feature does for the user
- Screens: the screens or commands that show the feature
- Data: the tables, columns, or files that the feature reads or writes
- APIs: the endpoints or functions that other features use
- Depends on: the features that this feature uses
-->
"""


def _team_config(root: Path) -> str:
    packs = langs.detect(root)
    lines = ["# The team rules of Akasha. Change them with the approval of an administrator.",
             "[roles]", 'developers = []', 'administrators = []', "",
             "[risk]", 'high = ["**/migrations/**", "**/auth/**", "**/payments/**"]', 'medium = ["**/api/**"]', "",
             "# The agent engine makes the technical decisions. To add a person gate for a risk level, remove the #.",
             "[approval]", '# high = ["developer"]', "",
             "[checks]"]
    required = ["secrets"] + (["tests"] if packs and packs[0].tests else [])
    lines.append("required = [" + ", ".join(f'"{name}"' for name in required) + "]")
    if packs and packs[0].setup:
        lines.append(f'# setup = "{packs[0].setup}"    # installs the dependencies in a work copy and in CI')
    if packs and packs[0].tests:
        lines.append(f'tests = "{packs[0].tests}"')
    if packs and packs[0].lint:
        lines.append(f'lint = "{packs[0].lint}"')
    lines += ["", "[preview]", '# command = "npm run dev -- --port {port}"', 'database = "app_{task}"']
    return "\n".join(lines) + "\n"


def run(root: Path, approved_by: str) -> list[str]:
    report = []
    path = root / config.CONFIG_FILE
    if path.is_file():
        report.append(f"{config.CONFIG_FILE} is present. Akasha keeps it.")
    else:
        path.write_text(_team_config(root), encoding="utf-8")
        report.append(f"Akasha wrote {config.CONFIG_FILE}. Ask the team for the roles and the high-risk areas.")
    config.load(root)                                    # stop here if the team config is not correct
    product_map = root / config.PRODUCT_MAP
    if not product_map.is_file():
        product_map.parent.mkdir(parents=True, exist_ok=True)
        product_map.write_text(PRODUCT_MAP, encoding="utf-8")
        report.append(f"Akasha wrote {config.PRODUCT_MAP.as_posix()}. The agent engine fills it during the tasks.")
    ignore = root / ".gitignore"
    present = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    missing = [line for line in IGNORED if line not in present.splitlines()]
    if missing:
        ignore.write_text(present.rstrip("\n") + ("\n" if present.strip() else "") + "\n".join(missing) + "\n",
                          encoding="utf-8")
    report.append("Akasha wrote " + ", ".join(codex.write(root)) + ". Codex needs Akasha installed with pip.")
    if approved_by:
        problems = github.apply(root, approved_by)
        report += [f"GitHub: {item}" for item in problems] or ["GitHub settings agree with akasha.toml."]
    else:
        report += [f"GitHub: {item}" for item in github.status(root)]
        report.append("To change the GitHub settings, an administrator must approve. "
                      "Then run setup again with --approve-infra <administrator>.")
    return report
