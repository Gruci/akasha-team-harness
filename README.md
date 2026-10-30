<div align="center">

<img src="docs/readme/banner.svg" width="900" alt="Akasha lets any person on your team make features with an AI agent.">

**Let any person on your team make features with an AI agent.**<br>
Your developers get pull requests that they can merge: clear, tested, and accepted.

Akasha · team harness · harness v1.0.0

<img src="https://img.shields.io/badge/version-1.0.0-7c3aed" alt="Version 1.0.0">
<a href="#license"><img src="https://img.shields.io/badge/license-MIT-22c55e" alt="MIT license"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11 or later">
<img src="https://img.shields.io/badge/engines-Claude%20Code%20%C2%B7%20Codex-111827" alt="Engines: Claude Code and Codex">

[English](README.md) · [한국어](README.ko.md)

</div>

## Why teams use Akasha

AI agents can write code for anyone. In a team, that causes new problems.
Akasha stops these problems before they reach your developers.

| Without Akasha | With Akasha |
|:--|:--|
| A team member asks the AI for a feature. The request is not clear, so the AI makes a different feature | Akasha asks questions until the completion conditions are clear |
| The AI says "Done." Nobody knows if the feature does what the team member wanted | The team member examines the feature in a preview and accepts it |
| A change touches customer data or permissions. Nobody sees the risk | Akasha sets a risk level. A high-risk change needs the approval of a developer |
| Developers get large pull requests with no explanation | Each pull request contains the request, the test results, the acceptance result, and the risks that remain |
| Two people change the same feature at the same time | Akasha finds the overlap before the work starts |
| The team rules are only in the heads of senior developers | The rules are in the repository. Checks enforce them on each change |

## One request, from start to merge

A requester in the operations team wants a date filter in the customer search.
The requester is not a developer.

1. **The requester asks.** "Add a date filter to the customer search."
2. **Akasha asks back.** "Which date: the sign-up date or the transaction date?" "Must customers without permission be visible?" "Must the filter work with the other filters?"
3. **Akasha builds and checks.** The agent engine makes the change in a separate work copy. Akasha runs the tests and the checks, and repairs the failures.
4. **The requester examines.** Akasha shows the filter in a preview with sample data. The requester accepts the result.
5. **The developer merges.** The pull request shows risk level low, all tests passed, and the acceptance of the requester. The developer reviews the data permissions and the query speed, and merges the change.

The requester did not write code. The developer did not explain the procedure again. Akasha did that work.

## What each person does

| Person | Does | Does not need to |
|:--|:--|:--|
| Requester | Tells the goal, answers business questions, and examines the preview | Read code, run commands, or decide the architecture |
| Developer | Approves high-risk designs, reviews pull requests, and merges | Explain the procedure again for each request |
| Administrator | Writes the team rules one time in `akasha.toml` | Configure each repository setting by hand |

Akasha asks each question only to the person who can answer it. The requester gets no technical questions.

## How Akasha works

Akasha puts the agent engine inside a fixed procedure.
Each task goes through six stages. A task goes to the next stage only when it meets the exit condition.

| Stage | Exit condition |
|:--|:--|
| 1. Request | The completion conditions are clear |
| 2. Specification and risk | The requester approves the design. For a high risk, a developer also approves |
| 3. Build | The change uses only the permitted files, tools, and permissions |
| 4. Checks and repair | All required checks pass. After three failed repairs, Akasha stops and tells a developer the problem in simple words |
| 5. Inspection | The requester accepts the result in a preview |
| 6. Handover | A developer approves and the required checks pass. Then the change merges |

A small change uses the `small` workflow. A defect uses the `fix` workflow.

Akasha enforces this procedure at three layers:

1. **During the work.** Akasha does a check each time it saves a file and at the end of each turn. It stops a command that you cannot undo, for example a force push, before the command runs.
2. **Before the handover.** All required checks and tests must pass, and the requester must accept the feature. Only then does Akasha open the pull request.
3. **On the server.** Akasha installs and monitors the required checks, branch protection, and CODEOWNERS on GitHub. The required checks run with the rules of the default branch. A pull request that makes the checks weaker cannot pass.

## Install

Akasha is a plugin. In Claude Code, type these two commands:

```
/plugin marketplace add Gruci/akasha-team-harness
/plugin install akasha@akasha
```

Then do these steps:

1. Open your repository.
2. Say "Set up Akasha."
3. Answer the questions about the roles in your team, the high-risk areas, and the preview command.

Akasha writes `akasha.toml`, configures GitHub, and writes the files that Codex reads.

> **CAUTION:** Akasha changes branch protection and CODEOWNERS only with the approval of a repository administrator.

You need Python 3.11 or later and git. The pull request flow and the server rules need GitHub.

## Inside Akasha

Akasha has eight parts in four areas.

| Area | Part | Function |
|:--|:--|:--|
| Team harness | Core | Keeps the state of each task, moves the task between stages, holds the approval waits, and writes the handover document. The core is the same in all teams |
| Team harness | Workflow | Declares the stages and the exit conditions. Your team can change the `feature`, `fix`, and `small` workflows and add more |
| Team harness | Skills and context | Contain only the procedures and the knowledge of your team, for example the request interview and the record of decisions and lessons |
| Team harness | Validators | Change each rule that a machine can examine into a check: tests, lint, boundary checks, secret keys, and commands that you cannot undo |
| Team harness | Team config | Contains the team rules for one repository in `akasha.toml`: roles, risk rules, approval rules, workflows, checks, and the preview command |
| Agent engine | Agent engine | Operates Claude Code or Codex with the session rules, hooks, and skills of Akasha |
| Coordination | Coordinator | Keeps the shared task board on GitHub, finds overlaps before a task starts, and gives each task its own preview resources |
| Infrastructure control | Infrastructure manager | Keeps the required checks, branch protection, and CODEOWNERS the same as the team config, and offers to restore a changed setting |

## What your team can change

- **Agent engine.** Claude Code or Codex. The procedure and the checks do not change.
- **Languages.** Packs for Python, TypeScript, Go, and Java are included. Add a language with one pack file.
- **Workflows.** Change the workflows and add more. The core does not change.
- **Project structure.** Akasha does not force a structure, for example layers or feature folders.

## What Akasha guarantees

| Guaranteed | How |
|:--|:--|
| A change that fails a required check does not merge | The required checks and branch protection stop the merge. Akasha installs and monitors them |
| A high-risk change does not merge without developer approval | The risk level sets the approvers. CODEOWNERS enforces the approval |
| A feature that the requester did not accept does not go to a pull request | In the `feature` and `fix` workflows, stage 6 starts only with the acceptance record from stage 5 |
| Two tasks do not write over each other | Each task has a separate work copy, and Akasha finds overlaps before a task starts |

| Not guaranteed | Reason |
|:--|:--|
| Correct business logic | The inspection and the review must examine it. A person must decide if the tests cover the correct behavior |
| A security boundary | The local checks keep a cooperative agent engine on the rules. They are not a sandbox |
| A preview environment | Your project supplies it. Akasha starts it with your command and gives each task a different name |

## FAQ

| Question | Answer |
|:--|:--|
| Can a team without a developer use Akasha? | No. A developer must make the merge decision. Akasha makes the result ready for that decision |
| Must a requester use a terminal? | No. The requester asks in the desktop app. Akasha runs the commands |
| Who can change the infrastructure rules? | Only a repository administrator. Akasha proposes each change and makes it after the administrator approves |
| Two requesters want to change the same item. What occurs? | Akasha finds the overlap before the second task starts. For the same feature, it offers to join the tasks. For the same files, it sets the sequence. For the same contract, it tells the owners |
| Can I use Akasha in a repository without tests? | Yes, but the guarantee of stage 4 is weaker. Make the tests a required check in the team config. Then Akasha stops a merge without tests |

## Changelog

| Version | Changes |
|:--|:--|
| **v1.0.0** | Eight parts. The `feature`, `fix`, and `small` workflows. Roles and risk levels. Inspection with a preview. The handover document. A shared task board with overlap checks. Agent engines for Claude Code and Codex. Infrastructure control for GitHub. Four language packs. Plugin install. |

## License

Daehyun Kim · [LinkedIn](https://www.linkedin.com/in/daehyun-kim-b00365176/)

MIT License
