"""The retro: what stops the work again and again. A repeated failure of the same kind is a rule that the team can
turn into a check, so that the AI meets it before the merge and not after it."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from akasha import repo, trace
from akasha.config import LABEL
from akasha.task import parse_block

MERGED_SHOWN = 50


def report(root: Path) -> list[str]:
    items = trace.read(root)
    lines = []
    checks = Counter(item.get("check", "") for item in items if item.get("kind") == "check_failed")
    blocks = Counter((item.get("reason") or "")[:90] for item in items if item.get("kind") == "blocked")
    server = Counter(name for item in items if item.get("kind") == "server_check_failed"
                     for name in item.get("checks") or [])
    if checks:
        lines.append("Failed checks on this computer: " + ", ".join(f"{name} {count}" for name, count in
                                                                     checks.most_common(5)))
    if server:
        lines.append("On this computer, failed on GitHub after they passed here: " + ", ".join(
            f"{name} {count}" for name, count in server.most_common(5)))
    if blocks:
        lines.append("Stopped actions on this computer: " + "; ".join(f"{count}× {reason}" for reason, count in
                                                                      blocks.most_common(5)))
    merged = repo.gh_json(root, "pr", "list", "--label", LABEL, "--state", "merged", "--limit", str(MERGED_SHOWN),
                          "--json", "body") if repo.origin(root) else None
    tasks = [task for item in merged or [] if (task := parse_block(item.get("body") or "")) is not None]
    if tasks:
        failures: Counter[str] = Counter()
        on_server: Counter[str] = Counter()
        for task in tasks:
            failures.update(task.stats.get("check_failures") or {})
            on_server.update(task.stats.get("server_check_failures") or {})
        rounds = [int(task.stats.get("review_rounds", 0)) for task in tasks if task.stats.get("review_rounds")]
        lines.append(f"The last {len(tasks)} merged tasks of the team: " + (", ".join(
            f"{name} failed {count}×" for name, count in failures.most_common(5)) or "no failed checks"))
        if on_server:
            lines.append("Of the team, failed on GitHub after they passed on a computer: " + ", ".join(
                f"{name} {count}×" for name, count in on_server.most_common(5)))
        if rounds:
            lines.append(f"Plan reviews: {sum(rounds) / len(rounds):.1f} rounds on average")
    return lines or ["Nothing repeats yet."]
