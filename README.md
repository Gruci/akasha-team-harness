**English** | [한국어](README.ko.md)

<div align="center">

<img src="docs/readme/banner.svg" width="860" alt="Akasha lets your whole team build one product with AI: sales, operations, finance, and developers.">

<h3>Your whole team can build with AI,<br>without the product drifting.</h3>

When people who don't code build with AI on their own, the product drifts:<br>
odd results, and changes nobody asked for.<br>
With Akasha, each person approves one preview, and only that gets built, under your team's rules.

<img src="https://img.shields.io/badge/version-1.1.5-7c3aed" alt="Version 1.1.5">
<a href="#license"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT license"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11 or later">
<img src="https://img.shields.io/badge/engines-Claude%20Code%20%C2%B7%20Codex-111827" alt="Engines: Claude Code and Codex">

[How It Works](#how-it-works) · [How You Use It](#how-you-use-it) · [Quick Start](#quick-start) · [Many People](#many-people-at-the-same-time) · [Docs](docs/README.md)

</div>

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

* * *

## How It Works

<img src="docs/readme/with-and-without.svg" width="900" alt="Same request, same AI, different result. Without Akasha, the AI builds what it guessed, changes other screens on its own, breaks something that used to work, and goes live with nobody checking. With Akasha, the person approves exactly what they will get, only that gets built, changes to shared parts wait for a developer, and it goes live only when the team's checks pass.">

Many people can do this at the same time without stepping on each other: [see how](#many-people-at-the-same-time).

* * *

## How You Use It

| 1 · Say what you want | 2 · Check the preview | 3 · It goes live |
|:--|:--|:--|
| In Claude Code or Codex, in your own words | It opens in your browser: the screen, and where each number comes from | When your team's checks pass. You get a short note of what changed |
| *"Add a monthly fee total to the board."* | *"Build it like this."* | *"Live. Monthly fee total added."* |

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
> CLI `gh`. Codex also needs `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.1.5"` in that Python
> (on Windows `py -3 -m pip install …`).

* * *

## Under the Hood

Each task goes through six steps, and many tasks go through them at once:

| Step | Who | Gate |
|:--|:--|:--|
| 1.&nbsp;Request | The person says what they want | — |
| 2.&nbsp;Preview | The AI makes a preview: the look, the values, the rules. The person checks it | The person approves it in the chat |
| 3.&nbsp;Plan | The AI writes research and a plan | A second AI checks it until it passes |
| 4.&nbsp;Build | The AI changes the code in its own copy | No code before steps 2 and 3 |
| 5.&nbsp;Check | The checks of the team run | Each required check passes |
| 6.&nbsp;Land | The pull request comes up to date and merges | The checks pass on GitHub |

The hooks hold the AI on these steps.

- They keep the message of the person for the approval, and record the verdict of the second AI.
- They stop a change of the code before the gates.
- They stop a change in the main checkout, or in a work copy outside Akasha.
- They stop a force push, a push to the default branch, and a merge by hand.
- The same rules hold for a session in another folder that changes this repository or uses `git -C`.

[How it works](docs/how-it-works.md) tells each detail.

* * *

## Many People at the Same Time

<img src="docs/readme/how-it-works.svg" width="1000" alt="Several teams and an agent ask at the same time. Each person only approves a preview; the person who asked the agent approves its result before the merge. For each task an AI plans, a second AI checks the plan, the AI builds and tests. When two tasks plan the same file, each AI reads the other's change first. The tasks merge into one product one by one, and each later one is first updated from main and checked again.">

Each person, from any team, works on their own task at the same time as the others.

| Situation | What happens |
|:--|:--|
| A new task plans the files of open tasks | The board shows those tasks and who holds them, and the AI reads what they change before it plans |
| Tasks change the same file | Each AI hears of it. Each task keeps its own pull request: the later one takes the change, and its AI resolves a conflict and checks again |
| Several tasks are ready at once | They merge one by one, each up to date first |
| A person stops, and another continues | `handoff` frees the task, `resume` continues it anywhere |
| A task name is in use | The start refuses it, and the AI picks another |
| The AI is stuck | It asks the administrators on the pull request |

* * *

## Who Does What

A team has three roles: the administrators, the teammates, and the agent accounts.

| Who | Does | Does not have to |
|:--|:--|:--|
| **Administrator** | Sets up and maintains Akasha, the database, and the deployment | Review any task |
| **Teammate** | Says what to make, and approves the preview | Read code or review plans |
| **Agent account** | A program runs it, for example an operations agent: it works from the request of a person, and that person approves the result before the merge | Make a preview |

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
| The person approves a specification, not only a picture | Akasha refuses a preview without rules, or with a value from data that has no source, formula, value, and check |
| The code waits for the approval and the plan check | The guard stops each edit of the code before both |
| A change that failed the checks does not merge | The required checks must really run and pass on GitHub |
| Only an administrator changes the risky parts | A teammate's task stops at the database or the deployment |
| Each change can be found and undone | One squash commit with its summary and records |

| Does not guarantee | Know this |
|:--|:--|
| A sandbox | The hooks keep a cooperative AI on the steps |
| The meaning of an approval | The AI judges it. The pull request names who approved and when; the exact words stay on the computer of the session (`.akasha/state`) |
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
| **v1.1.5** | Who approved, not what they typed |
| **v1.1.4** | Pinned team version · lighter plan review |
| **v1.1.3** | Developer mode · plan approval without a screen · dated records |
| **v1.1.2** | Work copies in `.claude/worktrees/` |
| **v1.1.1** | Preview as spec |
| **v1.1.0** | Agent accounts |
| **v1.0.0** | First release |

* * *

<div align="center">

*People decide what to make, once, on what they can see. The AI decides how. Each change keeps one clear record.*

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/) · MIT License

</div>
