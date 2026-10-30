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

## `[context]`

| Key | Value |
|:--|:--|
| `map` | The map folder of the product map, relative to the top of the repository. The default is `.akasha/context/map`. Akasha refuses an absolute path, a drive, `..`, and a device name of Windows, for example `aux` |

The map folder is outside each task scope, and its files do not raise the risk level of a task, so that each task can update its map file. Use it only for the product map.

> **CAUTION:** An Akasha plugin that is not updated refuses an unknown section, also `[context]`. Make sure that each person updated the Akasha plugin before you add it.

## Product map and team context

The product map tells how the features, screens, data, and APIs connect. It has one Markdown file for each feature key in the map folder:

| Feature key | Map file |
|:--|:--|
| `billing` | `.akasha/context/map/billing.md` |
| `billing/invoice` | `.akasha/context/map/billing/invoice.md` |

The whole feature key selects the file. Thus the tasks of different features, and the parts of one large feature, do not change the same file, and their pull requests do not conflict there. A feature key has only lower-case letters `a` to `z`, digits, and `-`, with `/` between the parts. A part cannot be a device name of Windows (`con`, `prn`, `aux`, `nul`, `com0` to `com9`, `lpt0` to `lpt9`), because Windows cannot make its map file, and git cannot check out a commit that has it. The key cannot be `readme`, because a file system that ignores case puts `readme.md` on the guide `README.md`. `request --feature` and `specify --feature` refuse other keys.

`setup` writes the guide of the map folder, `README.md`, with the shape of a map file. A repository that Akasha 1.0.0 set up has no guide. The akasha-request skill and the Akasha rules in `AGENTS.md` give the shape too. The agent engine reads the map file of its feature before each impact analysis, and finds the features that depend on it ("Depends on"). It updates its map file before each handover. The session start notice shows the map folder and the feature keys that have a map file on the default branch, as git fetched it last. When git does not know the default branch, for example without a remote, it shows the map files of the checkout.

Akasha 1.0.0 had one map file for all features, `.akasha/context/product-map.md`. Akasha keeps it, and a change of it still updates the product map of each task. Move its sections to the map files of the features when you can.

Put the other decisions and lessons of your team in `.akasha/context/` as Markdown files. The session start notice shows all these files.

## How Akasha examines this file

- Akasha refuses an unknown section, an unknown key, and a value of the wrong type. When the incorrect file is on the default branch, the message names the branch, for example `origin/main`.
- The server check takes `akasha.toml` from the default branch. Thus a pull request cannot make its own rules weaker.
- A change applies to the tasks when it merges on the default branch. A change in a checkout that did not merge does not apply.

> **CAUTION:** A change to `akasha.toml` changes the rules for all tasks. Get the approval of an administrator for each change.
