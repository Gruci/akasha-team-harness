<div align="center">

<img src="docs/readme/banner.svg" width="900" alt="Akasha lets any person on your team build one product with an AI agent.">

**Let any person on your team build one product with an AI agent.**<br>
People decide what to make, how it looks, and how people use it. The AI makes the technical decisions, checks them, and merges each change as one clear commit.

Akasha · team harness · harness v1.0.0

<img src="https://img.shields.io/badge/version-1.0.0-7c3aed" alt="Version 1.0.0">
<a href="#license"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT license"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11 or later">
<img src="https://img.shields.io/badge/engines-Claude%20Code%20%C2%B7%20Codex-111827" alt="Engines: Claude Code and Codex">

[English](README.md) · [한국어](README.ko.md)

</div>

## Why teams use Akasha

AI agents can write code for anyone. In a team, that causes new problems.
Akasha is a harness for the whole team: each person installs it. It stops these problems, so that developers and other team members can build one product together.

| Without Akasha | With Akasha |
|:--|:--|
| Only developers can judge the technical effects of a change | The AI makes the technical decisions and records them. People decide what to make, how it looks, and how people use it |
| A team member asks the AI for a feature. The request is not clear, so the AI makes a different feature | Akasha asks questions until the completion conditions are clear |
| The AI says "Done." Nobody knows if the feature does what the team member wanted | The team member examines the feature in a preview and accepts it |
| A change touches other features, customer data, or permissions. Nobody sees the effects | The AI finds the effects on other features, data, and APIs, and records how to reverse the change |
| Changes merge with no explanation. Later, nobody can find the change that caused a problem | Each change merges as one commit with a one-minute briefing: why, scope, blast radius, and verification |
| Two people change the same feature at the same time, and wait for each other | Akasha finds the overlap before the work starts. The second task builds on the first, so nobody waits |

## One request, from start to merge

A requester in the operations team wants a date filter in the customer search.
The requester is not a developer.

1. **The requester asks.** "Add a date filter to the customer search."
2. **Akasha asks back.** "Which date: the sign-up date or the transaction date?" "Must customers without permission be visible?" "Must the filter work with the other filters?"
3. **The AI examines the effects.** Two reports also read the customer table. The change adds an index and changes no data. The AI records this impact analysis.
4. **Akasha builds and checks.** The AI makes the change and a test for each condition in a separate work copy. Akasha runs the checks, and the AI repairs the failures.
5. **The requester examines.** Akasha shows the filter in a preview with sample data. The requester accepts the result.
6. **GitHub merges.** The pull request has a one-minute briefing. When the server check passes, GitHub merges the change as one commit.

The requester did not write code or make a technical decision. Nobody explained the procedure. Akasha and the AI did that work.

## What each person does

| Who | Does | Does not need to |
|:--|:--|:--|
| Requester (any team member, a developer or not) | Tells what to make, how it looks, and how people use it. Examines the preview | Read code, decide the implementation, or judge the technical risk |
| The AI (agent engine) | Decides the implementation, the scope, and the impact. Writes the tests, the briefing, and the product map | Ask people technical questions |
| Administrator | Writes the team rules one time in `akasha.toml`, and approves changes of the GitHub settings | Configure each repository setting by hand |

Akasha asks people only what to make, how it looks, and how they use it.

## How Akasha works

Akasha puts the agent engine inside a fixed procedure.
Each task goes through six stages. A task goes to the next stage only when it meets the exit condition.

| Stage | Exit condition |
|:--|:--|
| 1. Request | The completion conditions are clear |
| 2. Specification and impact | The requester approves the specification. The AI recorded the effects on features, data, APIs, and other tasks, and how to reverse the change |
| 3. Build | The change uses only the files in its scope |
| 4. Checks and repair | All required checks pass. After three failed repairs, Akasha stops and tells a developer the problem in simple words |
| 5. Inspection | The requester accepts the result in a preview. The product map shows the change |
| 6. Handover | The server check passes. GitHub merges the change as one commit with the briefing |

A small change uses the `small` workflow. A defect uses the `fix` workflow.

Akasha enforces this procedure at three layers:

1. **During the work.** Akasha does a check each time it saves a file and at the end of each turn. It stops a command that you cannot undo, for example a force push, before the command runs.
2. **Before the handover.** All required checks must pass, the requester must accept the feature, and the briefing must pass its check. Only then does Akasha open the pull request.
3. **On the server.** Akasha installs and monitors the required check, branch protection, and auto-merge on GitHub. The check runs with the rules of the default branch, so a pull request that makes the checks weaker cannot pass. A change of the team rules needs an administrator.

## Install

Akasha is a team harness. Each person on the team installs it. In Claude Code, type these two commands:

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

Then open the team repository. Akasha first examines the repository on GitHub:

- **The team rules and the server rules are on.** Akasha is ready. Ask for features. Nobody does a setup.
- **The repository does not use Akasha yet.** Say "Set up Akasha." Akasha asks about the administrators, the high-risk areas, and the preview command. Then it writes `akasha.toml`, the product map, and the files that Codex reads.
- **The server rules are off.** Akasha tells you. A repository administrator turns them on one time, for the whole team. Until then, you can work, but the handover waits.

> **CAUTION:** Akasha changes branch protection, auto-merge, and CODEOWNERS only with the approval of a repository administrator.

You need Python 3.11 or later and git. The pull request flow and the server rules need GitHub. In a private repository, the server rules need GitHub Pro, Team, or Enterprise. GitHub Free has them only in public repositories.

## Inside Akasha

Akasha has eight parts in four areas.

| Area | Part | Function |
|:--|:--|:--|
| Work procedure | Core | Keeps the state of each task, moves the task between stages, and writes the pull request briefing. The core is the same in all teams |
| Work procedure | Workflow | Declares the stages and the exit conditions. Your team can change the `feature`, `fix`, and `small` workflows and add more |
| Work procedure | Skills and context | Contain the procedures, the product map, and the decisions of your team |
| Work procedure | Validators | Change each rule that a machine can examine into a check: tests, lint, scope, secret keys, the briefing, and commands that you cannot undo |
| Work procedure | Team config | Contains the team rules for one repository in `akasha.toml`: roles, risk rules, person gates, workflows, checks, and the preview command |
| Agent engine | Agent engine | Operates Claude Code or Codex with the session rules, hooks, and skills of Akasha |
| Coordination | Coordinator | Keeps the shared task board on GitHub and finds overlaps before a task starts. Stacks the tasks of one feature, and gives each task its own preview resources |
| Infrastructure control | Infrastructure manager | Examines the server rules when a person opens the repository. Keeps the required check, branch protection, auto-merge, and CODEOWNERS the same as the team config |

## What your team can change

- **Agent engine.** Claude Code or Codex. The procedure and the checks do not change.
- **Languages.** Packs for Python, TypeScript, Go, and Java are included. Add a language with one pack file.
- **Workflows.** Change the workflows and add more. The core does not change.
- **Person gates.** By default, the AI makes the technical decisions. Add a person gate for a risk level, for example a developer approval for data changes.
- **Project structure.** Akasha does not force a structure, for example layers or feature folders.

## What Akasha guarantees

| Guaranteed | How |
|:--|:--|
| A change that fails a required check does not merge | The required check and branch protection stop the merge. Akasha installs and monitors them |
| A change of the team rules does not merge without an administrator | CODEOWNERS gives the team rules to the administrators |
| A feature that the requester did not accept does not go to a pull request | In the `feature` and `fix` workflows, stage 6 starts only with the acceptance record from stage 5 |
| You can find and revert each change | Each task merges as one squash commit. Its body is the briefing: why, scope, blast radius, and verification |
| Two tasks do not write over each other | Each task has a separate work copy. A task of the same feature builds on the earlier task |

| Not guaranteed | Reason |
|:--|:--|
| Correct business logic | The inspection must examine it. A person must decide if the result does what the team needs |
| Data reversal | A revert of the code does not restore data. The impact analysis records how to reverse a data change |
| A security boundary | The local checks keep a cooperative agent engine on the rules. They are not a sandbox |
| A preview environment | Your project supplies it. Akasha starts it with your command and gives each task a different name |

## FAQ

| Question | Answer |
|:--|:--|
| Can a team without a developer use Akasha? | Yes. The AI makes the technical decisions, and the server check stops a change that fails. When your team has a developer, add a person gate for data or permissions |
| Must a requester use a terminal? | No. The requester asks in the desktop app. Akasha runs the commands |
| Who can change the infrastructure rules? | Only a repository administrator. Akasha proposes each change and makes it after the administrator approves |
| Two people want to change the same feature. What occurs? | Akasha finds the overlap before the second task starts. The second task builds on the first, so nobody waits for the other person. If the second request changes behavior that the first requester accepted, Akasha tells the first requester on GitHub |
| How do I revert a change? | Find its commit on the default branch. The briefing tells why, the scope, and the blast radius. Revert that one commit. For a data change, also do the rollback in the impact analysis |
| Can I use Akasha in a repository without tests? | Yes. The AI writes a test for each completion condition. Make the tests a required check in the team config. Then Akasha stops a merge without tests |

## Changelog

| Version | Changes |
|:--|:--|
| **v1.0.0** | Eight parts. The `feature`, `fix`, and `small` workflows. AI impact analysis and the product map. Inspection with a preview. A one-minute briefing and auto-merge as one commit. A shared task board with overlap checks and stacked tasks. Optional person gates. Agent engines for Claude Code and Codex. Infrastructure control for GitHub. Four language packs. Plugin install. |

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/)

MIT License
