**English** | [한국어](README.ko.md)

<div align="center">

◯ ───────────────────────────────── ◯

<img src="docs/readme/banner.svg" width="860" alt="Akasha lets any person on your team build one product with an AI agent.">

**A K A S H A**

◯ ───────────────────────────────── ◯

**A team harness for Claude Code and Codex.**

Anyone on the team asks for a feature in plain words. The AI asks, builds, and makes the technical calls —<br>
Akasha keeps it on one procedure until the change merges as one checked, accepted commit.

<img src="https://img.shields.io/badge/version-1.0.0-7c3aed" alt="Version 1.0.0">
<a href="#license"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT license"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11 or later">
<img src="https://img.shields.io/badge/engines-Claude%20Code%20%C2%B7%20Codex-111827" alt="Engines: Claude Code and Codex">

[Quick Start](#quick-start) · [Why](#why-akasha) · [How It Works](#how-it-works) · [Who Does What](#who-does-what) · [Server Rules](#server-rules) · [Docs](docs/README.md)

</div>

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

* * *

## Why Akasha

Akasha is not another agent. It runs inside the AI you already use: skills give it the team procedure, hooks stop what breaks the procedure, and stage gates hold a task until it passes.

| | Without | With Akasha |
|:--|:--|:--|
| A vague request | The AI builds something else | The AI asks until the completion conditions are clear. The task does not move before that |
| Technical calls | Only a developer can judge them | The AI makes them and records them. People decide what to make, how it looks, and how it is used |
| Side effects | Nobody sees what else the change touches | The AI records the effect on features, data, APIs, and other tasks, and how to reverse it |
| "Done" | A claim | The requester tries it in a preview and accepts each condition |
| Months later | Nobody can find the change that broke it | One squash commit per change, with a one-minute briefing |
| Two people, one feature | One waits for the other | The second task builds on the first |

* * *

## Quick Start

**1. Install** — each person, once:

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

**2. Open the team repository.** At session start, the Akasha hook checks it on GitHub and tells the AI what it found:

| The hook finds | What happens |
|:--|:--|
| Team rules and server rules on | The AI starts work. No setup |
| No `akasha.toml` yet | Say **"Set up Akasha."** The AI asks for the administrators, the high-risk folders, and the preview command |
| Server rules off | The AI tells you. An administrator approves once, and the AI turns them on for the whole team. Work can start now; only the handover waits |

**3. Ask for a feature:**

```
Add a date filter to the customer search.
```

> **NOTE:** Needs Python 3.11+, git, and GitHub. Codex also needs `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.

* * *

## What You Get

<p align="center"><img src="docs/readme/one-request.en.svg" width="1000" alt="One request from someone in operations, start to merge. The AI asks which date and whether customers without permission are visible, records the impact, builds the change with a test per condition in its own work copy, and shows a preview that the requester accepts. GitHub merges one commit with the briefing. The AI works inside the Akasha harness, whose gates hold each step."></p>

* * *

## How It Works

<p align="center"><img src="docs/readme/stages.en.svg" width="1000" alt="Six stages with an Akasha gate between each: request, specification, build, checks, inspection, and handover. The AI does the work of every stage. The requester answers, approves, and accepts; a developer steps in after three failed repairs; GitHub merges."></p>

Small changes use the `small` workflow, defects the `fix` workflow.

| Layer | Enforced by |
|:--|:--|
| While working | Hooks check every command and saved file, and stop what cannot be undone, like a force push |
| Before handover | The exit conditions, including a check of the briefing |
| On the server | The required check `akasha`, run with the rules of the default branch — a pull request cannot loosen its own rules |

* * *

## Who Does What

| Who | Does | Never has to |
|:--|:--|:--|
| **Requester** — anyone on the team | Says what to make, how it looks, and how it is used. Tries the preview | Read code or judge technical risk |
| **The AI** — Claude Code or Codex | Implementation, scope, impact, tests, briefing, and product map | Ask people technical questions |
| **Administrator** | Writes the team rules in `akasha.toml` once. Approves changes of the GitHub settings | Configure each setting by hand |

* * *

## Server Rules

GitHub's own protection comes first. Akasha's helper workflows fill in only where the GitHub plan has none.

| Repository | Enforced by |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | **GitHub** — branch protection, the required check, code owners, and auto-merge |
| Private on GitHub Free | **Akasha's helpers** — `akasha-merge` merges after the check passes. `akasha-watch` reverts a change that skipped it and opens an issue |

Setup tries GitHub first and records which one applies in `akasha.toml`. After a plan change, run setup again.

> **NOTE:** GitHub stops a bad change before it merges. `akasha-watch` reverts it right after. Administrator pushes and force pushes are reported, not reverted.

* * *

## What It Guarantees — and What It Does Not

| Guaranteed | How |
|:--|:--|
| Nothing merges with a failed required check | The server rules. Setup installs them; each session start checks them again |
| The team rules do not change without an administrator | CODEOWNERS |
| Nothing the requester did not accept reaches a pull request | `feature` and `fix` need the acceptance record to hand over |
| Every change can be found and reverted | One squash commit per task, with its briefing |
| Tasks do not overwrite each other | One work copy per task. Tasks of the same feature stack |

| Not guaranteed | What to know |
|:--|:--|
| Correct business logic | That is what the inspection is for |
| Data rollback | Reverting code does not restore data. The impact record says how to reverse it |
| A security boundary | Hooks keep a cooperating AI on the rules. They are not a sandbox |
| A preview environment | Your project provides it. The AI starts it with your command |

* * *

## FAQ

| Question | Answer |
|:--|:--|
| A team with no developer? | Yes. The AI makes the technical calls, and the server check stops a failing change. A team with developers can add a person gate for data or permissions |
| Does the requester need a terminal? | No. They ask in the desktop app. The AI runs the commands |
| Two people change the same feature? | The second task builds on the first. If it changes behavior that the first requester accepted, Akasha leaves that person a notice on GitHub |
| How do I revert a change? | Find its commit on the default branch, read the briefing, and revert that one commit |
| A private repository on GitHub Free? | Yes. See [Server Rules](#server-rules) |

* * *

## Details

You do not need these to get started — the AI handles them.

<details>
<summary><b>Under the hood — eight parts in four areas</b></summary>

| Area | Part | Function |
|:--|:--|:--|
| Work procedure | Core | Task state, stage moves, and the pull request briefing |
| Work procedure | Workflow | The stages and exit conditions of `feature`, `fix`, and `small` |
| Work procedure | Skills and context | The procedures, the product map, and the decisions of your team |
| Work procedure | Validators | Each rule that a machine can examine, as a check |
| Work procedure | Team config | The team rules in `akasha.toml` |
| Agent engine | Agent engine | Loads the hooks and skills into Claude Code or Codex |
| Coordination | Coordinator | The shared task board, overlap checks, and stacked tasks |
| Infrastructure control | Infrastructure manager | Keeps the server rules the same as the team config |

```
akasha/
├── core/          task state, stages, risk, work copies, pull request text
├── workflows/     feature · fix · small
├── validators/    guard, secret check, check runner, briefing check, language packs
├── coordinator/   shared task board, overlap checks, preview resources
├── infra/         GitHub settings, merge and watch helpers, workflow templates
└── engine/        hooks for Claude Code and Codex
skills/            akasha-setup · akasha-request · akasha-inspect · akasha-handover
```

</details>

* * *

## Changelog

| Version | Changes |
|:--|:--|
| **v1.0.0** | First public release. |

* * *

<div align="center">

*People decide what to make. The AI decides how. Each change leaves one clear record.*

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/) · MIT License

</div>
