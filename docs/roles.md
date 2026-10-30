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

A team can add a person gate for a risk level in `[approval]`, for example a developer approval for data changes. The names of the gate people go in `[roles]`. A developer also opens a task again after three failed repairs.

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

The agent engine records each decision of a person with a command: `approve`, `accept`, `resume`, or `cancel`. Each record contains the name of the person.

- A gate decision and a `resume` must come from a name in `[roles] developers`.
- A change of the GitHub settings must come from a name in `[roles] administrators`.

> **CAUTION:** The agent engine must never record a decision that a person did not give. Akasha cannot verify a person on the local computer. GitHub verifies the code owner reviews with GitHub accounts.
