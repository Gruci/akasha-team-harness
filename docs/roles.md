# Roles

Akasha has three roles. Akasha asks each question only to the person who can answer it.

## Requester

The requester is a person who needs a feature, for example a person in operations, sales, or finance. The requester does not have to be a developer.

| The requester does | Akasha does for the requester |
|:--|:--|
| Tells the goal and the use scenario | Asks questions until the completion conditions are clear |
| Answers business questions | Asks no technical questions |
| Approves the specification | Writes the specification in simple words |
| Examines the result in a preview and accepts it | Starts the preview and shows each completion condition |

## Developer

| The developer does | Akasha does for the developer |
|:--|:--|
| Approves the specification of a risky change, when `[approval]` requires it | Sets the risk level and shows the reasons |
| Examines a stopped task and opens it again | Stops the task after three failed repairs and tells the problem in simple words |
| Reviews and merges the pull request | Writes the handover document: the request, the conditions, the inspection, the risk, the checks, the changed files, and what Akasha did not verify |

## Administrator

| The administrator does | Akasha does for the administrator |
|:--|:--|
| Writes the team rules in `akasha.toml` | Refuses a team config with an incorrect shape |
| Approves each change of the GitHub settings | Shows each setting that is not correct, and corrects it after the approval |
| Owns `akasha.toml`, `.akasha/`, and `.github/` | Writes CODEOWNERS, so that a change of the rules needs an administrator |

## Who decides what

| Decision | Role |
|:--|:--|
| The goal, the completion conditions, and the business rules | Requester |
| Approval of the specification | Requester |
| Approval of a change at a risk level that `[approval]` names | The roles that `[approval]` names |
| Acceptance of the result | Requester |
| Withdrawal of a request | Requester |
| Opening a stopped task again | Developer |
| Merge of the pull request | Developer, as CODEOWNERS sets |
| Change of the team rules and the GitHub settings | Administrator |

## How Akasha records a decision

The agent engine records each decision with a command: `approve`, `accept`, `resume`, or `cancel`. Each record contains the name of the person.

- A developer decision must come from a name in `[roles] developers`.
- A change of the GitHub settings must come from a name in `[roles] administrators`.

> **CAUTION:** The agent engine must never record a decision that a person did not give. Akasha cannot verify a person on the local computer. The server verifies the merge decision with GitHub accounts, through CODEOWNERS and branch protection.
