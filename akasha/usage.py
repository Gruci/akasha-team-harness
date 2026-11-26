"""The tokens that a task used, by step and by who used them.

Claude Code writes each call of a model into a transcript file with its tokens: one file for a session, and one for
each subagent. Akasha keeps what tells the tasks and the steps apart in `.docs/state/usage.jsonl`, on this computer:

- An event line, where a command changed where a task is: it started, the person approved, a review gave a verdict,
  the landing started or went back, the task ended, or another session took it.
- An agent line, each time a subagent stops (the hook SubagentStop): the tokens of that agent so far, the end of the
  round, and the step of the round. An agent that is asked again keeps its transcript, so its stops cut it into
  rounds.
- A total line, when the task writes its sums into its pull request.

A main session works for no single task, so its calls are counted later, in one pass over its transcript: a call
belongs to the step that the last mark of its session before it named. A mark is an event, or the start of a round
of an agent. `akasha usage <task>` shows the result. The landing and the handoff write the sums into the stats of
the task, the pull request carries them to the team, and the retro reads them there.

While the transcripts are there, the count comes from them: one answer that is in several files counts once, for
the main session first. Claude Code removes old transcripts; then the sums of the agent lines and of the total
lines stay. The record holds tokens and the name of the model, never money: RATES turns them into list prices only
where a command shows them. A file that Akasha cannot read gives "not read", never 0. Codex keeps a file for each
thread of a session (a rollout) with the tokens of each answer: Akasha reads the main thread and each subagent of
it in the same way. A model of another company has no rate: its tokens are in the table, without a price."""

from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import time
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from akasha.config import STATE_DIR
from akasha.task import Task, all_local

USAGE = STATE_DIR / "usage.jsonl"
# The phases of a task, in their order. Each call counts in one phase only, so the phases add up to the task. A
# phase that ends in "-fix" repairs: each time that it starts has its number
PHASES = ("preview", "preview-fix", "plan", "review", "plan-fix", "build", "check-fix", "result", "result-fix",
          "land", "land-fix")
FIXES = {"preview-fix": "after the person saw the preview, until the approval",
         "plan-fix": "after a CHANGES of the review of the plan, until the next verdict",
         "check-fix": "after the checks failed in the build, until they pass",
         "result-fix": "after a CHANGES of the review of the result, until the next verdict",
         "land-fix": "after the landing went back or a local check ran again, until the next landing"}
# The step of the work that each phase is a part of: the worker tells its step by what it ran in its round
STEP = {"preview-fix": "preview", "plan-fix": "plan", "check-fix": "build", "result-fix": "build", "land-fix": "build"}
MAIN, WORKER, REVIEWER, OTHER = "main", "worker", "reviewer", "other"
WHO = (MAIN, WORKER, REVIEWER, OTHER)
AGENTS = {"akasha-worker": WORKER, "akasha-reviewer": REVIEWER}
# Until when the sums of a task in its pull request count: the landing writes them when it starts and again when
# it sees the merge, and a merge that only a later session start sees leaves the first ones
LANDING, MERGE, HANDOFF = "landing", "merge", "handoff"
SHORT = 8                      # the characters of a session id that a line for a person shows
LONG_PROMPT = 100_000          # Claude Haiku 5.5 costs more for a call that holds more text than this
# A sum of calls: how many, then the tokens: input, cache write for 5 minutes, cache write for 1 hour, cache read,
# output. A cache read is text that an earlier call wrote and this call holds again
ZERO = (0, 0, 0, 0, 0, 0)
# The list prices of the API on RATES_DAY (platform.claude.com/docs/en/about-claude/pricing), for the global
# routing and without the discount of a batch: the id of a model, the dollars for a million input tokens, and the
# part of that price that a cache read costs. For each model a cache write for 5 minutes costs 1.25 times the
# input, one for 1 hour 2 times, and the output 5 times. Only an id that is here has a price: a new model is shown
# with its tokens and without a price, never with the price of a model with a similar name
RATES_DAY = "2026-11-24"
RATES = {"claude-fable-5-2": (8.0, 0.025), "claude-mythos-5-2": (8.0, 0.025),
         "claude-fable-5-1": (10.0, 0.025), "claude-mythos-5-1": (10.0, 0.025),
         "claude-fable-5": (10.0, 0.1), "claude-mythos-5": (10.0, 0.1),
         "claude-opus-5-5": (4.0, 0.05), "claude-opus-5": (5.0, 0.1), "claude-opus-4-8": (5.0, 0.1),
         "claude-opus-4-7": (5.0, 0.1), "claude-opus-4-6": (5.0, 0.1), "claude-opus-4-5": (5.0, 0.1),
         "claude-sonnet-5-5": (2.0, 0.05), "claude-sonnet-5": (2.0, 0.1), "claude-sonnet-4-6": (3.0, 0.1),
         "claude-sonnet-4-5": (3.0, 0.1), "claude-haiku-5-5": (0.1, 0.1), "claude-haiku-4-5": (1.0, 0.1)}
SNAPSHOT = re.compile(r"-\d{8}$")          # the day at the end of the id of an older model: claude-haiku-4-5-20251001
FAST, LONG = "/fast", "/long"  # the end of the name of a model for a call in fast mode, and for a long prompt
TIMES = {FAST: 2, LONG: 5}     # how many times the price
_AKASHA = r"(?:akasha_run\.py\"?|-m\s+akasha|\bakasha)\s+"
_NAME = r"\"?([a-z0-9][a-z0-9-]{0,59})(?![a-z0-9-])"
# An Akasha command that names a task, in a shell line of an agent: `… akasha_run.py" status <task> --brief`
NAMED = re.compile(_AKASHA + r"status\s+" + _NAME)
# The commands that tell the step of a round of a worker: it examines a preview, checks a build, or has a plan
# reviewed by the reviewer command of the team
ROUND = re.compile(_AKASHA + r"(check|preview|review)\s+" + _NAME)
STEP_OF = {"check": "build", "preview": "preview", "review": "plan"}
TASK_COMMANDS = {"status", "notes", "preview", "approve", "check", "review", "land", "result"}


@dataclass(frozen=True)
class Call:
    """One call of a model, as a transcript has it."""
    id: str
    at: float                  # seconds since 1970
    model: str                 # with FAST or LONG at its end where the call costs more
    tokens: tuple[int, ...]    # as ZERO, for one call
    thinking: int              # the part of the output that was thinking
    size: int                  # the text that the call held: input, cache writes, and cache reads
    turn: str = ""             # Codex: the turn of its thread, which is one round of an agent


@dataclass
class Thread:
    """One file of a session of Codex: the main thread or the thread of a subagent."""
    meta: dict                 # the payload of its line session_meta
    calls: list[Call]
    reviewed: bool             # an answer of its own holds the mark of a review of Akasha


def new_uid() -> str:
    """A name for one task that no other task has."""
    return secrets.token_hex(4)


def key(task: Task) -> str:
    """The name of a task in the record that no later task has: a merged task gives its id free. The stats hold
    it, because an Akasha before 2.0.4 keeps each entry of the stats and drops a field of the task that it does not
    know. A task that an older Akasha started has the number of its pull request."""
    return str(task.stats.get("uid") or f"{task.id}#{task.number}")


def plus(one: Iterable[int], other: Iterable[int], sign: int = 1) -> tuple[int, ...]:
    return tuple(left + sign * right for left, right in zip(one, other))


def price(model: str, total: Iterable[int]) -> float | None:
    """The dollars for these tokens of this model at the list prices, or None for a model without a rate."""
    end = next((item for item in TIMES if model.endswith(item)), "")
    name = model.removesuffix(end)
    found = RATES.get(name) or RATES.get(SNAPSHOT.sub("", name))
    if found is None:
        return None
    _calls, plain, short, hour, held, output = total
    return (plain + 1.25 * short + 2 * hour + found[1] * held + 5 * output) * found[0] * TIMES.get(end, 1) / 1e6


def _when(text: object) -> float:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _call(message: dict, used: dict, at: float) -> Call:
    written = used.get("cache_creation") if isinstance(used.get("cache_creation"), dict) else {}
    hour = int(written.get("ephemeral_1h_input_tokens") or 0)
    short = int(written.get("ephemeral_5m_input_tokens") or 0) if written else \
        int(used.get("cache_creation_input_tokens") or 0)
    plain, held = int(used.get("input_tokens") or 0), int(used.get("cache_read_input_tokens") or 0)
    size, model = plain + short + hour + held, str(message.get("model") or "?")
    if used.get("speed") == "fast":
        model += FAST
    elif model.startswith("claude-haiku-5-5") and size > LONG_PROMPT:
        model += LONG
    details = used.get("output_tokens_details") if isinstance(used.get("output_tokens_details"), dict) else {}
    return Call(str(message["id"]), at, model, (1, plain, short, hour, held, int(used.get("output_tokens") or 0)),
                int(details.get("thinking_tokens") or 0), size)


def _main_task(command: str) -> str:
    """The task explicitly named by one direct shell invocation of Akasha."""
    command = command.strip().removeprefix("& ").strip()
    if "akasha" not in command or any(char in command for char in "\n;&|`$<>"):
        return ""
    try:
        words = shlex.split(command.replace("\\", "/"))
    except ValueError:
        return ""
    if len(words) < 3:
        return ""
    exe = words[0].rsplit("/", 1)[-1].lower().removesuffix(".exe")
    args = words[1:]
    if re.fullmatch(r"py|python[\d.]*", exe):
        while args and args[0] in ("-3", "-B", "-X"):
            if args[0] == "-X" and args[:2] != ["-X", "utf8"]:
                return ""
            args = args[2:] if args[0] == "-X" else args[1:]
        if args[:2] == ["-m", "akasha"]:
            args = args[2:]
        elif args and args[0].rsplit("/", 1)[-1] == "akasha_run.py":
            args = args[1:]
        else:
            return ""
    elif exe != "akasha":
        return ""
    return args[1] if len(args) >= 2 and args[0] in TASK_COMMANDS else ""


def read(path: Path, commands: list[tuple[float, str]] | None = None,
         named_calls: dict[str, set[str]] | None = None) -> list[Call]:
    """Each call of a model in a transcript file, once. Claude Code writes one line for each block of an answer,
    each with the same id and the same tokens: the first one counts. OSError when the file cannot be read.
    `commands` takes the shell lines with their times. `named_calls` collects explicit task names by answer id."""
    found: list[Call] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as file:
        for line in file:
            if '"usage"' not in line:                 # a transcript of a session has tens of megabytes
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message") if isinstance(entry, dict) else None
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            at = _when(entry.get("timestamp")) or (found[-1].at if found else 0.0)
            used, name = message.get("usage"), message.get("id")
            if commands is not None or named_calls is not None:
                for block in message.get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    inputs = block.get("input")
                    if not isinstance(inputs, dict):
                        continue
                    command = str(inputs.get("command") or "")
                    if commands is not None:
                        commands.append((at, command))
                    if named_calls is not None and name and block.get("name") in ("Bash", "PowerShell"):
                        if task := _main_task(command):
                            named_calls.setdefault(str(name), set()).add(task)
            # Claude Code writes an error of the API as an answer of the model "<synthetic>", without tokens
            if not isinstance(used, dict) or not name or name in seen or message.get("model") == "<synthetic>":
                continue
            seen.add(name)
            found.append(_call(message, used, at))
    return found


def _codex_call(entry: dict, payload: dict, model: str, at: float) -> Call:
    """A call of a model in a file of Codex. Its input holds the cache reads and the cache writes; its output holds
    the reasoning."""
    used = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    held, written = int(used.get("cached_input_tokens") or 0), int(used.get("cache_write_input_tokens") or 0)
    size = int(used.get("input_tokens") or 0)
    name = str(payload.get("response_id") or f"{payload.get('thread_id')}:{entry.get('ordinal')}")
    tokens = (1, max(size - held - written, 0), written, 0, held, int(used.get("output_tokens") or 0))
    return Call(name, at, model, tokens, int(used.get("reasoning_output_tokens") or 0), size,
                str(payload.get("turn_id") or ""))


def read_codex(path: Path) -> Thread:
    """Each call of a model in a file of Codex (a rollout), once, with the model of its turn. A thread of a subagent
    starts with a copy of the talk of its parent: only its own lines after that tell whether it reviewed. OSError
    when the file cannot be read."""
    from akasha.review import MARK                    # review reads this module for its events
    meta: dict = {}
    found: list[Call] = []
    seen: set[str] = set()
    model, reviewed = "?", False
    with path.open(encoding="utf-8", errors="replace") as file:
        for line in file:
            kind = next((name for name in ("session_meta", "turn_context", "token_usage_record", "AKASHA-REVIEW:")
                         if name in line), "")
            if not kind:                              # a file of a session has tens of megabytes
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload") if isinstance(entry, dict) else None
            if not isinstance(payload, dict):
                continue
            if entry.get("type") == "session_meta" and not meta:
                meta = payload
            elif entry.get("type") == "turn_context":
                model = str(payload.get("model") or model)
            elif entry.get("type") == "token_usage_record":
                call = _codex_call(entry, payload, model, _when(entry.get("timestamp")) or
                                   (found[-1].at if found else 0.0))
                if call.id not in seen:
                    seen.add(call.id)
                    found.append(call)
            elif payload.get("type") == "message" and payload.get("role") == "assistant" and \
                    int(entry.get("ordinal") or 0) >= int(meta.get("subagent_history_start_ordinal") or 0):
                reviewed = reviewed or bool(MARK.search(json.dumps(payload.get("content"), ensure_ascii=False)))
    return Thread(meta, found, reviewed)


def codex_files(session: str) -> tuple[Path | None, list[Path]]:
    """The file of a session of Codex, and the files of its subagents: each file from the same moment on whose
    session is this one. (None, []) when this computer has no such session."""
    top = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    if not session or not top.is_dir():
        return None, []
    main = next(iter(sorted(top.rglob(f"rollout-*{session}.jsonl"))), None)
    if main is None:
        return None, []
    agents = []
    for path in sorted(top.rglob("rollout-*.jsonl")):
        if path == main or path.name < main.name:     # the name starts with the moment of the start of the thread
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as file:
                first = json.loads(file.readline() or "{}")
        except (OSError, ValueError):
            continue
        payload = first.get("payload") if isinstance(first, dict) else None
        if isinstance(payload, dict) and payload.get("session_id") == session and payload.get("id") != session:
            agents.append(path)
    return main, agents


def _by_model(calls: Iterable[Call]) -> dict[str, tuple[int, ...]]:
    sums: dict[str, tuple[int, ...]] = {}
    for call in calls:
        sums[call.model] = plus(sums.get(call.model, ZERO), call.tokens)
    return sums


def _append(root: Path, line: dict) -> None:
    path = root / USAGE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(line, ensure_ascii=False) + "\n")


def lines(root: Path) -> list[dict]:
    """Each line of the record of this computer, in the order in which it was written."""
    try:
        text = (root / USAGE).read_text(encoding="utf-8")
    except OSError:
        return []
    found = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            found.append(item)
    return found


def note_event(root: Path, task: Task, what: str, stage: str | None = None, **more: object) -> None:
    """Add an event of a task, after the command did what the event tells. `stage`: the step of the task from now
    on, for the session that holds it; "" when the task ends for this session; None when the event moves no step.
    A failure never stops the command."""
    try:
        line = {"at": round(time.time(), 3), "kind": "event", "what": what, "key": key(task), "task": task.id,
                "number": task.number, "session": task.session, **more}
        if stage is not None:
            line["stage"] = stage
        _append(root, line)
    except Exception:     # noqa: BLE001 — the record of the usage must never stop the work
        pass


def _main_of(path: Path, session: str) -> str:
    """The transcript of the session of an agent file. The folder of the agents of a session has the name of the
    session, and the transcript is beside that folder. A workflow puts its agents some folders deeper."""
    for parent in path.parents:
        if session and parent.name == session:
            return str(parent.parent / f"{session}.jsonl")
    return ""


def _named(local: dict[str, Task], commands: list[tuple[float, str]]) -> Task | None:
    """The task of this computer that the agent named first in an Akasha command."""
    for _at_, line in commands:
        for name in NAMED.findall(line):
            if name in local:
                return local[name]
    return None


def _ran(commands: list[tuple[float, str]], since: float, name: str) -> str:
    """The step that the Akasha commands of a worker tell, of those after `since` that name the task: it checked
    a build, examined a preview, or had a plan reviewed. "" when none tells one."""
    ran = {word for at, line in commands if at > since for word, found in ROUND.findall(line) if found == name}
    return next((STEP_OF[word] for word in ("check", "preview", "review") if word in ran), "")


def _step(who: str, task: Task, commands: list[tuple[float, str]], since: float, verdicts: list[tuple]) -> str:
    """The step of the round of an agent of Akasha that stops now. A reviewer: the review whose verdict this very
    stop recorded. A worker: what it ran in this round, because one worker can be asked for the preview, then the
    plan, then the build. Else the state of the task now."""
    from akasha import flow                            # flow reads this module for its events
    if who == REVIEWER:
        said = next((subject for found, subject in verdicts if found == key(task)), "")
        return {"plan": "review", "result": "result"}.get(said) or flow.stage(task, reviews=True)
    step = _ran(commands, since, task.id) or flow.stage(task)
    return step if step in ("preview", "plan", "build") else "build"      # a worker lands nothing


def repeated(root: Path, payload: dict, agent: str = "claude") -> bool:
    """True when this stop of a subagent is in the record already: the same agent of the same session, and no
    call of a model since its last stop line. An agent engine can give one stop twice; a review that is recorded
    twice counts one more round and one more verdict. An agent that was asked again has new calls."""
    place = str(payload.get("agent_transcript_path") or "")
    if agent != "claude" or not place:
        return False
    path, session = Path(place), str(payload.get("session_id") or "")
    name = str(payload.get("agent_id") or path.stem.removeprefix("agent-"))
    try:
        calls = len(read(path))
    except OSError:
        return False
    return bool(calls) and any(item.get("kind") == "agent" and item.get("agent") == name
                               and item.get("session") == session and item.get("calls") == calls
                               for item in lines(root))


def on_subagent_stop(root: Path, payload: dict, agent: str = "claude", verdicts: list[tuple] | None = None) -> None:
    """Add the tokens of a subagent that stopped, as its transcript has them now, with the end and the step of this
    round. A second stop without a new call adds no line. `verdicts`: the key of the task and the subject of each
    review that the hook of this stop recorded."""
    place = str(payload.get("agent_transcript_path") or "")
    if agent != "claude" or not place:
        return
    path, session = Path(place), str(payload.get("session_id") or "")
    name = str(payload.get("agent_id") or path.stem.removeprefix("agent-"))
    kind = str(payload.get("agent_type") or "")
    who = AGENTS.get(kind.split(":")[-1], OTHER)
    line = {"at": round(time.time(), 3), "kind": "agent", "agent": name, "agent_type": kind, "who": who,
            "session": session, "transcript": place,
            "main": str(payload.get("transcript_path") or "") or _main_of(path, session)}
    before = [item for item in lines(root) if item.get("kind") == "agent" and item.get("agent") == name
              and item.get("session") == session and not item.get("unread")]
    commands: list[tuple[float, str]] = []
    try:
        calls = read(path, commands)
    except OSError:
        keys = {key for key, _subject in verdicts or []}
        if len(keys) == 1:
            line["key"] = keys.pop()
        elif not keys and before and before[-1].get("key"):
            line["key"] = before[-1]["key"]
        _append(root, {**line, "unread": True})
        return
    if not calls or (before and before[-1].get("calls") == len(calls)):
        return
    last = float(before[-1].get("last") or 0) if before else 0.0
    local = {task.id: task for task in all_local(root)}
    recorded = {found for found, _subject in verdicts or []}
    task = next((item for item in local.values() if who == REVIEWER and key(item) in recorded), None) or \
        (local.get(str(before[-1].get("task"))) if before and before[-1].get("key") else None) or \
        (_named(local, commands) if who != OTHER else None)
    whose = {"key": key(task), "task": task.id, "number": task.number,
             "stage": _step(who, task, commands, last, verdicts or [])} if task else \
        {"key": "", "task": "", "number": 0, "stage": ""}      # the marks of the session decide
    _append(root, {**line, **whose, "calls": len(calls), "largest": max(call.size for call in calls),
                   "thinking": sum(call.thinking for call in calls), "models": _by_model(calls),
                   "first": calls[0].at, "last": calls[-1].at,
                   "round_first": next((call.at for call in calls if call.at > last), calls[-1].at)})


@dataclass
class Round:
    """One round of one agent: from a request to its stop."""
    agent: str
    who: str
    key: str                   # "" when the marks of the session decide
    stage: str
    at: float                  # its first call
    models: dict[str, tuple[int, ...]]
    largest: int
    calls: list[Call] | None = None    # None when only the sums of a stop line are left
    stopped: bool = True       # False for calls without a stop line after them: counted from the transcript


def _rounds(agent_lines: list[dict]) -> list[Round]:
    """The rounds of an agent whose transcript is gone, from its lines: the sums of each line less the line
    before it. An estimate: a line cannot tell a copy of an answer of the session, nor the time of each call."""
    found: list[Round] = []
    before: dict = {}
    for line in agent_lines:
        sums = line.get("models") or {}
        models = {model: plus(total, before.get(model, ZERO), -1) for model, total in sums.items()}
        models = {model: total for model, total in models.items() if total[0] > 0}
        before = sums
        if models:
            found.append(Round(str(line.get("agent")), str(line.get("who") or OTHER), str(line.get("key") or ""),
                               str(line.get("stage") or ""), float(line.get("round_first") or line.get("first") or 0),
                               models, int(line.get("largest") or 0)))
    return found


def _cut(name: str, who: str, calls: list[Call], stops: list[dict], commands: list[tuple[float, str]]) -> list[Round]:
    """The rounds of an agent from the calls of its transcript: each stop line ends one round, and the calls after
    the last stop are one more round without a stop. An agent that still runs, one that was cut off, and an agent of
    a workflow have such calls. They tell their own step: a worker that was cut off in its build ran the checks."""
    found, start = [], float("-inf")

    def one(line: dict, part: list[Call], stage: str, stopped: bool = True) -> Round:
        return Round(name, str(line.get("who") or who), str(line.get("key") or ""), stage, part[0].at,
                     _by_model(part), max(call.size for call in part), part, stopped)

    for line in stops:
        end = float(line.get("last") or 0)
        part = [call for call in calls if start < call.at <= end]
        start = end
        if part:
            found.append(one(line, part, str(line.get("stage") or "")))
    rest = [call for call in calls if call.at > start]
    if rest:
        last = stops[-1] if stops else {}
        told = _ran(commands, start, str(last.get("task"))) if last.get("key") and last.get("who") == WORKER else ""
        found.append(one(last, rest, told or str(last.get("stage") or ""), stopped=False))
    return found


def _turns(name: str, who: str, calls: list[Call]) -> list[Round]:
    """The rounds of a subagent of Codex: each turn of its thread, from a request to its answer."""
    found: list[Round] = []
    for call in calls:
        if found and found[-1].calls and found[-1].calls[-1].turn == call.turn:
            last = found[-1]
            last.calls.append(call)
            last.models, last.largest = _by_model(last.calls), max(last.largest, call.size)
        else:
            found.append(Round(name, who, "", "", call.at, _by_model([call]), call.size, [call]))
    return found


def _kind(path: Path) -> str:
    """The type of an agent, from the file that Claude Code keeps beside its transcript. "" when it is not there."""
    try:
        found = json.loads(path.with_name(path.stem + ".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(found.get("agentType") or "") if isinstance(found, dict) else ""


def _marks(all_lines: list[dict]) -> dict[str, list[tuple[float, str, str]]]:
    """For each session, in the order of time: from when on it works on which task, in which step. ("", "") from
    the moment when it works on no task."""
    marks: dict[str, list[tuple[float, str, str]]] = {}
    for line in all_lines:
        session, at = str(line.get("session") or ""), float(line.get("at") or 0)
        if line.get("kind") == "event":
            if session and "stage" in line:
                stage = str(line["stage"])
                marks.setdefault(session, []).append((at, str(line.get("key") or ""), stage))
            if line.get("was"):                       # another session took the task from this one
                marks.setdefault(str(line["was"]), []).append((at, str(line.get("key") or ""), ""))
        elif line.get("kind") == "agent" and session and line.get("key") and line.get("stage"):
            marks.setdefault(session, []).append((float(line.get("round_first") or line.get("first") or at),
                                                  str(line["key"]), str(line["stage"])))
    for session, changes in marks.items():
        active: dict[str, str] = {}
        history = []
        for at, name, stage in sorted(changes, key=lambda change: change[0]):
            active.pop(name, None)
            if stage and name:
                active[name] = stage
            # Ending or handing off one task leaves the other active tasks in this session.
            latest = next(reversed(active), "")
            history.append((at, latest, active.get(latest, "")))
        marks[session] = history
    return marks


def _at(marks: list[tuple[float, str, str]], when: float) -> tuple[str, str]:
    """The task and the step of a session at a moment."""
    place = bisect_right(marks, (when, "￿", ""))
    return marks[place - 1][1:] if place else ("", "")


@dataclass
class Timeline:
    """The phases of a task on this computer, in the order of time: from when on the task is in which phase, and
    the number of the time for a phase that repairs. `counts`: how many times each phase that repairs started."""
    marks: list[tuple[float, str, int]]
    counts: dict[str, int]

    def at(self, when: float) -> tuple[str, int]:
        """The phase of the task at a moment. ("", 0) before its first event and after its end."""
        place = bisect_right(self.marks, (when, "￿", 0))
        return self.marks[place - 1][1:] if place else ("", 0)

    def last(self) -> tuple[str, int]:
        return self.marks[-1][1:] if self.marks else ("", 0)


def timeline(mine: list[dict], carried: dict | None = None) -> Timeline:
    """The phases of a task from its events on this computer. `carried`: the usage that the task carries, with the
    phase and the counts of another computer at its handoff, which a session that resumes the task here continues.
    A show of a preview without a digest starts a fix each time."""
    carried = carried or {}
    seed = carried.get("phase") if isinstance(carried.get("phase"), list) and len(carried["phase"]) == 2 else None
    found = Timeline([], {})
    # A task without a screen starts in its plan, and shows the plan to the person after its review
    now, waits, shown = "", False, None

    def go(at: float, phase: str, number: int = 0) -> None:
        nonlocal now
        now = phase
        found.marks.append((at, phase, number))

    def fix(at: float, phase: str) -> None:
        found.counts[phase] = found.counts.get(phase, 0) + 1
        go(at, phase, found.counts[phase])

    events = sorted((line for line in mine if line.get("kind") == "event"), key=lambda line: float(line.get("at") or 0))
    for line in events:
        what, at, stage = line.get("what"), float(line.get("at") or 0), line.get("stage")
        if what in ("start", "upgraded"):
            waits = stage == "plan"
            go(at, str(stage or ""))
        elif what == "shown":
            if line.get("digest") is None or line.get("digest") != shown:
                shown = line.get("digest")
                fix(at, "preview-fix")
        elif what == "approved":
            waits = False
            go(at, str(stage or "build"))
        elif what == "verdict":
            subject = "result" if line.get("subject") == "result" else "plan"
            if line.get("verdict") == "CHANGES":
                fix(at, f"{subject}-fix")
            elif now not in ("land", "land-fix"):
                # A quick task still has its preview and approval after its code review.
                # Only the landing event begins a landing, for every kind of task.
                go(at, "plan" if subject == "plan" and waits else "build")
        elif what == "check":
            if now == "land":
                # A local full check ran again on the work. CI polling emits no check event.
                fix(at, "land-fix")
            elif line.get("verdict") == "FAIL" and now in ("build", "check-fix"):
                fix(at, "check-fix")
            elif line.get("verdict") == "PASS" and now == "check-fix":
                go(at, "build")
        elif what == "landing":
            go(at, "land")
        elif what == "back" and now != "land-fix":
            fix(at, "land-fix")
        elif what in ("taken", "resumed"):
            if not now and seed:                      # this computer continues the task of another one
                for phase, count in (carried.get("counts") or {}).items():
                    found.counts[str(phase)] = max(found.counts.get(str(phase), 0), int(count))
                go(at, str(seed[0]), int(seed[1]))
            elif not now and stage:
                go(at, str(stage))
        elif stage == "":                             # merged, closed, cancelled, dropped, or handed off
            go(at, "")
    return found


def _phase(who: str, stage: str, now: str, own: bool) -> str:
    """The phase of a call. `stage`: the step of the round of an agent that named the task (`own`), else the step
    of its session then. `now`: the phase of the task then. A reviewer reviews the plan or the result. A worker
    tells its step by what it ran in its round, and the phase of the task tells the part of that step. The main
    session and another agent work in the phase of the task."""
    if who == REVIEWER:
        if stage in ("review", "result"):
            return stage
        return "result" if STEP.get(now, now) in ("build", "land") else "review"
    if own and who == WORKER:
        return now if now and STEP.get(now, now) == stage else stage
    return now or stage


def _main(all_lines: list[dict], session: str) -> str:
    """The transcript file of a session: as a hook named it, else where Claude Code keeps its sessions."""
    named = next((str(line["main"]) for line in all_lines if line.get("session") == session and line.get("main")), "")
    if named:
        return named
    top = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    return next((str(path) for path in top.glob(f"*/{session}.jsonl")), "") if session else ""


def _shared_tasks(all_lines: list[dict], session: str, here: list[tuple[float, str, str]]) \
        -> dict[str, list[tuple[float, str, str]]]:
    """For a shared session, when each named task was active there. Names can be reused after a merge."""
    keys = {key for _at_, key, _stage in here if key}
    if len(keys) < 2:
        return {}
    grouped: dict[str, list[dict]] = {}
    for line in all_lines:
        if line.get("key") in keys and line.get("task"):
            grouped.setdefault(str(line["task"]), []).append(line)
    return {name: _marks(group).get(session, []) for name, group in grouped.items()}


def _fixes(sums: dict) -> list[list]:
    """The rows of each time of a phase that repairs, in the stats of a session."""
    return [row for row in sums.get("fixes") or [] if isinstance(row, list) and len(row) == 9]


class Sums:
    """Sums of a task: of one source (the main session, or one agent), or of a whole session. The rows, the count
    of the rounds, and the cost of each time of a phase that repairs go into the stats of the task. The largest
    call, each round, and the notes are only for this computer. `kept`, `stops`, and `unread` name what did not come
    from a transcript now: from an earlier count, from the sums of the stop lines (an estimate), or from nothing."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], tuple[int, ...]] = {}          # phase, who, model
        self.fixes: dict[tuple[str, int, str], tuple[int, ...]] = {}         # phase, its number, model
        self.counts: dict[tuple[str, str], int] = {}                         # phase, who: its rounds
        self.rounds: list[tuple[str, str, float, dict[str, tuple[int, ...]]]] = []    # phase, who, start, sums
        self.largest: dict[tuple[str, str, str], int] = {}
        self.kept: list[str] = []
        self.stops: list[str] = []
        self.unread: list[str] = []
        self.estimated_main = 0                       # main calls assigned by time in a shared session
        self.notes: list[str] = []

    def add(self, phase: str, number: int, who: str, model: str, total: tuple[int, ...], size: int) -> None:
        """Add calls of one moment: also to the time of the phase that repairs, when it is one."""
        self.rows[phase, who, model] = plus(self.rows.get((phase, who, model), ZERO), total)
        self.largest[phase, who, model] = max(self.largest.get((phase, who, model), 0), size)
        if phase in FIXES and number:
            self.fixes[phase, number, model] = plus(self.fixes.get((phase, number, model), ZERO), total)

    def count(self, phase: str, who: str, at: float, models: dict[str, tuple[int, ...]]) -> None:
        """Add one round of an agent."""
        self.counts[phase, who] = self.counts.get((phase, who), 0) + 1
        self.rounds.append((phase, who, at, models))

    def take(self, old: dict) -> bool:
        """Add the sums of an earlier count, in the form of the stats. False when it holds no row."""
        rows = [row for row in old.get("rows") or [] if isinstance(row, list) and len(row) == 9]
        for phase, who, model, *total in rows:
            self.rows[phase, who, model] = plus(self.rows.get((phase, who, model), ZERO), total)
        for phase, number, model, *total in _fixes(old):
            where = (str(phase), int(number), str(model))
            self.fixes[where] = plus(self.fixes.get(where, ZERO), total)
        for phase, who, count in old.get("rounds") or []:
            self.counts[phase, who] = self.counts.get((phase, who), 0) + int(count)
        self.estimated_main += int(old.get("estimated_main") or 0)
        return bool(rows)

    def merge(self, other: Sums) -> None:
        for where, total in other.rows.items():
            self.rows[where] = plus(self.rows.get(where, ZERO), total)
        for place, total in other.fixes.items():
            self.fixes[place] = plus(self.fixes.get(place, ZERO), total)
        for step, count in other.counts.items():
            self.counts[step] = self.counts.get(step, 0) + count
        for where, size in other.largest.items():
            self.largest[where] = max(self.largest.get(where, 0), size)
        self.rounds += other.rounds
        self.kept += other.kept
        self.stops += other.stops
        self.unread += other.unread
        self.estimated_main += other.estimated_main
        self.notes += other.notes

    def stats(self) -> dict:
        """The sums in the form that the pull request carries. To count the same again gives the same."""
        found: dict = {"rows": [[*where, *total] for where, total in sorted(self.rows.items())]}
        if self.counts:
            found["rounds"] = [[*where, count] for where, count in sorted(self.counts.items())]
        if self.fixes:
            found["fixes"] = [[*where, *total] for where, total in sorted(self.fixes.items())]
        for name in ("kept", "stops", "unread"):
            if getattr(self, name):
                found[name] = sorted(set(getattr(self, name)))
        if self.estimated_main:
            found["estimated_main"] = self.estimated_main
        return found


@dataclass
class Count:
    """The usage of a task as this computer counted it: each session, each source of each session (the main
    session, and each agent by its id), and the phases of the task."""
    sessions: dict[str, Sums]
    parts: dict[str, dict[str, Sums]]
    phases: Timeline


def _usage(task: Task | None) -> dict:
    found = task.stats.get("usage") if task is not None else None
    return found if isinstance(found, dict) else {}


def carried(task: Task | None) -> dict:
    """The usage that the task carries in its stats: the sums of each session, and the phase at a handoff."""
    return _usage(task)


def _kept(root: Path, task_key: str, task: Task | None) -> dict[str, dict]:
    """The sums of each session that the task already carries: from the total lines of this computer, and from
    the stats of the task, which another computer can have written into the pull request."""
    found: dict[str, dict] = {}
    for line in lines(root):
        if line.get("kind") == "total" and line.get("key") == task_key and isinstance(line.get("sessions"), dict):
            found.update(line["sessions"])
    carried = _usage(task).get("sessions") or {}
    found.update({name: sums for name, sums in carried.items() if name not in found or not sums.get("unread")})
    return found


def _sources(all_lines: list[dict], task_key: str) -> dict[str, dict[str, dict]]:
    """What each source of each session gave at the earlier counts of this computer. A source that cannot be read
    now keeps what it gave then: a later count never loses a call that an earlier one read."""
    found: dict[str, dict[str, dict]] = {}
    for line in all_lines:
        if line.get("kind") == "total" and line.get("key") == task_key and isinstance(line.get("sources"), dict):
            for session, sources in line["sources"].items():
                found.setdefault(session, {}).update(sources)
    return found


def _where(one: Round, here: list[tuple[float, str, str]], phases: Timeline, at: float) -> tuple[str, str, int]:
    """The task, the phase, and the number of the time of the phase of a call of an agent at a moment."""
    whose, stage = (one.key, one.stage) if one.key else _at(here, at)
    now, number = phases.at(at)
    phase = _phase(one.who, stage, now, bool(one.key))
    return whose, phase, number if phase == now else 0


def _take_round(part: Sums, one: Round, here: list[tuple[float, str, str]], task_key: str, phases: Timeline) -> None:
    """Add a round of an agent to the sums of the task. With its calls, each call counts at its own time: in the
    phase of the task then, and, for an agent that names no task, for the task of the session then. With only the
    sums of a stop line, the whole round counts at its start."""
    if one.calls is None:
        whose, phase, number = _where(one, here, phases, one.at)
        if whose == task_key:
            for model, total in one.models.items():
                part.add(phase, number, one.who, model, total, one.largest)
            part.count(phase, one.who, one.at, one.models)
        return
    counted, first = [], ""
    for call in one.calls:
        whose, phase, number = _where(one, here, phases, call.at)
        if whose == task_key:
            part.add(phase, number, one.who, call.model, call.tokens, call.size)
            counted.append(call)
            first = first or phase
    if counted:
        part.count(first, one.who, counted[0].at, _by_model(counted))
        if not one.stopped:
            part.notes.append(f"agent {one.agent} ({one.who}) has calls without a stop after them: counted from "
                              "its transcript")


def _session(all_lines: list[dict], session: str, task_key: str, here: list[tuple[float, str, str]],
             phases: Timeline, seen: set[str], old: dict[str, dict], kept: dict) -> dict[str, Sums]:
    """The sums of one session for the task, by source: the main session, and each agent by its id. A transcript
    gives the calls. The main session comes first: an agent that starts with the talk of its session holds a copy
    of its answers, and an answer that `seen` holds does not count again. A source without a transcript keeps what
    an earlier count read; else the sums of its stop lines stand in, as an estimate; else it is not read. A session
    of Codex has a file for its main thread and one for each subagent, each turn of a subagent one round."""
    main = _main(all_lines, session)
    codex_main, codex_agents = (None, []) if main else codex_files(session)
    parts = {MAIN: Sums()}
    shared = _shared_tasks(all_lines, session, here)
    named_calls: dict[str, set[str]] = {}
    try:
        calls = read(Path(main), named_calls=named_calls if shared else None) if main else \
            read_codex(codex_main).calls if codex_main else None
    except OSError:
        calls = None
    if calls is None:
        earlier = old.get(MAIN) or {"rows": [row for row in kept.get("rows") or [] if row[1] == MAIN],
                                    "estimated_main": kept.get("estimated_main", 0)}
        (parts[MAIN].kept if parts[MAIN].take(earlier) else parts[MAIN].unread).append("the main session")
    for call in calls or []:
        if call.id not in seen:
            seen.add(call.id)
            whose, stage = _at(here, call.at)
            names = named_calls.get(call.id, set())
            named = _at(shared.get(next(iter(names)), []), call.at) if len(names) == 1 else ("", "")
            if named[0]:
                whose, stage = named
            if whose == task_key:
                now, number = phases.at(call.at)
                phase = _phase(MAIN, stage, now, False)
                parts[MAIN].add(phase, number if phase == now else 0, MAIN, call.model, call.tokens, call.size)
                if shared and not named[0]:
                    parts[MAIN].estimated_main += 1
    agent_lines = [line for line in all_lines if line.get("kind") == "agent" and line.get("session") == session]
    stops: dict[str, list[dict]] = {}
    for line in agent_lines:
        if not line.get("unread"):
            stops.setdefault(str(line.get("agent")), []).append(line)
    # Each agent file of the session, also some folders deeper, where a workflow puts its agents
    places = {path.stem.removeprefix("agent-"): path
              for path in (sorted(Path(main).with_suffix("").rglob("agent-*.jsonl")) if main else [])}
    for line in agent_lines:
        if line.get("transcript"):
            places.setdefault(str(line.get("agent")), Path(str(line["transcript"])))
    loaded: dict[str, tuple[list[Call], list[tuple[float, str]]]] = {}
    kinds: dict[str, str] = {}
    for name, path in places.items():
        commands: list[tuple[float, str]] = []
        try:
            loaded[name] = (read(path, commands), commands)
        except OSError:
            continue
        kinds[name] = AGENTS.get(_kind(path).split(":")[-1], OTHER)
    threads: set[str] = set()
    for path in codex_agents:
        try:
            thread = read_codex(path)
        except OSError:
            continue
        name = str(thread.meta.get("id") or path.stem)
        loaded[name], threads = (thread.calls, []), threads | {name}
        role = str(thread.meta.get("agent_role") or "").split(":")[-1]
        kinds[name] = AGENTS.get(role) or (REVIEWER if thread.reviewed else OTHER)
    for name in sorted(loaded, key=lambda item: loaded[item][0][0].at if loaded[item][0] else 0.0):
        fresh = [call for call in loaded[name][0] if call.id not in seen]
        seen.update(call.id for call in fresh)
        parts[name] = Sums()
        rounds = _turns(name, kinds[name], fresh) if name in threads else \
            _cut(name, kinds[name], fresh, stops.get(name, []), loaded[name][1])
        for one in rounds:
            _take_round(parts[name], one, here, task_key, phases)
    unread: set[str] = set()
    unassigned: set[str] = set()
    for line in agent_lines:
        name = str(line.get("agent"))
        if not line.get("unread") or name in loaded or name in stops or name in old:
            continue
        owner = line.get("key") or _at(here, float(line.get("at") or 0))[0]
        if owner == task_key:
            unread.add(name)
        elif not owner:
            unassigned.add(name)
    if unassigned - unread:
        parts[MAIN].notes.append(f"session {session[:SHORT]}: {len(unassigned - unread)} unread agent(s) stopped "
                                 "without an active task; their usage could not be assigned")
    for name in sorted((set(stops) | set(old) | unread) - set(loaded) - {MAIN}):
        part = parts[name] = Sums()
        if name in old:                               # an earlier count read it: also when it gave nothing
            if part.take(old[name]):
                part.kept.append(f"agent {name}")
        elif name in stops:
            for one in _rounds(stops[name]):
                _take_round(part, one, here, task_key, phases)
            if part.rows:
                part.stops.append(f"agent {name}")
        else:
            part.unread.append(f"agent {name}")
    return parts


def measure(root: Path, task_key: str, kept: dict[str, dict] | None = None, carried: dict | None = None) -> Count:
    """Count the usage of a task on this computer, for each session that worked on it. `kept`: the sums that the
    task carries already. `carried`: the usage that the task carries, with the phase of another computer at its
    handoff."""
    all_lines = lines(root)
    mine = [line for line in all_lines if line.get("key") == task_key]
    sessions = list(dict.fromkeys(str(line["session"]) for line in mine if line.get("session")))
    marks, old = _marks(all_lines), _sources(all_lines, task_key)
    found = Count({}, {}, timeline(mine, carried))
    seen: set[str] = set()                            # a session that continues another one copies its answers
    for session in sessions:
        here = marks.get(session, [])
        parts = _session(all_lines, session, task_key, here, found.phases, seen, old.get(session) or {},
                         (kept or {}).get(session) or {})
        whole = Sums()
        for part in parts.values():
            whole.merge(part)
        others = {whose for _when_, whose, _stage in here if whose and whose != task_key}
        if others:
            whole.notes.append(f"session {session[:SHORT]} also worked on {len(others)} other task(s). A direct Claude shell "
                               "command naming one active task counts there. Other main calls use the last recorded "
                               "step of the session")
        found.sessions[session], found.parts[session] = whole, parts
    return found


def _totals(root: Path, task: Task, cut: str) -> tuple[dict, Count]:
    carried, kept = _usage(task), _kept(root, key(task), task)
    found = measure(root, key(task), kept, carried)
    sessions = dict(kept)
    for session, sums in found.sessions.items():
        if sums.rows:                                 # a session of which nothing was read stays out
            sessions[session] = sums.stats()
    result: dict = {"v": 1, "cut": cut or carried.get("cut") or "", "sessions": sessions}
    phase, number = found.phases.last()
    if phase:
        result["phase"] = [phase, number]
    if found.phases.counts:
        result["counts"] = dict(sorted(found.phases.counts.items()))
    return result, found


def totals(root: Path, task: Task, cut: str = "") -> dict:
    """The sums of the task for its stats: each session that this computer measured, and the sessions of other
    computers as the task carries them. To write them again changes nothing. `cut`: until when they count. The
    phase of the task now and how many times each phase that repairs started go with them, so that the computer
    that continues the task counts in the same phase, with the next numbers."""
    return _totals(root, task, cut)[0]


def freeze(root: Path, task: Task, cut: str) -> None:
    """Write the sums of the task into its stats, for the pull request, and keep them on this computer too, with
    what each source gave: Claude Code removes old transcripts, and an update of the pull request can fail. A
    failure never stops the command."""
    try:
        found, count = _totals(root, task, cut)
        if not found["sessions"]:
            return
        task.stats["usage"] = found
        # Each agent that a transcript gave, also one that gave nothing for this task: a later count without its
        # transcript must not take the sums of its stop lines in place of what was read
        sources = {session: {name: part.stats() for name, part in parts.items()
                             if not part.stops and (part.rows or not part.unread)}
                   for session, parts in count.parts.items()}
        _append(root, {"at": round(time.time(), 3), "kind": "total", "key": key(task), "task": task.id,
                       "number": task.number, "cut": cut, "sessions": found["sessions"], "sources": sources})
    except Exception:     # noqa: BLE001 — the record of the usage must never stop the work
        pass


def _rows(stats: dict | None, name: str = "rows") -> list[list]:
    """Each row of the sums of a task, over its sessions."""
    sessions = (stats or {}).get("sessions") if isinstance(stats, dict) else None
    return [row for sums in (sessions or {}).values() if isinstance(sums, dict)
            for row in sums.get(name) or [] if isinstance(row, list) and len(row) == 9]


def _dollars(rows: Iterable[list]) -> tuple[float, set[str]]:
    """The list price of rows of the stats, and the models among them that have no rate."""
    total, unknown = 0.0, set()
    for row in rows:
        found = price(str(row[2]), row[3:9])
        if found is None:
            unknown.add(str(row[2]))
        else:
            total += found
    return total, unknown


def rows_of(stats: dict | None) -> list[list]:
    """Each row of the sums of a task (as `totals` gives them), over its sessions."""
    return _rows(stats)


def dollars(rows: Iterable[list]) -> tuple[float, set[str]]:
    """The list price of rows of the stats, and the models among them that have no rate."""
    return _dollars(rows)


def _money(value: float) -> str:
    return f"${value:.2f}"


def _by(rows: list[list], place: int, order: tuple[str, ...]) -> list[tuple[str, float]]:
    """The list price of the rows by the value of one column, in the given order, without the empty ones."""
    found = [(name, _dollars(row for row in rows if row[place] == name)[0]) for name in order]
    return [(name, value) for name, value in found if value]


def _fix_costs(stats: dict | None) -> dict[str, list[tuple[int, float]]]:
    """The list price of each time of each phase that repairs, by phase in the order of PHASES: over each session
    that worked in it."""
    each: dict[tuple[str, int], list[list]] = {}
    sessions = (stats or {}).get("sessions") if isinstance(stats, dict) else None
    for sums in (sessions or {}).values():
        for row in _fixes(sums) if isinstance(sums, dict) else []:
            each.setdefault((str(row[0]), int(row[1])), []).append(row)
    found: dict[str, list[tuple[int, float]]] = {}
    for (phase, number), rows in sorted(each.items(), key=lambda item: (_order(item[0][0]), item[0][1])):
        found.setdefault(phase, []).append((number, _dollars(rows)[0]))
    return found


def _order(phase: str) -> int:
    return PHASES.index(phase) if phase in PHASES else len(PHASES)


def line(task: Task) -> str:
    """One line for the end of a landing, from the stats of the task: the list price of the task, by who used it,
    and what each phase that repairs cost. "" for a task without a record."""
    rows = _rows(_usage(task))
    if not rows:
        return ""
    total, unknown = _dollars(rows)
    parts = [f"{name} {_money(value)}" for name, value in _by(rows, 1, WHO)]
    fixes = [f"{phase} {_money(sum(cost for _number, cost in costs))} ({len(costs)})"
             for phase, costs in _fix_costs(_usage(task)).items()]
    return (f"usage of task {task.id}, an estimate at the list prices of the API: {_money(total)} — "
            + " · ".join(parts)
            + (f" · repairs: {', '.join(fixes)}" if fixes else "")
            + (f" · no price for {', '.join(sorted(unknown))}" if unknown else "")
            + (" · counted up to the start of the landing" if _usage(task).get("cut") == LANDING else ""))


def _tokens(count: int) -> str:
    return f"{count / 1e6:.1f}M" if count >= 1e6 else f"{count / 1e3:.0f}K" if count >= 1000 else str(count)


def _place(phase: str, who: str, model: str) -> tuple[int, int, str]:
    """Where a row stands in the table: the phases in their order, then who, then the model."""
    return _order(phase), WHO.index(who) if who in WHO else len(WHO), model


def _head(name: str, rows: list[list]) -> list[str]:
    total, unknown = _dollars(rows)
    calls = sum(int(row[3]) for row in rows)
    priced = sum(int(row[3]) for row in rows if str(row[2]) not in unknown)
    return [f"Usage of task {name}: {calls} calls of a model. Estimate at the list prices of the API of {RATES_DAY}: "
            f"{_money(total)}" + (f" for {priced} of the {calls} calls" if unknown else "")
            + ". It takes the global routing and no discount; a plan with a fixed price does not pay it. Read it as "
            "the size of each part. Each call counts in one phase, so the phases add up to the task.",
            f"{'phase':<11} {'who':<9} {'model':<24} {'rounds':>6} {'calls':>6} {'largest':>8} {'input':>7} "
            f"{'written':>8} {'read':>8} {'output':>7} {'price':>8}"]


def table(root: Path, name: str) -> list[str]:
    """`akasha usage <task>`: the usage of a task by phase, who, and model: the tokens, and an estimate at list
    prices. Each time of a phase that repairs has its own price."""
    local = next((task for task in all_local(root) if task.id == name), None)
    task_key = key(local) if local else next(
        (str(item["key"]) for item in reversed(lines(root)) if item.get("task") == name and item.get("key")), "")
    if not task_key:
        raise LookupError(f"no record of the usage of task {name} on this computer")
    kept = _kept(root, task_key, local)
    found = measure(root, task_key, kept, _usage(local)).sessions
    stats = {"sessions": {**kept, **{session: sums.stats() for session, sums in found.items() if sums.rows}}}
    rows = _rows(stats)
    said = _head(name, rows) if rows else [f"task {name} has a record, and no call of a model that Akasha could "
                                           "count yet"]
    coverage = dict(stats["sessions"])
    for session, sums in found.items():
        if session not in coverage:
            coverage[session] = sums.stats()
    missing = sum(len(sums.get("unread") or []) for sums in coverage.values())
    estimated = sum(int(sums.get("estimated_main") or 0) for sums in coverage.values())
    if missing:
        said[0] += f" {missing} unread source(s) excluded."
    if estimated:
        said[0] += f" {estimated} main call(s) assigned by time in a shared session."
    counts: dict[tuple[str, str], int] = {}
    for sums in stats["sessions"].values():
        for phase, who, many in sums.get("rounds") or []:
            counts[phase, who] = counts.get((phase, who), 0) + int(many)
    sizes: dict[tuple[str, str, str], int] = {}
    for sums in found.values():
        for where, size in sums.largest.items():
            sizes[where] = max(sizes.get(where, 0), size)
    merged: dict[tuple[str, str, str], tuple[int, ...]] = {}
    for row in rows:
        merged[row[0], row[1], row[2]] = plus(merged.get((row[0], row[1], row[2]), ZERO), row[3:9])
    for (phase, who, model), total in sorted(merged.items(), key=lambda item: _place(*item[0])):
        cost = price(model, total)
        said.append(f"{phase or '—':<11} {who:<9} {model:<24} {counts.get((phase, who)) or '—':>6} {total[0]:>6} "
                    f"{_tokens(sizes[phase, who, model]) if (phase, who, model) in sizes else '—':>8} "
                    f"{_tokens(total[1]):>7} {_tokens(total[2] + total[3]):>8} {_tokens(total[4]):>8} "
                    f"{_tokens(total[5]):>7} {_money(cost) if cost is not None else '—':>8}")
    whole, unknown = _dollars(rows)
    if whole:
        said.append("by phase: " + " · ".join(f"{phase} {_money(value)}" for phase, value in _by(rows, 0, PHASES)))
        said.append("by who: " + " · ".join(f"{who} {_money(value)} ({value * 100 / whole:.0f}%)"
                                             for who, value in _by(rows, 1, WHO)))
    for phase, costs in _fix_costs(stats).items():
        said.append(f"each {phase} ({FIXES.get(phase, 'a repair')}): "
                    + ", ".join(f"#{number} {_money(cost)}" for number, cost in costs))
    if unknown:
        said.append(f"no price: {', '.join(sorted(unknown))} (no rate in this Akasha): its tokens are in the table, "
                    "and not in the dollars")
    away = len(stats["sessions"]) - sum(1 for sums in found.values() if sums.rows)
    if away:
        said.append(f"note — {away} session(s) are from the sums that the task carries: another computer, or an "
                    "earlier count")
    for session, sums in found.items():
        said += [f"note — {note}" for note in sums.notes]
        said += [f"note — session {session[:SHORT]}: {what} is from an earlier count: its transcript is gone"
                 for what in sorted(set(sums.kept))]
        said += [f"note — session {session[:SHORT]}: {what} is an estimate from the sums of its stops: its "
                 "transcript is gone, and no count read it before" for what in sorted(set(sums.stops))]
        said += [f"note — session {session[:SHORT]}: {what} not read, so not in the sums" for what in
                 sorted(set(sums.unread))]
    return said


def retro(tasks: list[Task]) -> list[str]:
    """The lines of the retro about the usage, from the stats of the merged tasks of the team."""
    counted = [(task, _rows(_usage(task))) for task in tasks]
    counted = [(task, rows) for task, rows in counted if rows]
    said = []
    if counted:
        every = [row for _task, rows in counted for row in rows]
        total = _dollars(every)[0]
        most = sorted(((_dollars(rows)[0], task.id) for task, rows in counted), reverse=True)[:3]
        early = sum(1 for task, _rows_ in counted if _usage(task).get("cut") == LANDING)
        said.append(f"Usage of {len(counted)} merged tasks, at list prices, on average for one task: " + " · ".join(
            f"{phase} {_money(value / len(counted))}" for phase, value in _by(every, 0, PHASES))
            + ". The most: " + ", ".join(f"{name} {_money(value)}" for value, name in most)
            + (f". {early} of them are counted only up to the start of the landing" if early else ""))
        if total:
            said.append(f"The main session used {_dollars(row for row in every if row[1] == MAIN)[0] * 100 / total:.0f}"
                        "% of it: the rest is the agents")
        costs: dict[str, list[float]] = {}
        for task, _rows_ in counted:
            for phase, values in _fix_costs(_usage(task)).items():
                costs.setdefault(phase, []).extend(cost for _number, cost in values)
        if costs:
            said.append("One repair costs on average: " + " · ".join(
                f"{phase} {_money(sum(values) / len(values))} ({len(values)})"
                for phase, values in sorted(costs.items(), key=lambda item: _order(item[0]))))
    results = [int(task.stats.get("result_rounds", 0)) for task in tasks if task.stats.get("result_rounds")]
    if results:
        said.append(f"Reviews of the result: {sum(results) / len(results):.1f} rounds on average")
    return said
