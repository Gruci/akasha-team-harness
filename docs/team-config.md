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
required = ["secrets", "tests", "front"]
setup = "python -m pip install -r requirements.txt"
tests = "python -m pytest -q"

[checks.front]
command = "npm ci && npm run build"
cwd = "frontend"
only_when = ["frontend/**"]

[preview]
command = "npm run dev -- --port {port}"
database = "app_{task}"

[contracts]
customers-api = ["src/api/customers/**"]

[workflows]
enabled = ["feature", "fix", "small"]

[ci]
runs-on = "ubuntu-latest"
python = "3.12"

[context]
map = ".akasha/context/map"

[work]
folder = ".akasha/work"
branch_prefix = "akasha/"
wip_prefix = "akasha-wip/"
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
| `required` | The checks that must pass. Only these checks run. The default is `["secrets"]`. An empty list is also `["secrets"]`: with no check, no task can pass its checks. Akasha 1.0.0 ran no check for an empty list |
| `setup` | The command that installs the dependencies in a new copy. Akasha runs it in each new work copy and in the server check. It is not a check. When `required` names `setup`, as Akasha 1.0.0 permitted, the setup command also runs as a check at the top of the repository |
| `run_all_when` | File patterns. When a changed file matches one, each required check runs, also a check with `only_when`. The default is the dependency files, the lock files, and the settings files of the projects (for example `**/requirements*.txt`, `**/pyproject.toml`, `**/setup.py`, `**/package.json`, `**/package-lock.json`, `**/go.mod`, and `**/build.gradle`), `akasha.toml`, and `.github/workflows/**`. `[]` turns it off |
| `tests`, `lint` | One command line for the check `tests` or `lint`, as in Akasha 1.0.0. It is the same as a table with only `command` |
| `<name>` | A table `[checks.<name>]`: one check. See below |

The `secrets` check is built in. It examines each changed file, and it has no table.

### `[checks.<name>]`

Each table in `[checks]` is one check. Add its name to `required`: a check that is not in `required` does not run.

```toml
[checks]
required = ["secrets", "static", "pytest", "front"]

[checks.static]
command = "python -X utf8 static_check.py"

[checks.pytest]
command = "python -m pytest tests/ -q"
only_when = ["**/*.py", "tests/**", "pytest.ini", "conftest.py"]

[checks.front]
command = "npm ci && npm run build"
cwd = "frontend"
only_when = ["frontend/**"]
```

| Key | Value |
|:--|:--|
| `command` | The command of the check. It is necessary. The check passes when the command stops with the exit code 0 |
| `cwd` | The folder of the command, relative to the top of the repository. The default is the top. Akasha refuses an absolute path, a drive, and `..`. When the folder does not exist, the check fails and tells why |
| `only_when` | File patterns, relative to the top of the repository, also when the check has `cwd`. The check runs only when a changed file matches one, or a changed file matches `run_all_when`. Else its result is NOT_NEEDED. Without `only_when`, the check runs for each change |
| `command_windows` | The command on Windows, in the words of `cmd.exe`. On Windows, it replaces `command` |

A check name has only letters, digits, `-`, and `_`. `required`, `setup`, `run_all_when`, and `secrets` cannot be check names.

The results:

- PASS: the check passed.
- NOT_NEEDED: the change touches no file that the check examines. NOT_NEEDED is a pass. The Verification section of the pull request tells these checks apart from the checks that passed.
- SKIP: a required check without a command. SKIP is not a pass.
- FAIL: the check failed.

Akasha runs each command in the shell of the operating system: `cmd.exe` on Windows, and `/bin/sh` on macOS and Linux. It is not the shell of the person, for example PowerShell or zsh. The server check runs on the machine of `[ci] runs-on`, by default Linux (`ubuntu-latest`). Thus it uses `command`, and `command_windows` on a Windows runner.

The patterns of `only_when` and `run_all_when` use the pattern rules of `[risk]`. Akasha reads `\` as `/` and removes a leading `./`. A pattern that ends with `/`, for example `frontend/`, matches each file in that folder. A folder name alone, for example `frontend`, matches only a file with that name: write `frontend/**`. A pattern that matches no changed file makes the check NOT_NEEDED, and NOT_NEEDED is a pass. Thus make sure that each pattern is relative to the top of the repository, not to `cwd`. The default `run_all_when` closes a gap: a pull request that changes only a dependency file, for example `requirements.txt`, can break each check, but it matches no `only_when` of the code.

> **CAUTION:** An Akasha plugin that is not updated refuses `[checks.<name>]` and `run_all_when`. Make sure that each person updated the Akasha plugin before you add them.

## `[preview]`

| Key | Value |
|:--|:--|
| `command` | The command that starts a preview |
| `database` | The name of the preview database |
| `seed` | The command that makes the preview database of the task and puts sample data in it. It must give the same result when it runs again |
| `cleanup` | The command that removes the preview database of a finished task. It must not fail when the database is not there |

Akasha replaces `{task}` with the task name and `{port}` with the preview port of the task on this computer. Thus each task gets its own values. Before the inspection, the agent engine runs `preview <task>`: Akasha reserves the port, runs `seed` in the work copy, and shows the filled values. `show` also shows them. Before the port is reserved, `show` shows a value with `{port}` as it is.

When the pull request of a task merges, Akasha runs `cleanup` in the work copy, then removes the work copy and frees the port. `cleanup` runs only for a task that `preview` prepared on this computer, also before a handoff. A cancelled task keeps its database, as it keeps its work copy. The server check never runs `seed` or `cleanup`. See [Preview resources](coordination.md#preview-resources).

```toml
[preview]
command = "npm run dev -- --port {port}"
database = "app_{task}"
seed = "npm run db:seed -- app_{task}"
cleanup = "npm run db:drop -- app_{task}"
```

> **CAUTION:** An Akasha plugin that is not updated refuses `seed` and `cleanup`. Make sure that each person updated the Akasha plugin before you add them.

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

## `[ci]`

The machine and the Python of the server check, `.github/workflows/akasha.yml`.

| Key | Value |
|:--|:--|
| `runs-on` | The runner label of the machine, or a list of labels for a runner of the team, for example `["self-hosted", "windows"]`. The default is `ubuntu-latest`. Akasha refuses an empty label, a line break, and `#` |
| `python` | The Python version of the server check, as text, for example `"3.12"` or `"3.13.1"`. It must be 3.11 or higher, because Akasha needs Python 3.11 or higher. Akasha refuses a number without quotes: TOML reads `3.10` as `3.1`. The default is `"3.12"` |

Akasha writes these values into `akasha.yml` when an administrator sets up Akasha (`infra --apply` or `setup --approve-infra`). The examination of the server rules compares `akasha.yml` on the default branch with the file that `[ci]` on the default branch gives. Thus, after a change of `[ci]`, set up Akasha again, and commit `akasha.toml` and `akasha.yml` in one pull request.

The steps of `akasha.yml` use bash, also on a Windows runner. A Windows runner of the team needs Git Bash. The check commands of the team run in the shell of the operating system, so they run in `cmd.exe` on a Windows runner. Give `command_windows` to each check that needs it.

The merge and watch helpers always run on `ubuntu-latest`. They can write to the repository, so they must not run on a machine where the code of a pull request ran.

> **CAUTION:** In a public repository, a pull request from a fork runs its code in the server check. On a runner of the team, that code runs on a machine of the team. When `runs-on` is not a standard machine of GitHub, for example `ubuntu-latest`, `windows-2022`, `macos-15`, or `ubuntu-24.04-arm`, and the repository is public, Akasha shows a warning. A standard label has the name of the system, then a version, `latest`, or `slim`. It can end with `-arm`, `-intel`, `-large`, or `-xlarge`, and with no other text. Thus a label of the team, for example `ubuntu-22.04-gpu`, gets the warning. A larger runner of GitHub with a name that the team gave it also gets the warning: Akasha cannot tell it from a runner of the team. `infra --apply` and `setup --approve-infra` show the warning when they write `akasha.yml`. `infra` and `setup` show it after the change is on the default branch. The warning does not stop a handover.

> **CAUTION:** An Akasha plugin that is not updated refuses `[ci]`. Make sure that each person updated the Akasha plugin before you add it.

## `[context]`

| Key | Value |
|:--|:--|
| `map` | The map folder of the product map, relative to the top of the repository. The default is `.akasha/context/map`. Akasha refuses an absolute path, a drive, `..`, and a device name of Windows, for example `aux` |

The map folder is outside each task scope, and its files do not raise the risk level of a task, so that each task can update its map file. Use it only for the product map.

> **CAUTION:** An Akasha plugin that is not updated refuses an unknown section, also `[context]`. Make sure that each person updated the Akasha plugin before you add it.

## `[work]`

The work copies and the branches of the tasks. Change these keys when the repository already uses the default names, for example for its own branches or for another tool.

| Key | Value |
|:--|:--|
| `folder` | The folder of the work copies, relative to the top of the repository. The default is `.akasha/work`. The work copy of each task is `<folder>/<task>`. Akasha refuses an absolute path, a drive, `..`, the top of the repository, and a device name of Windows. It also refuses `.git`, `.akasha/state`, `.akasha/context`, `.akasha/workflows`, and the map folder, a folder in one of them, and a folder around one of them |
| `branch_prefix` | The prefix of the task branches. The default is `akasha/`. The branch of a task is `<prefix><task>`, for example `feat/add-a-date-filter-1f3a9c0b` |
| `wip_prefix` | The prefix of the branches of the handoffs. The default is `akasha-wip/` |

The folder must be in the repository. Outside it, the guard stops each recursive delete in a work copy, and two clones on one computer share one folder. Git must not track the work copies. When no ignore file names the folder, Akasha adds it to `.git/info/exclude` at the first work copy on each computer. Nobody commits that file. `setup` also adds the folder to `.gitignore` when git does not ignore it yet. Git must not track files in the folder either: git ignores the folder, also in each work copy, so the new files of a task there would not go into the task. Akasha stops the work copies and `setup` when git tracks files in the folder. Case does not count.

Akasha adds the task name to each prefix, so the result must be a correct branch name of git. Akasha refuses a space, `~`, `^`, `:`, `?`, `*`, `[`, `\`, `..`, `@{`, a leading `-`, and a part that starts with `.` or ends with `.lock`. Akasha tells a task branch from a wip branch by the prefix. Thus it also refuses two prefixes when one starts with the other, for example `akasha/` and `akasha/wip/`. The default prefixes count too, because the tasks from before a change of `[work]` keep their branches: Akasha refuses a `branch_prefix` when it or `akasha-wip/` starts with the other, and a `wip_prefix` when it or `akasha/` starts with the other. Case does not count.

A change applies to the new tasks. Each task keeps its branch, also after a takeover on another computer: its pull request and its branch on the server stay the same. A work copy of the task that a computer still has stays in its folder. A takeover finds the work of the last handoff with `wip_prefix` and with the default `akasha-wip/`. A handoff never pushes to the branch of the task: when the wip branch has its name, the handoff uses the default `akasha-wip/`. The guard stops a push to the branches of the prefixes of `[work]`, of the default prefixes, and of each task on this computer, also from the work copy of each task.

> **CAUTION:** An Akasha plugin that is not updated refuses `[work]`. Make sure that each person updated the Akasha plugin before you add it.

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
