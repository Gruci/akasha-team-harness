**English** | [한국어](README.ko.md)

<div align="center">

◯ ───────────────────────────────── ◯

<img src="docs/readme/banner.svg" width="860" alt="Akasha lets any person on your team build one product with an AI agent.">

**A K A S H A**

◯ ───────────────────────────────── ◯

**Anyone on the team builds one product. The AI makes the technical decisions.**

A team harness for Claude Code and Codex. People decide what to make, how it looks, and how people use it.<br>
Akasha makes the AI record each technical decision, checks the result, and merges each change as one clear commit.

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

Each person on the team installs Akasha one time. Then open the team repository and ask for a feature.

* * *

## Why Akasha

AI agents write code for anyone. In a team, the problem is not the code. It is everything around the code.

| Without Akasha | With Akasha |
|:--|:--|
| Only developers can judge the technical effects of a change | **The AI decides and records.** People decide what to make, how it looks, and how people use it |
| The request is not clear, so the AI makes a different feature | **Akasha asks first.** It asks questions until the completion conditions are clear |
| The AI says "Done," and nobody knows if it is correct | **The requester inspects.** The requester examines the feature in a preview and accepts it |
| A change touches other features or data, and nobody sees it | **The AI finds the effects.** It records the effects on features, data, APIs, and other tasks, and how to reverse the change |
| Later, nobody can find the change that caused a problem | **One commit, one briefing.** Each change merges with a one-minute briefing: why, scope, blast radius, and verification |
| Two people change the same feature and wait for each other | **Nobody waits.** The second task builds on the first |

* * *

## Quick Start

**1. Install.** Each person, one time:

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

**2. Open the team repository.** Akasha examines it on GitHub first:

| What Akasha finds | What occurs |
|:--|:--|
| The team rules and the server rules are on | Akasha is ready. Nobody does a setup |
| The repository does not use Akasha yet | Say **"Set up Akasha."** Akasha asks about the administrators, the high-risk areas, and the preview command |
| The server rules are off | Akasha tells you. A repository administrator turns them on one time, for the whole team |

**3. Ask for a feature** in plain words:

```
Add a date filter to the customer search.
```

> **NOTE:** You need Python 3.11 or later, git, and GitHub. Codex also needs `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.

* * *

## What You Get

One request from an operations team member, who is not a developer:

```
requester  ─►  "Add a date filter to the customer search."
Akasha     ─►  "Which date: the sign-up date or the transaction date?"
               "Must customers without permission be visible?"
the AI     ─►  finds that two reports also read the customer table
               records: adds an index, changes no data, revert the commit to reverse
the AI     ─►  builds the change and a test for each condition, in its own work copy
Akasha     ─►  runs the checks ─► shows a preview ─► the requester accepts
GitHub     ─►  merges one commit: "Add a date filter (#42)" with the briefing
```

The requester wrote no code and made no technical decision. Nobody explained the procedure.

* * *

## How It Works

Each task goes through six stages. A task goes to the next stage only when it meets the exit condition.

```
request ──► specification ──► build ──► checks ──► inspection ──► handover
   │              │              │          │            │             │
 clear          impact        files in    checks      accepted       merged
 conditions     recorded      the scope   pass        + map shows
                                                      the change
```

| Stage | Exit condition |
|:--|:--|
| 1. Request | The completion conditions are clear |
| 2. Specification and impact | The requester approves. The AI recorded the effects on features, data, APIs, and other tasks, and how to reverse the change |
| 3. Build | The change uses only the files in its scope |
| 4. Checks and repair | All required checks pass. After three failed repairs, Akasha stops and tells a developer in simple words |
| 5. Inspection | The requester accepts the result in a preview. The product map shows the change. The server rules are on |
| 6. Handover | The server check passes, and the change merges as one commit with the briefing |

A small change uses the `small` workflow. A defect uses the `fix` workflow.

Three layers enforce the procedure:

| Layer | What enforces it |
|:--|:--|
| During the work | Hooks examine each command and each saved file. They stop a command that you cannot undo, for example a force push |
| Before the handover | The exit conditions. The briefing must also pass its check |
| On the server | The required check `akasha` runs with the rules of the default branch, so a pull request cannot make its own rules weaker |

* * *

## Who Does What

| Who | Does | Does not need to |
|:--|:--|:--|
| **Requester** — any team member, a developer or not | Tells what to make, how it looks, and how people use it. Examines the preview | Read code, decide the implementation, or judge the technical risk |
| **The AI** — Claude Code or Codex | Decides the implementation, the scope, and the impact. Writes the tests, the briefing, and the product map | Ask people technical questions |
| **Administrator** | Writes the team rules in `akasha.toml` one time. Approves changes of the GitHub settings | Configure each repository setting by hand |

Akasha asks people only what to make, how it looks, and how they use it.

* * *

## Server Rules

GitHub's own branch protection and auto-merge come first. Akasha's helpers fill the gap only where the GitHub plan has none.

| Repository | Who enforces the rules |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | **GitHub** — branch protection, the required check, code owners, and auto-merge |
| Private on GitHub Free | **Akasha's helpers** — `akasha-merge` merges a pull request after the check passes. `akasha-watch` undoes a change that went around the check and opens an issue |

The setup tries GitHub's protection first and records the result in `akasha.toml`. The helpers are always installed, and they do nothing while GitHub protects the default branch. Thus a repository that changes its plan changes its rules with one setup.

> **NOTE:** GitHub protection stops a bad change before it merges. `akasha-watch` undoes it right after it arrives. It reports a push of an administrator and a force push, and it does not undo them.

* * *

## Under the Hood

Akasha has eight parts in four areas.

| Area | Part | Function |
|:--|:--|:--|
| Work procedure | Core | Keeps the state of each task, moves it between stages, and writes the pull request briefing |
| Work procedure | Workflow | Declares the stages and the exit conditions: `feature`, `fix`, and `small` |
| Work procedure | Skills and context | Contain the procedures, the product map, and the decisions of your team |
| Work procedure | Validators | Change each rule that a machine can examine into a check |
| Work procedure | Team config | Holds the team rules in `akasha.toml` |
| Agent engine | Agent engine | Operates Claude Code or Codex with the hooks and skills of Akasha |
| Coordination | Coordinator | Keeps the shared task board, finds overlaps, and stacks the tasks of one feature |
| Infrastructure control | Infrastructure manager | Examines the server rules and keeps them the same as the team config |

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

* * *

## What Akasha Guarantees

| Guaranteed | How |
|:--|:--|
| A change that fails a required check does not merge | The server rules stop it. Akasha installs and monitors them |
| A change of the team rules does not merge without an administrator | CODEOWNERS gives the team rules to the administrators |
| A feature that the requester did not accept does not go to a pull request | In the `feature` and `fix` workflows, the handover needs the acceptance record |
| You can find and revert each change | Each task merges as one squash commit with its briefing |
| Two tasks do not write over each other | Each task has a separate work copy. A task of the same feature builds on the earlier task |

| Not guaranteed | Reason |
|:--|:--|
| Correct business logic | The inspection must examine it |
| Data reversal | A revert of the code does not restore data. The impact analysis records how to reverse a data change |
| A security boundary | The local checks keep a cooperative AI on the rules. They are not a sandbox |
| A preview environment | Your project supplies it. Akasha starts it with your command |

* * *

## FAQ

| Question | Answer |
|:--|:--|
| Can a team without a developer use Akasha? | Yes. The AI makes the technical decisions, and the server check stops a change that fails. A team with a developer can add a person gate for data or permissions |
| Must a requester use a terminal? | No. The requester asks in the desktop app. Akasha runs the commands |
| Two people want to change the same feature. What occurs? | The second task builds on the first, so nobody waits. If it changes behavior that the first requester accepted, Akasha tells that person on GitHub |
| How do I revert a change? | Find its commit on the default branch. The briefing tells why, the scope, and the blast radius. Revert that one commit |
| Does a private repository on GitHub Free work? | Yes. Akasha's merge and watch helpers enforce the rules. See [Server Rules](#server-rules) |

* * *

## Changelog

| Version | Changes |
|:--|:--|
| **v1.0.0** | Eight parts. The `feature`, `fix`, and `small` workflows. AI impact analysis and the product map. Inspection with a preview. A one-minute briefing and auto-merge as one commit. A shared task board with stacked tasks. Server rules by GitHub, or by Akasha's merge and watch helpers on GitHub Free. Claude Code and Codex. Four language packs. Plugin install. |

* * *

<div align="center">

*People decide what to make. The AI decides how. Each change leaves one clear record.*

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/) · MIT License

</div>
