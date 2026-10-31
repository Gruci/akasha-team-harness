# Architecture

This document tells how the parts of Akasha connect, where Akasha keeps its data, and which commands the agent engine runs.

## The principle

People decide what to make, how it looks, and how people use it. The agent engine makes the technical decisions: the implementation, the scope, the impact on other features and data, and the order of the work between tasks. Akasha makes the agent engine record each decision, checks the result, and merges it as one commit that a person can find and revert.

## Four areas and eight parts

| Area | Part | Location | Function |
|:--|:--|:--|:--|
| Work procedure | Core | `akasha/core/`, `akasha/flow.py` | Keeps the state of each task, moves the task between stages, and writes the pull request text |
| Work procedure | Workflow | `akasha/workflows/`, `.akasha/workflows/` | Declares the stages and the exit conditions |
| Work procedure | Skills and context | `skills/`, `.akasha/context/` | Give the procedures to the agent engine, and give it the product map and the decisions of your team |
| Work procedure | Validators | `akasha/validators/` | Change each rule that a machine can examine into a check |
| Work procedure | Team config | `akasha.toml`, `akasha/config.py` | Holds the team rules for one repository |
| Agent engine | Agent engine | `akasha/engine/`, `.claude-plugin/` | Connects Claude Code and Codex to Akasha with hooks, skills, and session rules |
| Coordination | Coordinator | `akasha/coordinator/` | Keeps the shared task board, finds overlaps, stacks tasks of one feature, and gives each preview its own resources |
| Infrastructure control | Infrastructure manager | `akasha/infra/` | Keeps the required check, branch protection, auto-merge, and CODEOWNERS the same as the team config |

The core is the same in all teams. A team changes the workflows, the skills and context, and the team config.

## The path of one task

```mermaid
flowchart LR
    R([Requester]) --> E[Agent engine]
    E --> C[Core]
    C <--> B[Coordinator]
    C --> V[Validators]
    C --> I[Infrastructure manager]
    I --> G([GitHub merges])
```

1. The requester tells the agent engine what to make.
2. The agent engine records the task. The coordinator compares it with the tasks of all requesters.
3. The agent engine asks questions until the completion conditions are clear.
4. The agent engine reads the map file of the feature, finds the effects of the change, and records the impact analysis.
5. The requester approves the specification in simple words. With GitHub, the requester writes a decision comment on the issue of the task.
6. The core makes a work copy. The agent engine builds the change and a test for each completion condition.
7. The validators run the required checks. A check with `only_when` runs only when the change touches its files. When each check passes or is not needed, Akasha saves the work and pushes the task branch.
8. The requester examines the result in a preview and accepts it, with GitHub also in a decision comment.
9. The agent engine updates the map file of the feature and writes the briefing.
10. Akasha opens the pull request, and turns on auto-merge where GitHub merges. GitHub merges it as one squash commit when the server check passes and the code owners of its files approved. Where the GitHub plan has no auto-merge, the merge helper of Akasha merges it.

## Where Akasha keeps its data

| Data | Location | In git |
|:--|:--|:--|
| Team rules | `akasha.toml` | Yes |
| Team workflows | `.akasha/workflows/*.toml` | Yes |
| Team context | `.akasha/context/*.md` | Yes |
| Product map | One file for each feature key in `.akasha/context/map/`, or in the folder of `[context] map`. Akasha 1.0.0 had one file, `.akasha/context/product-map.md`, and it stays | Yes |
| Server files | `.github/workflows/akasha.yml`, `akasha-merge.yml`, `akasha-watch.yml`, the Akasha block of CODEOWNERS, `.github/pull_request_template.md` | Yes |
| Branch protection and repository settings | GitHub | No |
| Shared task board | GitHub issues with the label `akasha` | No |
| Task state | The issue of the task on the shared task board. Each computer also keeps the task in `.akasha/state/tasks/<task>.json`, with its work copy folder and its preview port | No |
| The person and the copy of the repository | `.akasha/state/me.json` (the GitHub name for the hooks, for one hour. Each command asks `gh`) and `.akasha/state/machine.json` (the random mark of this copy) | No |
| Work copies | `.akasha/work/<task>/`, on the branch `akasha/<task>`. A handoff pushes the work to `akasha-wip/<task>`. `[work]` in `akasha.toml` can give another folder in the repository and other prefixes. Git ignores the folder: `.gitignore`, or `.git/info/exclude` on each computer | No |
| Preview ports | `~/.akasha/ports.json` in the home folder of the person: the reserved ports of the previews of all copies of all repositories on this computer | No |
| Notices | `.akasha/state/board.json` (the copy of the board for the hooks, five minutes at most), `.akasha/state/seen.json` (the overlap notices after an edit), and `.akasha/state/seen/<task>.json` (the last comment on the issue that this computer showed) | No |

Each command of a task fetches the default branch from the server once. The team rules, the team workflows, and the start of each new work copy come from that branch, not from the checkout of the computer, which can be old. Without a server, Akasha uses the checkout, as in Akasha 1.0.0. When a server that is not on GitHub does not answer, Akasha uses the default branch as git fetched it last.

## Three enforcement layers

| Layer | When | What enforces it |
|:--|:--|:--|
| During the work | Before each command and edit, after each edit, and at the end of each turn | The hooks of the agent engine |
| Before the handover | When a task tries to go to the next stage | The exit conditions of the workflow |
| On the server | Before each merge | The required check `akasha`. GitHub branch protection and CODEOWNERS enforce it. Where the GitHub plan has no protection, the helpers of Akasha enforce it |

> **CAUTION:** The first two layers keep a cooperative agent engine on the rules. They are not a sandbox. Only a person with administrator rights can go around the server layer.

## The command line

The agent engine runs these commands. People do not have to remember them. The session start notice gives the full command.

| Command | Function |
|:--|:--|
| `setup` | Writes `akasha.toml`, the guide of the map folder, and the files that Codex reads. It keeps the other text of `AGENTS.md` and the other hooks of `.codex/hooks.json` at their places, and it does not change a `.codex/hooks.json` that is not JSON. It removes a byte order mark from `.codex/hooks.json`. In a repository that is ready, it writes only the files that Codex reads again, when the default branch does not have them as this Akasha makes them, and the work folder of `[work]` in `.gitignore` when git does not ignore it yet, and tells you to commit them. When the default branch has them and this checkout does not, it tells you to pull. When a newer Akasha wrote the rules or the hooks of Akasha in them, it does not write the older rules back and tells you to update Akasha. A change of the team in these files, for example its own hooks, does not count. It stops when git tracks files in the work folder of `[work]`. With the approval of an administrator, it also changes the GitHub settings |
| `request` | Records a new task and shows overlaps. With GitHub, the requester is your GitHub account, or the account that `--requester` names. `--feature <key>` gives the feature key: lower-case letters, digits, and `-`, with `/` between the parts of a large feature. `--builds-on` stacks it on an earlier task. It brings the main checkout forward to the latest default branch, or tells how far it stays behind |
| `specify` | Adds completion conditions, open questions, or file patterns of the scope. `--builds-on ""` stops building on the earlier task. `--requester <GitHub name>` gives a GitHub account to a requester that is not one, for example a name that Akasha 1.0.0 recorded. `--feature <key>` changes the feature key. After a change of the scope or of the feature key, Akasha compares what changed with the other tasks |
| `impact` | Records the impact analysis, a reason why the map file of the feature does not change, or a change of behavior that an earlier requester accepted |
| `approve` | Records the approval of a requester or of a gate role. With GitHub, it writes the decision comment only for the GitHub account of this computer, else it tells the comment that the person must write. Without GitHub, `--by` names the person |
| `advance` | Moves the task to the next stage, or shows what blocks it. It compares a new contract of the real changes with the other tasks. It shows the new comments on the issue as news, apart from the blockers |
| `show` | Shows one task: stage, risk, holder, feature key and map file, scope, the revision of the specification, the numbered conditions, impact, approvals, checks, preview values, the decision comments that do not count, and the news. It only reads the task |
| `check` | Runs the required checks in the work copy. When each check passes or is NOT_NEEDED, it saves the work and pushes the task branch. It tells a push that the server refuses |
| `preview` | Reserves the preview port of the task on this computer, runs the seed command of `[preview]` in the work copy, and shows the filled preview values. The agent engine runs it before it starts the preview for the inspection |
| `accept` | Records the inspection of the requester, of one condition by its text or number, or of all conditions. With GitHub, the same rule as `approve` |
| `brief` | Examines and records the briefing |
| `handover` | Merges the task branch on the server and the latest default branch, checks the change again, opens the pull request with the label `akasha-merge`, and turns on auto-merge where GitHub merges. It also shows the news |
| `resume` | Opens a stopped task again after a developer examined it. With GitHub, the same rule as `approve` |
| `cancel` | Stops a task for good. With GitHub, the same rule as `approve`. It also closes the open pull request of the task, also when another person holds the task |
| `handoff` | Saves the work so far on the server and frees the task, so that another person can take it over. Run it in the main checkout |
| `takeover` | Holds a task that another person handed off, and makes its work copy on this computer. With `--force`, it takes over an open task without the handoff, when the copy of the holder is gone |
| `board` | Shows the tasks of all requesters, with the holder and the feature key of each task |
| `infra` | Shows the GitHub settings that are not correct. With `--apply`, it corrects them when the GitHub account of this computer is an administrator |
| `hook` | The entry point for the hooks of the agent engine: the session start, before a command or an edit, after an edit, and the end of a turn. Claude Code and Codex use the same hooks |
| `server` | The merge and watch helpers run this on GitHub: `merge`, `watch`, `update`, and `failed`. People and the agent engine do not run it |

## Requirements

- Python 3.11 or later, and git.
- The GitHub command line `gh`, logged in with the GitHub account of the person on the computer. To hold a task, the account must be able to write to the repository.
- A GitHub account for each requester, that can write comments in the repository. In a private repository, the account needs access to the repository.
- The git remote `origin` is the team repository on GitHub, not a fork. Akasha gives `gh` the repository of `origin`, so that the branches, the issues, and the pull requests go to the same repository.

> **NOTE:** Without GitHub, the shared task board holds only the tasks on one computer, and the handover cannot open a pull request. When `origin` is on GitHub and `gh` cannot read or write the board, the commands stop.
