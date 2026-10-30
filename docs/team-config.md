# Team config

`akasha.toml` holds the team rules for one repository. The administrators own it through CODEOWNERS.

Each command of a task reads `akasha.toml` and the team workflows from the default branch on the server, once for each command. Thus each computer uses the rules that the administrators merged, also when its checkout is old. Without a server, or when the default branch has no `akasha.toml`, Akasha reads the files in the checkout. With GitHub, a server that does not answer stops the command. When a server that is not on GitHub does not tell its default branch in 10 seconds, Akasha uses the default branch as git fetched it last. `setup` and `infra --apply` read and write the file in the checkout, because the administrator changes it there and opens a pull request.

## Example

```toml
[roles]
developers = ["lead-dev"]
administrators = ["repo-admin"]

[risk]
high = ["**/migrations/**", "**/auth/**", "**/payments/**"]
medium = ["**/api/**"]

[approval]
high = ["developer"]

[checks]
required = ["secrets", "tests", "lint"]
setup = "npm ci"
tests = "npm test --silent"
lint = "npx eslint ."

[preview]
command = "npm run dev -- --port {port}"
database = "app_{task}"

[contracts]
customers-api = ["src/api/customers/**"]

[workflows]
enabled = ["feature", "fix", "small"]
```

## `[roles]`

| Key | Value |
|:--|:--|
| `developers` | The GitHub names of the people who can open a stopped task again and who hold the `developer` gate |
| `administrators` | The GitHub names of the people who own the team rules and approve changes of the GitHub settings |

A developer approval and a `resume` must come from a name in `developers`. A change of the GitHub settings must come from a name in `administrators`.

With GitHub, the name is the GitHub account that wrote the decision comment, or the GitHub account of the computer for a change of the GitHub settings. When a list is empty, each person with write access to the repository has the role. Akasha asks GitHub for the permission of the account. A change of the GitHub settings also needs an account that administers the repository on GitHub. Without GitHub, an empty list accepts each name. [Roles](roles.md) tells each decision and its comment.

## `[risk]`

| Key | Value |
|:--|:--|
| `high` | File patterns of high-risk code |
| `medium` | File patterns of medium-risk code |

A change is high risk when one changed file matches a `high` pattern. It is medium risk when one file matches a `medium` pattern or a contract. All other changes are low risk. The risk level goes into the impact analysis and the briefing.

Pattern rules:

- `*` matches all characters, also `/`.
- A leading `**/` also matches a file at the top of the repository.

## `[approval]`

By default, no person gate exists. The agent engine makes the technical decisions and records them.

To add a person gate, name the roles that must approve each risk level:

| Key | Value |
|:--|:--|
| `high` | The roles that must approve a high-risk change |
| `medium` | The roles that must approve a medium-risk change |

The roles are `requester`, `developer`, and `administrator`. Akasha also writes each gate into CODEOWNERS. Then GitHub also requires the review of these people before the merge.

## `[checks]`

| Key | Value |
|:--|:--|
| `required` | The checks that must pass: `secrets`, `tests`, and `lint`. The default is `["secrets"]` |
| `setup` | The command that installs the dependencies in a new copy. Akasha runs it in each new work copy and in CI |
| `tests` | The command that runs the tests |
| `lint` | The command that runs the lint |

The `secrets` check is built in. A required check without a command gets the result SKIP. SKIP is not a pass.

## `[preview]`

| Key | Value |
|:--|:--|
| `command` | The command that starts a preview |
| `database` | The name of the preview database |

Akasha replaces `{task}` with the task name and `{port}` with a port for the task. Thus each task gets its own values. The agent engine reads the filled values with `show`.

## `[contracts]`

Each key is the name of a public contract, for example an API that other teams use. The value is a list of file patterns.

A change that matches a contract pattern is medium risk or higher. The coordinator tells the requesters of the other tasks that change the same contract.

## `[workflows]`

| Key | Value |
|:--|:--|
| `enabled` | The workflows that new requests can use. The default is all workflows. A task that started with a workflow continues with it, also when the workflow is not in the list now |

## `[server]`

| Key | Value |
|:--|:--|
| `rules` | `github` when GitHub branch protection and auto-merge enforce the server rules. `akasha` when the merge and watch helpers of Akasha enforce them, because the GitHub plan has no branch protection |

The setup writes this key. Do not change it by hand. When the plan of the repository changes, run the setup again.

## Product map and team context

`.akasha/context/product-map.md` tells how the features, screens, data, and APIs connect. `setup` writes an empty map. The agent engine reads it before each impact analysis and updates it before each handover.

Put the other decisions and lessons of your team in `.akasha/context/` as Markdown files. The session start notice shows all these files.

## How Akasha examines this file

- Akasha refuses an unknown section, an unknown key, and a value of the wrong type. When the incorrect file is on the default branch, the message names the branch, for example `origin/main`.
- The server check takes `akasha.toml` from the default branch. Thus a pull request cannot make its own rules weaker.
- A change applies to the tasks when it merges on the default branch. A change in a checkout that did not merge does not apply.

> **CAUTION:** A change to `akasha.toml` changes the rules for all tasks. Get the approval of an administrator for each change.
