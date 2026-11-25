"""How far a task is, for the person who asked for it and for the team: four facts on four lines.

1. The stage: its number among the stages of the kind of the task, and its name. "The person's turn" when the task
   waits for an answer of the person; "repair N" while a repair runs.
2. The part done, in percent: each stage has a fixed part. The build is the longest one, so its part grows with
   each step of the plan that is done (steps.py), and the last part of it when the checks pass. A repair moves
   nothing; only a preview that changed after its approval moves the task back.
3. The time left: the minutes of each stage still to do. While this computer has fewer than MEASURED merged tasks
   of the same kind, the minutes are the defaults of STAGES; then the medians of those tasks. The wait for the
   person counts no minutes: nobody knows when they answer.
4. Where the task works: the areas of the files of its plan, and the step of the plan that the build does now.

`akasha status <task> --brief` shows the four lines, and the main session gives them to the person when the stage
changes. The pull request of the task shows the same at its top, and the board one line, from the snapshot in the
stats of the task (`progress`): the board of another person cannot read this work copy."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field

from akasha import usage
from akasha.task import Task

# For each kind: each stage with its part of the task in percent and its minutes by default. The parts add up to 100
STAGES = {
    "full": (("preview", 15, 20), ("approval", 5, 0), ("plan", 10, 15), ("review", 10, 10), ("build", 40, 40),
             ("result", 10, 10), ("merge", 5, 3), ("deploy", 5, 2)),
    "no-screen": (("plan", 25, 20), ("review", 15, 10), ("approval", 5, 0), ("build", 40, 40), ("result", 5, 10),
                  ("merge", 5, 3), ("deploy", 5, 2)),
    "quick": (("build", 50, 15), ("review", 20, 5), ("approval", 10, 0), ("merge", 10, 3), ("deploy", 10, 2)),
    "agent": (("plan", 15, 15), ("review", 10, 10), ("build", 40, 40), ("result", 15, 10), ("approval", 10, 0),
              ("merge", 5, 3), ("deploy", 5, 2)),
}
CHECKS_PART = 5                 # the last part of the build: the checks pass on the code of the task
FIX_MINUTES = 8                 # one repair, by default
MEASURED = 5                    # merged tasks of a kind on this computer before their medians replace the defaults
BAR = 10                        # the marks of the bar
WAITS = "approval"              # the stage where the task waits for the person
# The phases of the record of the usage that repair a stage, and the stage that they repair
REPAIRS = {"preview-fix": "preview", "plan-fix": "review", "check-fix": "build", "result-fix": "result",
           "land-fix": "merge"}


@dataclass
class Facts:
    """What Akasha knows of a task now, as plain values: `where` reads only these."""
    kind: str = "full"
    status: str = "preview"
    shown: bool = False          # the person sees the current version (the preview, or the plan of a task without a
                                 # screen) and did not answer yet
    approved: bool = False       # the approval holds for the current version
    plan_ready: bool = False     # the plan is written, with its notes: it waits for its review
    plan_passed: bool = False    # the review of the plan (of the change, for a quick task) passed this version
    checks_passed: bool = False  # the checks passed on the code of the task as it is now
    result_needed: bool = False
    result_passed: bool = False
    deploying: bool = False      # merged, and the deployment is not confirmed yet
    steps: tuple[int, int] = (0, 0)               # the steps of the plan that are done, and all of them
    repair: tuple[str, int] = ("", 0)             # the phase that repairs now (usage.py), and its number


@dataclass
class Progress:
    task: str
    stages: tuple[str, ...]
    stage: str                   # "" when the task is done
    state: str                   # work, person, repair, or done
    percent: int
    repair: int = 0
    steps: tuple[int, int] = (0, 0)
    left: int | None = None      # minutes, without the wait for the person
    basis: str = "default"       # "default", or how many merged tasks gave the medians
    spent: int | None = None     # minutes since the start of the task on this computer
    cost: float | None = None    # dollars at list prices
    areas: list[str] = field(default_factory=list)
    now: str = ""                # the step of the plan that the build does now: its id, title, and files
    outside: int = 0             # changed files of code that no step of the plan names


def stages_of(kind: str) -> tuple[tuple[str, int, int], ...]:
    return STAGES.get(kind, STAGES["full"])


def where(facts: Facts) -> tuple[str, str]:
    """The stage of a task and its state: work, person, repair, or done."""
    phase, _number = facts.repair
    if facts.status in ("merged", "closed"):
        return ("deploy", "work") if facts.deploying else ("", "done")
    if facts.status == "landing":
        return "merge", "repair" if phase == "land-fix" else "work"
    if facts.kind == "quick":
        if not facts.checks_passed:
            return "build", "repair" if phase == "check-fix" else "work"
        if not facts.plan_passed:
            return "review", "work"
        if not facts.approved:
            return WAITS, "person" if facts.shown else "work"
        return "merge", "work"
    plan_first = facts.kind in ("no-screen", "agent")
    if not plan_first and not facts.approved:
        if facts.shown:
            return WAITS, "person"
        return "preview", "repair" if phase == "preview-fix" else "work"
    if not facts.plan_passed:
        if phase == "plan-fix":
            return "review", "repair"
        return ("review" if facts.plan_ready else "plan"), "work"
    if facts.kind == "no-screen" and not facts.approved:
        return WAITS, "person" if facts.shown else "work"
    if phase == "result-fix":
        return "result", "repair"
    if not facts.checks_passed:
        return "build", "repair" if phase == "check-fix" else "work"
    if facts.result_needed and not facts.result_passed:
        return "result", "work"
    if facts.kind == "agent" and not facts.approved:
        return WAITS, "person" if facts.shown else "work"
    return "merge", "work"


def percent(facts: Facts, stage: str) -> int:
    """The part of the task that is done: the parts of the stages before this one, and the part of the build that
    its steps and its checks did."""
    if not stage:
        return 100
    done = 0
    for name, part, _minutes in stages_of(facts.kind):
        if name == stage:
            if name == "build":
                finished, total = facts.steps
                done += round((part - CHECKS_PART) * finished / total) if total else 0
                done += CHECKS_PART if facts.checks_passed else 0
            break
        done += part
    return min(done, 99)


def minutes_left(facts: Facts, stage: str, state: str, minutes: dict[str, float]) -> int | None:
    """The minutes of the stages still to do, without the wait for the person. None when the task is done."""
    if not stage:
        return None
    names = [name for name, _part, _minutes in stages_of(facts.kind)]
    total = 0.0
    for name in names[names.index(stage):]:
        if name == WAITS:
            continue
        each = minutes.get(name, 0)
        if name == stage and name == "build" and facts.steps[1]:
            each *= 1 - facts.steps[0] / facts.steps[1]
        total += each
    if state == "repair":
        total += minutes.get("fix", FIX_MINUTES)
    return max(round(total), 1)


def _events(lines: list[dict]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for line in lines:
        if line.get("kind") == "event" and line.get("key"):
            found.setdefault(str(line["key"]), []).append(line)
    return {key: sorted(events, key=lambda line: float(line.get("at") or 0)) for key, events in found.items()}


def _first(events: list[dict], what: str, **match: str) -> float:
    return next((float(line.get("at") or 0) for line in events if line.get("what") == what
                 and all(line.get(name) == value for name, value in match.items())), 0.0)


def measured(lines: list[dict], kind: str) -> tuple[dict[str, float], int]:
    """The minutes of each stage: the medians of the merged tasks of this kind in the record of this computer, when
    it has MEASURED of them, else the defaults. Also how many tasks gave the medians (0: the defaults). A span that
    holds two stages is shared by the parts of their defaults."""
    defaults = {name: float(minutes) for name, _part, minutes in stages_of(kind)}
    defaults["fix"] = float(FIX_MINUTES)
    spans: dict[str, list[float]] = {}
    tasks = 0
    for events in _events(lines).values():
        start, merged = _first(events, "start"), _first(events, "merged")
        if not start or not merged or next((line.get("task_kind") for line in events if line.get("task_kind")),
                                           "full") != kind:
            continue
        tasks += 1
        approved, shown, landing = _first(events, "approved"), _first(events, "shown"), _first(events, "landing")
        passed = _first(events, "verdict", subject="plan", verdict="PASS")
        done = _first(events, "verdict", subject="result", verdict="PASS")
        for name, begin, end in (("preview", start, shown), ("plan+review", approved, passed),
                                 ("build+result", passed, done), ("merge", landing, merged)):
            if begin and end > begin:
                spans.setdefault(name, []).append((end - begin) / 60)
    if tasks < MEASURED:
        return defaults, 0
    found = dict(defaults)
    for name, values in spans.items():
        middle = statistics.median(values)
        parts = name.split("+")
        whole = sum(defaults.get(part, 0) for part in parts) or 1
        for part in parts:
            found[part] = middle * defaults.get(part, 0) / whole
    return found, tasks


def build(task: Task, facts: Facts, lines: list[dict], areas: list[str] | None = None, now: str = "",
          outside: int = 0, cost: float | None = None) -> Progress:
    """The progress of a task from its facts and the record of the usage of this computer."""
    stage, state = where(facts)
    minutes, tasks = measured(lines, facts.kind)
    events = _events(lines).get(usage.key(task), [])
    # A task that an Akasha before 2.0.4 started has no event of its start: its first event stands in
    begun = _first(events, "start") or (float(events[0].get("at") or 0) if events else 0.0)
    return Progress(task.id, tuple(name for name, _part, _minutes in stages_of(facts.kind)), stage, state,
                    percent(facts, stage), facts.repair[1] if state == "repair" else 0, facts.steps,
                    minutes_left(facts, stage, state, minutes), f"{tasks} merged tasks" if tasks else "default",
                    round((time.time() - begun) / 60) if begun else None, cost, areas or [], now, outside)


def _duration(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def _bar(value: int) -> str:
    full = round(value * BAR / 100)
    return "▰" * full + "▱" * (BAR - full)


def _stage_line(found: Progress) -> str:
    marks = []
    for name in found.stages:
        if not found.stage or found.stages.index(name) < found.stages.index(found.stage):
            marks.append(f"✓{name}")
        elif name == found.stage:
            marks.append(("↻" if found.state == "repair" else "◉") + name)
        else:
            marks.append(f"○{name}")
    return " ".join(marks)


def headline(found: Progress) -> str:
    """The stage in one phrase: `stage 5/8 build (plan steps 3/5 done)`."""
    if not found.stage:
        return "done"
    number = found.stages.index(found.stage) + 1
    said = f"stage {number}/{len(found.stages)} {found.stage}"
    if found.state == "person":
        said += " — the person's turn"
    elif found.state == "repair":
        said += f" — repair {found.repair}" if found.repair else " — repair"
    if found.stage == "build" and found.steps[1]:
        said += f" (plan steps {found.steps[0]}/{found.steps[1]} done)"
    return said


def card(found: Progress) -> list[str]:
    """The four lines for the person: the stage, the part done, the time left, and where the task works."""
    lines = [f"progress: {found.task} · {headline(found)}",
             f"  {found.percent}% {_bar(found.percent)}  {_stage_line(found)}"]
    times = []
    if found.left is not None:
        ahead = "after the answer of the person: " if found.state == "person" else ""
        times.append(f"time left: {ahead}about {_duration(found.left)} ({found.basis})")
    if found.spent is not None:
        times.append(f"{_duration(found.spent)} so far")
    if found.cost is not None:
        times.append(f"${found.cost:.2f} at list prices")
    if times:
        lines.append("  " + " · ".join(times))
    where_ = [", ".join(found.areas[:3]) + (f" and {len(found.areas) - 3} more" if len(found.areas) > 3 else "")] \
        if found.areas else []
    if found.now:
        where_.append(f"now: {found.now}")
    if found.outside:
        where_.append(f"{found.outside} changed file(s) of code outside the plan")
    if where_:
        lines.append("  works on: " + " · ".join(where_))
    return lines


def snapshot(found: Progress) -> dict:
    """The progress in the stats of the task, for the pull request and the board of the team."""
    return {"stage": found.stage, "state": found.state, "percent": found.percent, "headline": headline(found),
            "stages": list(found.stages), "left": found.left, "basis": found.basis, "areas": found.areas[:6],
            "now": found.now, "at": round(time.time())}


def board_cell(stats: dict) -> str:
    """The progress of a task of the board in a few words, from the snapshot in its stats. "" without one."""
    found = stats.get("progress") if isinstance(stats, dict) else None
    if not isinstance(found, dict) or "percent" not in found:
        return ""
    left = found.get("left")
    said = f"{found.get('percent')}% · {found.get('headline')}"
    if isinstance(left, int):
        said += f" · {'after the answer: ' if found.get('state') == 'person' else ''}about {_duration(left)} left"
    return said


def markdown(stats: dict) -> str:
    """The part of the pull request that tells how far the task is, from the snapshot in its stats. "" without
    one."""
    found = stats.get("progress") if isinstance(stats, dict) else None
    if not isinstance(found, dict) or "percent" not in found:
        return ""
    stages, stage, state = list(found.get("stages") or []), str(found.get("stage") or ""), found.get("state")
    lines = ["<!-- akasha:progress -->", f"### {found.get('headline')} — {found.get('percent')}%", "",
             f"`{_bar(int(found.get('percent') or 0))}`"]
    facts = []
    if isinstance(found.get("left"), int):
        ahead = "after the answer of the person: " if state == "person" else ""
        facts.append(f"**time left {ahead}about {_duration(found['left'])}** ({found.get('basis')})")
    if found.get("now"):
        facts.append(f"now: {found['now']}")
    if found.get("areas"):
        facts.append("works on: " + ", ".join(f"`{area}`" for area in found["areas"]))
    if facts:
        lines += ["", " · ".join(facts)]
    if state == "person":
        lines += ["", "> [!IMPORTANT]", "> The person's turn: the task waits for their answer."]
    rows = ["", "| Stage | State |", "|:--|:--|"]
    for name in stages:
        if not stage or stages.index(name) < stages.index(stage):
            mark = "✅"
        elif name == stage:
            mark = {"person": "⏸ the person's turn", "repair": "↻ repair"}.get(str(state), "▶ now")
        else:
            mark = "○"
        rows.append(f"| {('**' + name + '**') if name == stage else name} | {mark} |")
    lines += rows + ["<!-- /akasha:progress -->"]
    return "\n".join(lines)
