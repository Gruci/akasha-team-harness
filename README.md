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

Akasha is not another agent. It runs inside the AI you already use: skills give it the team procedure, hooks stop what breaks the procedure, and stage gates hold a task until it passes. The AI asks, runs the commands, and shows the results. Akasha records each decision, gates each stage, stops what breaks the rules, and checks the result.

| | Without | With Akasha |
|:--|:--|:--|
| Team rules | Each person's AI works its own way | The administrator writes them once in `akasha.toml`.<br>Every AI on the team and the server check follow them |
| A vague request | The AI builds something else | The AI asks until the completion conditions are clear.<br>The task does not move before that |
| Technical calls | Only a developer can judge them | The AI makes them and records them.<br>People decide what to make, how it looks, and how it is used |
| Side effects | Nobody sees what else the change touches | The AI records the effect on features, data, APIs, and other tasks.<br>It also records how to reverse the change |
| "Done" | A claim | The requester tries it in a preview and accepts each condition |
| Who approved | Anybody can type a name | With GitHub, each decision is a comment from the account of the person.<br>Akasha counts only these comments |
| Months later | Nobody can find the change that broke it | One squash commit per change, with a one-minute briefing |
| Two people, one feature | One waits for the other | The second task builds on the first |
| Many computers | The work stays on the computer where it started | The issue of the task holds its state.<br>Another person, or another computer, takes the task over |

* * *

## Quick Start

**1. Administrator — once per repository**

Install the plugin, open the repository, and say **"Set up Akasha."**

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

The AI asks for:

- the administrators of the team rules
- the high-risk folders, and who must approve a change in them
- the commands that install, test, and preview the project
- the commands that make and remove a preview database, when the preview needs one

Then approve the GitHub settings. The `gh` account of your computer must administer the repository. The AI turns on the server rules for the whole team and opens a pull request with the setup files. Merge it.

Then make the GitHub app of Akasha. The setup skill tells the steps. With the app, the pull requests of the tasks come up to date by themselves.

**2. Each person — once**

Install the same plugin, and log in to GitHub with your own account: `gh auth login`. Then open the team repository. At session start, the Akasha hook checks the repository and tells the AI what it found:

| The hook finds | What happens |
|:--|:--|
| Not set up yet | The AI offers the setup of step 1 |
| Set up on the server.<br>Your checkout is old | The AI tells you to pull the default branch.<br>No second setup |
| Server rules off | The AI tells you. An administrator approves once, and the AI turns them on.<br>Work can start now. Only the handover waits |
| Ready | The AI starts work. No setup.<br>The notice also shows the tasks that you hold or requested, with the count of their new comments |

**3. Ask for a feature**

```
Add a date filter to the customer search.
```

> **NOTE:** Needs Python 3.11+, git, GitHub, and the GitHub command line `gh`. Each person needs a GitHub account that can write comments in the repository. Codex also needs `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.

* * *

## What You Get

<p align="center"><img src="docs/readme/team.en.svg" width="1000" alt="Three people work in one repository at the same time, each with their own AI. The shared task board of Akasha stacks the export button on the date filter because they are the same feature, and lets the invoice task run in parallel. GitHub merges three commits in order: #41, #42, and #43."></p>

An administrator set up the repository once. Then three people ask for changes on the same afternoon. Each person talks only to their own AI. None of them is a developer.

| Who | Asks | The shared task board |
|:--|:--|:--|
| Operations, with Claude Code | "Add a date filter to the customer search." | A new task with its own work copy |
| Finance, with Claude Code | "Show the tax on invoices." | No overlap with the date filter.<br>Both run in parallel |
| Sales, with Codex, a bit later | "Add an export button to the customer search." | The same feature as the date filter.<br>The task starts from that branch.<br>It hands over after the date filter merges |

GitHub merges three commits in order — `#41 Show the tax on invoices`, `#42 Add a date filter`, `#43 Add an export button` — each with its own briefing. Nobody waited for an answer from another person.

When two tasks overlap, Akasha applies these rules:

| Overlap | What happens |
|:--|:--|
| Same feature | The new task builds on the earlier one |
| Same files | Both tasks continue.<br>The task that merges later gets the earlier change and repairs a conflict |
| Same contract | A notice goes on the issue of the other task.<br>GitHub tells the people who follow it |

Each task also gets its own issue on the board, a map file for its feature, and its own preview port and preview database.

A task can also go to another person, or to the same person on another computer. One person on one computer holds each task, and only the holder changes it:

| Who | Says | What happens |
|:--|:--|:--|
| The holder | "Hand off the task." | The AI runs the handoff. Akasha checks the work copy for secret keys and stray files.<br>Then it saves the work on the server and frees the task |
| Another person, or the same person on another computer | "Take over the task." | The AI runs the takeover. Akasha makes a work copy from the work on the server.<br>That person holds the task now |

Akasha never forces a push. Thus old work on one computer cannot replace newer work of another person.

* * *

## How It Works

<p align="center"><img src="docs/readme/stages.en.svg" width="1000" alt="Six stages with an Akasha gate between each: request, specification, build, checks, inspection, and handover. The AI does the work of every stage. The requester answers, approves, and accepts; a developer steps in after three failed repairs; GitHub merges."></p>

| Stage | Exit condition | Who besides the AI |
|:--|:--|:--|
| Before the first task | The team rules are in `akasha.toml`.<br>The server rules are on before the first handover | The administrator, once |
| 1. Request | The completion conditions are clear | The requester answers the questions |
| 2. Specification | The impact is recorded.<br>The requester approves the current specification | The requester approves |
| 3. Build | Only files in the scope changed | — |
| 4. Checks | Each required check passes.<br>A check that the change does not touch is not needed | A developer, after three failed repairs |
| 5. Inspection | The requester accepts in a preview.<br>The map file of the feature shows the change | The requester accepts |
| 6. Handover | The server check passes.<br>One commit merges with the briefing | GitHub merges |

Small changes use the `small` workflow, defects the `fix` workflow.

With GitHub, the administrator approves a change of the GitHub settings on their own computer: Akasha asks `gh` for the account. Each other decision of a person is a comment on the issue of the task, from the GitHub account of that person:

| Decision | Comment | Who writes it |
|:--|:--|:--|
| Approve the specification | `/approve spec r<N>` | The requester |
| Approve a gated risk level | `/approve risk <level>` | A person with the gate role |
| Accept or reject a condition | `/accept <n> r<N>` or `/reject <n> r<N> <reason>` | The requester |
| Open a stopped task again | `/resume` | A developer |
| Withdraw the request | `/cancel <reason>` | The requester or a developer |

`r<N>` is the revision of the specification. A decision for an older revision does not count. When the person who decides is the `gh` account of this computer, the AI runs the Akasha command, and Akasha writes the comment with that account. Another person writes the comment on GitHub, also from a phone. Akasha does not count a typed name, the issue body, or an edited comment. Without GitHub, Akasha records the decisions on the computer.

| Layer | Enforced by |
|:--|:--|
| While working | Hooks check every command and saved file.<br>They stop what cannot be undone, like a force push.<br>They also stop a decision comment that the AI writes with `gh` |
| Before handover | The exit conditions, including a check of the briefing |
| On the server | The required check `akasha`, with the rules of the default branch.<br>A pull request cannot loosen its own rules |

* * *

## Who Does What

| Who | Does | Never has to |
|:--|:--|:--|
| **Administrator** | Sets up the repository once: the team rules in `akasha.toml`.<br>Approves changes of the GitHub settings.<br>Makes the GitHub app of Akasha | Configure each setting by hand |
| **Requester** — anyone on the team | Says what to make, how it looks, and how it is used.<br>Approves the specification and accepts the result in a preview, as a comment of their own GitHub account | Read code or judge technical risk |
| **Developer** — optional | Approves a gated risk level, when `[approval]` names one.<br>Opens a task again after three failed repairs | Watch each task |
| **The AI** — Claude Code or Codex | Asks the questions, runs the Akasha commands, and shows the results.<br>Implementation, scope, impact, and tests.<br>The briefing and the map file of the feature | Ask people technical questions |
| **Akasha** — the harness | Records each decision, gates each stage, stops what breaks the rules, and checks the result | Make a decision. People and the AI make them |

* * *

## Server Rules

GitHub's own protection comes first. Akasha's helper workflows merge and undo only where the GitHub plan has none.

| Repository | Enforced by |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | **GitHub** — branch protection, the required check, code owners, and auto-merge |
| Private on GitHub Free | **Akasha's helpers** — `akasha-merge` merges after the check passes and the code owners approve.<br>`akasha-watch` reverts a change that skipped the check, and opens an issue |

Setup tries GitHub first and records which one applies in `akasha.toml`. After a plan change, run setup again.

An administrator makes the GitHub app of Akasha once. The setup skill tells the steps. With the app, Akasha's helpers bring a pull request that is behind up to date when the default branch moves, in both cases. Thus tasks that hand over at the same time all merge, one after another. A merge of the helpers also starts your other workflows, for example a deployment.

When the server check fails on a pull request, the helpers write a comment on the pull request and on the issue of the task. With the app, they also write one when the pull request conflicts with the default branch. The AI of the holder shows these comments as news.

The server check runs on the runner and with the Python of `[ci]` in `akasha.toml`. The default is `ubuntu-latest` with Python 3.12.

> **NOTE:** GitHub stops a bad change before it merges. `akasha-watch` reverts it right after. Administrator pushes and force pushes are reported, not reverted.

* * *

## What It Guarantees — and What It Does Not

| Guaranteed | How |
|:--|:--|
| The team rules do not change without an administrator | CODEOWNERS |
| Nothing merges with a failed required check | The server rules.<br>Setup installs them, and each session start checks them again |
| A decision comes from the person who decides | With GitHub, only a decision comment from the account of that person counts.<br>The guard stops a decision comment that the AI writes with `gh` |
| Nothing the requester did not accept reaches a pull request | `feature` and `fix` hand over only with the acceptance of the requester |
| Every change can be found and reverted | One squash commit per task, with its briefing |
| Tasks do not overwrite each other | One work copy and one holder per task.<br>Tasks of the same feature stack.<br>A handoff never forces a push |

| Not guaranteed | What to know |
|:--|:--|
| A preview environment | Your project provides it. The administrator gives the commands at setup.<br>Akasha reserves a port for each task and runs the seed command. The AI starts the preview |
| A preview on another computer | The preview runs on the computer of the work copy.<br>A requester on another computer needs access to that preview. An approval works from any computer |
| A security boundary | Hooks keep a cooperating AI on the rules.<br>They are not a sandbox |
| The issue body of a task | People with write access to the repository can edit it, also the requester and the status of the task. Akasha cannot tell that edit from a write of Akasha.<br>Give write access only to the people that the team trusts. See [Roles](docs/roles.md) |
| Correct business logic | That is what the inspection is for |
| Data rollback | Reverting code does not restore data.<br>The impact record says how to reverse it |

* * *

## FAQ

| Question | Answer |
|:--|:--|
| Who can set up Akasha? | Anyone can say "Set up Akasha."<br>Only an administrator can approve the GitHub settings |
| A private repository on GitHub Free? | Yes. See [Server Rules](#server-rules) |
| A team with no developer? | Yes. The AI makes the technical calls, and the server check stops a failing change.<br>A team with developers can add a person gate for data or permissions |
| Does the requester need a terminal? | Only once, for the GitHub login: `gh auth login`.<br>Then they ask in the desktop app, and the AI runs the commands |
| Does each requester need a GitHub account? | Yes, when the repository is on GitHub. Each decision is a comment from the account of that person.<br>In a private repository, the account needs access to the repository |
| Can a requester approve from a phone? | Yes. The requester writes the comment that Akasha shows on the issue of the task.<br>To accept, the requester needs the preview |
| Can I continue a task on another computer? | Yes. Say "Hand off the task" on the first computer.<br>Then say "Take over the task" on the other computer |
| Two people change the same feature? | The second task builds on the first.<br>If it changes behavior that the first requester accepted, Akasha leaves that person a notice on GitHub |
| A frontend and a backend in one repository? | Give each part its own check in `[checks.<name>]`, with its folder and its files.<br>A check runs only when the change touches its files |
| The repository already has its own hooks, branches, or folders? | Akasha keeps the other hooks of Codex and the other text of `AGENTS.md`.<br>`[work]` in `akasha.toml` sets another work folder and other branch prefixes |
| How do I revert a change? | Find its commit on the default branch, and read the briefing.<br>Then revert that one commit |

* * *

## Details

You do not need these to get started — the AI handles them.

<details>
<summary><b>The team config — the sections of <code>akasha.toml</code></b></summary>

The administrators own `akasha.toml`. Each command of a task reads it from the default branch on the server, so each computer uses the rules that the administrators merged. [Team config](docs/team-config.md) tells each key.

| Section | Holds |
|:--|:--|
| `[roles]` | The GitHub names of the developers and the administrators |
| `[risk]` | The file patterns of high-risk and medium-risk code |
| `[approval]` | The person gates for each risk level. By default, there is none |
| `[checks]` | The required checks and the setup command.<br>`[checks.<name>]` gives one check its command, its folder, and the files that it examines |
| `[preview]` | The preview command and the name of the preview database.<br>Also the commands that make and remove the database of a task |
| `[contracts]` | The public contracts, for example an API that other teams use |
| `[workflows]` | The workflows that new requests can use |
| `[server]` | Who enforces the server rules: GitHub or the helpers of Akasha. Setup writes it |
| `[ci]` | The runner and the Python of the server check |
| `[context]` | The folder of the product map. The default is `.akasha/context/map` |
| `[work]` | The folder of the work copies and the prefixes of the task branches |

> **CAUTION:** An Akasha that is not updated refuses `[checks.<name>]`, `[ci]`, `[context]`, `[work]`, and the new keys of `[checks]` and `[preview]`. Make sure that each person updated Akasha before you add them. The first row of *When Akasha stops a step* tells how.

</details>

<details>
<summary><b>When Akasha stops a step</b></summary>

The AI tells you each message in simple words. These are the most frequent:

| Akasha says | What to do |
|:--|:--|
| A file of the server rules is different from the Akasha on this computer | Update Akasha. The version stays 1.0.0, so `/plugin update` and a plain `pip install` keep the old copy.<br>Claude Code: close it, remove the folder `.claude/plugins/cache/akasha` in your home folder, run `claude plugin install akasha@akasha` in a terminal, and open Claude Code again.<br>Codex: `pip install --force-reinstall "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.<br>If the file is still different, an administrator sets up Akasha again |
| It cannot read the shared task board, or your GitHub name | Log in to GitHub: `gh auth login`. Then do the step again.<br>If Akasha says that it saved or recorded the task, continue with that task: do not ask for it again. When `gh` works again, the AI runs the command that Akasha shows |
| It cannot fetch the default branch | Make sure that the network works and that git can log in to the server |
| Another person holds the task | Ask that person to hand off the task. Then take it over |
| You hold the task in another copy of the repository | Hand it off there. Then take it over here |
| Another computer changed the task | Do the step again. Akasha reads the new state first |
| A person must write a comment | That person writes the comment that Akasha shows on the issue, with their own GitHub account |
| The requester has no access to the private repository | An administrator gives the requester access |
| The earlier task was cancelled | The AI stops building on it, and removes the changes that the task does not need |
| The task has a pull request, so its specification cannot change | Make a new request |

</details>

<details>
<summary><b>Under the hood — eight parts in four areas</b></summary>

| Area | Part | Function |
|:--|:--|:--|
| Work procedure | Core | Task state, stage moves, and the pull request briefing |
| Work procedure | Workflow | The stages and exit conditions of `feature`, `fix`, and `small` |
| Work procedure | Skills and context | The procedures, the product map with one file for each feature, and the decisions of your team |
| Work procedure | Validators | Each rule that a machine can examine, as a check |
| Work procedure | Team config | The team rules in `akasha.toml` |
| Agent engine | Agent engine | Loads the hooks and skills into Claude Code or Codex |
| Coordination | Coordinator | The shared task board, handoffs and takeovers, overlap checks, stacked tasks, and preview resources |
| Infrastructure control | Infrastructure manager | Keeps the server rules the same as the team config, with the merge, watch, and update helpers |

```
akasha/
├── core/          task state, stages, risk, work copies, pull request text
├── workflows/     feature · fix · small
├── validators/    guard, secret check, check runner, briefing check, language packs
├── coordinator/   shared task board, overlap checks, preview resources
├── infra/         GitHub settings, merge, watch, and update helpers, workflow templates
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
