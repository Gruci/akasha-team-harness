**English** | [한국어](README.ko.md)

<div align="center">

◯ ───────────────────────────────── ◯

<img src="docs/readme/banner.svg" width="860" alt="Akasha lets any person on your team build one product with an AI agent.">

**A K A S H A**

◯ ───────────────────────────────── ◯

**A light team harness for Claude Code and Codex.**

Each person asks for a change in plain words<br>
and approves a preview of it. That is their only step.

The AI plans, a second AI checks the plan,<br>
and the AI builds, checks, and lands the change.

<img src="https://img.shields.io/badge/version-1.0.0-7c3aed" alt="Version 1.0.0">
<a href="#license"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT license"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11 or later">
<img src="https://img.shields.io/badge/engines-Claude%20Code%20%C2%B7%20Codex-111827" alt="Engines: Claude Code and Codex">

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [Many People](#many-people-at-the-same-time) · [Server Rules](#server-rules) · [Docs](docs/README.md)

</div>

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

* * *

## Why Akasha

Today the AI writes most of the code, and few people read it.<br>
The human check that still matters is the one at the start: is this what we want?<br>
Akasha puts the person there, and puts machines everywhere else.

| | Without | With Akasha |
|:--|:--|:--|
| What the person checks | A technical plan, or nothing | A preview they can see: a mockup or a diagram |
| The plan | Nobody reads it | A second AI checks it until it passes |
| The approval | The AI can write "approved" | Only words that the person typed, kept as typed |
| Many people | Nobody sees the others | The open pull requests are the board |
| "Done" | A claim | The checks pass on GitHub, then one commit |
| Months later | Nobody knows why | The preview, plan, and summary stay with it |

* * *

## Quick Start

**1. The administrator — once per repository**

Install the plugin, open the repository, and say **"Set up Akasha"**. Then the AI

- asks for the administrators, the risky parts, the check commands, what each computer needs, and the team documents
- lines up the own agent rules of the repository with Akasha
- sets up GitHub, and opens a pull request with the files. Merge it after its checks pass.

**2. Each teammate — once**

Install the plugin, log in with `gh auth login`, and open the repository.<br>
The repository already registers the plugin. If something is missing, the AI tells you.

**3. Ask for a change**

```
Add a button that downloads the order list as a CSV file.
```

The AI asks until it is clear, then opens a preview in the browser.<br>
Approve it in your own words, in any language, or tell what to change.<br>
The AI does the rest, and tells you when the change is merged and when it is live.

> **NOTE:** Python 3.11 or later (the hooks find it as `py -3`, `python3`, or `python`), git, GitHub, and the GitHub
> CLI `gh`. Codex also needs `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"` in that Python
> (on Windows `py -3 -m pip install …`).

* * *

## How It Works

<p align="center"><img src="docs/readme/stages.en.svg" width="1000" alt="Six steps with an Akasha gate between each: request, preview, plan, build, check, and land. The AI does the work of every step. The person asks and approves the preview; a second AI checks the plan; an administrator helps when the AI is stuck; the tasks merge one by one."></p>

| Step | Gate | Who besides the AI |
|:--|:--|:--|
| Before the first task | The setup of Akasha merged:<br>`akasha.toml` and the GitHub settings | The administrator, once |
| 1. Request | The AI knows what the person wants | The person says it in their own words |
| 2. Preview | The person approved the preview in the chat | The person approves |
| 3. Plan | A second AI passed the research and the plan | A second AI checks it |
| 4. Build | No code before steps 2 and 3.<br>The code changes in the own copy of the task | — |
| 5. Check | Each required check passes | An administrator, when the AI is stuck |
| 6. Land | The pull request is up to date, and the checks pass on GitHub.<br>One squash commit merges with the summary | GitHub, or Akasha on GitHub Free |

The person approves only in the chat, in their own words. A hook keeps the message, so the AI cannot make up an approval. When the preview changes, it needs a new approval.

| Layer | Enforced by |
|:--|:--|
| While working | Hooks check every command and saved file.<br>They stop a change of the code before the gates, and a change outside the copy of the task.<br>They stop a force push, a push to the default branch, and a merge by hand |
| Before landing | The approval, the passed plan, passed checks, and the summary |
| On GitHub | The checks of the team, with the rules of the default branch.<br>A pull request cannot loosen its own rules |

[How it works](docs/how-it-works.md) tells each detail.

* * *

## Many People at the Same Time

Each person, from any team, works on their own task at the same time as the others.

| Situation | What happens |
|:--|:--|
| A new task plans the files of open tasks | The board shows those tasks and who holds them |
| Tasks change the same file | Each AI hears of it, and the later task takes the change |
| Several tasks are ready at once | They merge one by one, each up to date first |
| A person stops, and another continues | `handoff` frees the task, `resume` continues it anywhere |
| A task name is in use | The start refuses it, and the AI picks another |
| The AI is stuck | It asks the administrators on the pull request |

* * *

## Who Does What

A team has two roles: the administrators, and the teammates.

| Who | Does | Does not have to |
|:--|:--|:--|
| **Administrator** | Sets up and maintains Akasha, the database, and the deployment | Review any task |
| **Teammate** | Says what to make, and approves the preview | Read code or review plans |

Each person keeps their own agent settings (`.claude/settings.local.json`, `CLAUDE.local.md`) out of git, so each
person can tune the harness freely.

* * *

## Server Rules

| Repository | What stops a bad merge |
|:--|:--|
| Public, or private on a paid GitHub plan | **GitHub**: branch protection and the required checks |
| Private on GitHub Free | **Akasha**: merges only after the checks pass |

- On GitHub Free, a watch workflow also reports each change that went around the rules.
- The setup tries GitHub first, and records which one applies.
- Before each landing Akasha asks GitHub again, and merges itself where the protection is weak.
- The merge comes from the account of the person, so the workflows after it start, for example a deployment.
- With `[deploy] workflow`, Akasha waits for the deployment and tells when the change is live.

* * *

## What Akasha Guarantees, and What It Does Not

| Guarantees | How |
|:--|:--|
| An approval comes from the person | Only words typed in the session that showed the preview |
| The code waits for the approval and the plan check | The guard stops each edit of the code before both |
| A change that failed the checks does not merge | The required checks must really run and pass on GitHub |
| Only an administrator changes the risky parts | A teammate's task stops at the database or the deployment |
| Each change can be found and undone | One squash commit with its summary and records |

| Does not guarantee | Know this |
|:--|:--|
| A sandbox | The hooks keep a cooperative AI on the steps |
| The meaning of an approval | The AI judges it. The pull request shows the exact words |
| Protection before a merge on GitHub Free | A person can merge by hand. The watch reports it |
| The business logic | The preview, the plan check, and the checks examine it |
| The data | Undoing code does not undo data. Mark the database risky |

* * *

## More

| | |
|:--|:--|
| [How it works](docs/how-it-works.md) | The steps, the gates, the landing, and where Akasha keeps its data |
| [Set up a team](docs/admin.md) | The setup, the server rules, a team with its own CI, the retro |
| [Team config](docs/team-config.md) | Each key of `akasha.toml` |
| [Commands](docs/commands.md) | Each command of Akasha |

* * *

## Changelog

| Version | Changes |
|:--|:--|
| **v1.0.0** | First release. |

* * *

<div align="center">

*People decide what to make, once, on what they can see. The AI decides how. Each change keeps one clear record.*

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/) · MIT License

</div>
