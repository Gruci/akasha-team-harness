# Roles

People decide what to make, how it looks, and how people use it. The agent engine makes the technical decisions, and asks each question only to the person who can answer it. Akasha is the harness of the agent engine: it records each decision and stops a stage that does not meet its exit condition.

## Requester

The requester is any person in the team: a developer, or a person in operations, sales, or finance.

| The requester does | The agent engine does for the requester |
|:--|:--|
| Tells what to make and how people use it | Asks questions until the completion conditions are clear |
| Tells how the result must look | Asks no technical questions |
| Approves the specification in simple words | Finds the effects on other features, data, APIs, and tasks, and records them |
| Examines the result in a preview and accepts it | Starts the preview and shows each completion condition |

## The agent engine

| The agent engine decides | Akasha makes it record |
|:--|:--|
| The implementation and the scope | The scope and the changed files |
| The effects on other features, data, APIs, and tasks | The impact analysis with five parts, also how to reverse the change |
| How tasks of one feature combine | The earlier task that a task builds on, and each notice to an earlier requester |
| What the change means for a later reader | The briefing, which becomes the merge commit |
| How the product connects | The product map |

## Administrator

| The administrator does | Akasha does for the administrator |
|:--|:--|
| Writes the team rules in `akasha.toml` | Refuses a team config with an incorrect shape |
| Approves each change of the GitHub settings | Shows each setting that is not correct, and corrects it after the approval |
| Owns `akasha.toml`, `.akasha/workflows/`, and `.github/` | Writes CODEOWNERS, so that a change of the rules needs an administrator |

## Optional gates and developers

A team can add a person gate for a risk level in `[approval]`, for example a developer approval for data changes. The names of the gate people go in `[roles]`. A developer also opens a task again after three failed repairs, with the decision comment `/resume`.

## Who decides what

| Decision | Who |
|:--|:--|
| What to make, how it looks, and how people use it | Requester |
| Approval of the specification | Requester |
| Implementation, scope, impact, and the order of the work | The agent engine |
| Approval of a change at a gated risk level | The roles that `[approval]` names |
| Acceptance of the result | Requester |
| Withdrawal of a request | Requester |
| Opening a stopped task again | Developer |
| Merge of the pull request | GitHub, when the server check passes and each code owner approved |
| Change of the team rules and the GitHub settings | Administrator |

## How Akasha records a decision of a person

With GitHub, each decision of a person is a decision comment on the issue of the task. GitHub shows the account that wrote each comment, so the comment tells who decided. Akasha does not trust a name that the agent engine types, the issue body, or the task file. Each time that Akasha reads a task, it counts the approvals and the inspection results again from the decision comments only.

| Decision | Decision comment | Who can write it | Without GitHub |
|:--|:--|:--|:--|
| Approval of the specification | `/approve spec r<N>` | The requester | `approve --role requester --by <name>` |
| Approval of a gated risk level | `/approve risk <level>` | A person with a gate role of that level in `[approval]` | `approve --role <role> --by <name>` |
| Inspection of a completion condition | `/accept <number> r<N>` or `/reject <number> r<N> <reason>` | The requester | `accept --condition <condition> --result yes` or `no` |
| Opening a stopped task again | `/resume` | A developer | `resume --by <developer>` |
| Withdrawal of a request | `/cancel <reason>` | The requester or a developer | `cancel --by <name>` |
| Change of the GitHub settings | No comment. Akasha asks GitHub who the person is | The GitHub account of the computer. It must be in `[roles] administrators` and administer the repository on GitHub | `infra --apply --by <administrator>` |

`[roles]` names the developers and the administrators. When a list is empty, each person with write access to the repository has that role: GitHub shows the account as an owner, a member, or a collaborator.

Rules for the decision comments:

- The comment starts with the decision. Write each decision as a new comment.
- `r<N>` is the revision of the specification. It goes up each time that the completion conditions or the open questions change. A decision for an older revision does not count. `show` and the issue body show the current revision.
- `<number>` is the number of a completion condition, from 1. `all` in place of the number inspects all conditions. For the same condition, the later comment wins.
- `/approve risk <level>` counts when the level is the current risk level of the task or higher. When the real changes raise the risk level, the gate needs a new approval. When `[approval]` names the role `requester`, the approval of the specification is the approval of the requester for the gate.
- A `/resume` counts only when it comes after the comment of Akasha that stopped the task, and only once.
- Akasha does not count an edited comment or a hidden comment. A person with write access can edit the comment of another person, and GitHub still shows the first author.
- The `@` and upper case or lower case do not change a name.
- `advance` and `show` tell each decision comment that does not count, and why.
- When Akasha cannot read the comments, no approval and no acceptance counts.

### The same-computer exception

When the person who decides is the GitHub account of this computer, the agent engine runs the Akasha command, for example `approve <task> --role requester`. Akasha writes the decision comment with that account, and counts it like each other comment. For the decision of another person, the command stops and tells the exact comment that the person must write on the issue. The guard stops a decision comment that the agent engine writes with `gh` in the shell.

> **CAUTION:** The agent engine must never record a decision that a person did not give. Each requester needs a GitHub account that can write comments in the repository. In a private repository, the account needs access to the repository. A person who uses the same-computer exception must be the GitHub account of `gh` on that computer.

> **NOTE:** A requester can approve on GitHub from any computer or phone. To accept, the requester examines the preview. The preview runs on the computer with the work copy, so a requester on another computer needs access to that preview.
