# Team config

`akasha.toml` holds the rules of the team for one repository. The administrators own it: a change of it, or of
`.github/`, lands only with the review of an administrator. Each command reads it from the default branch as git
fetched it last, so that each computer uses the merged rules, also when its checkout is old.

## Example

```toml
[team]
admins = ["lead"]                  # GitHub names: they set up GitHub and help when the AI is stuck
reviewers = ["lead", "dba"]        # GitHub names that review a change of a risky path

[risk]
paths = ["db/**", "**/migrations/**", ".github/workflows/**"]

[checks]
required = ["secrets", "tests", "front"]
setup = "python -m pip install -r requirements.txt"

[checks.tests]
command = "python -m pytest -q"
only_when = ["**/*.py", "tests/**"]

[checks.front]
command = "npm ci && npm run build"
cwd = "frontend"
only_when = ["frontend/**"]
ready = "node --version"           # akasha doctor runs it: can this computer run the check?

[ci]
required = ["checks"]              # the required checks of the own CI of the team

[guides]
join = ["docs/JOIN.md"]
preview = ["design/UX.md"]
plan = ["docs/ARCHITECTURE.md"]
review = ["docs/RULES.md"]

[work]
folder = ".akasha/work"
branch_prefix = "akasha/"
records = "docs/tasks/akasha"      # a folder that the own checkers of the team skip

[deploy]
workflow = "Deploy"                # the workflow that deploys each merge

[server]
rules = "akasha"                   # setup writes it
```

## `[team]`

| Key | Value |
|:--|:--|
| `admins` | The GitHub names of the administrators. They own `akasha.toml`, `.github/`, and CODEOWNERS: a change of them waits for the review of an administrator. They change the GitHub settings, and get the questions of `akasha help` and the reports of the watch |
| `reviewers` | The GitHub names that review a change of a path of `[risk]`. The landing waits for the approval of one of them |

Where GitHub protects the branch, it enforces CODEOWNERS. On a private repository on GitHub Free it does not, so
Akasha reads the reviews of the pull request itself before it merges, and the watch reports a merge by hand without
them. The person who made the change does not count: when no reviewer is free, an administrator reviews, and the
other way around.

## `[risk]`

| Key | Value |
|:--|:--|
| `paths` | File patterns. A change of a matching file waits for the review of a reviewer before the merge. Keep the list short: each risky path makes a person wait |

## `[checks]`

| Key | Value |
|:--|:--|
| `required` | The checks that must pass. `secrets` is built in: it finds secret keys in the changed files. The default is `["secrets"]` |
| `setup` | The command that prepares a new work copy and the checkout of the check of Akasha, for example `npm ci` |
| `run_all_when` | File patterns: a change of one runs each check, also a check with `only_when`. The default is the dependency files, `akasha.toml`, and `.github/workflows/**` |
| `tests`, `lint` | One command line, the same as a table with only `command` |
| `[checks.<name>]` | One check, below |

### `[checks.<name>]`

| Key | Value |
|:--|:--|
| `command` | The command. The check passes when it stops with the exit code 0 |
| `cwd` | The folder of the command, relative to the top of the repository |
| `only_when` | File patterns, relative to the top of the repository. The check runs only when a changed file matches; else it is NOT_NEEDED, which is a pass |
| `command_windows` | The command on Windows, for `cmd.exe` |
| `ready` | A quick command that passes when this computer can run the check, for example `python -c "import pytest"`. `akasha doctor` runs it; without it, doctor looks for the program of the command |

The commands run in the shell of the operating system: `cmd.exe` on Windows, `/bin/sh` elsewhere. A pattern: `*`
matches each character, also `/`; a leading `**/` also matches at the top; a pattern that ends with `/` matches each
file in the folder.

## `[ci]`

| Key | Value |
|:--|:--|
| `required` | The names of the required checks of the own CI of the team, as GitHub shows them. With it, Akasha installs no check of its own. Each named check must really run on a pull request that is ready: a check that only skips never passes for Akasha |
| `runs-on` | The machine of the check of Akasha: a label, or a list of labels of a runner of the team. The default is `ubuntu-latest` |
| `python` | The Python of the check of Akasha, as text, 3.11 or higher. The default is `"3.12"` |

## `[guides]`

The files of the team that the AI reads in each step. The session start notice names them.

| Key | The AI reads the files |
|:--|:--|
| `join` | When a new teammate gets ready (akasha-join): the programs, packages, settings of the network, and local files that the checks need |
| `preview` | Before it makes the preview: the design, the words on the screen |
| `plan` | Before it writes the research and the plan: the architecture, the rules |
| `build` | While it builds |
| `review` | The reviewer reads them for the review of the plan |

## `[work]`

| Key | Value |
|:--|:--|
| `folder` | The folder of the work copies, in the repository. The default is `.akasha/work`. Git must not track files in it |
| `branch_prefix` | The prefix of the task branches. The default is `akasha/` |
| `records` | The folder of the records of the tasks (preview, research, plan, summary), which go into git. The default is `.akasha/tasks`. Choose a folder that the own checkers of the team skip, for example a Markdown checker. A task keeps the folder that was set when it started |

## `[deploy]`

| Key | Value |
|:--|:--|
| `workflow` | The name of the workflow that deploys each merge to the default branch, as GitHub shows it. After the merge, `akasha land` waits for its run on the merge commit and says DEPLOYED, DEPLOY_FAILED, or DEPLOYING. When the workflow does not start for a change (for example a filter of paths), the result stays MERGED |

## `[server]`

| Key | Value |
|:--|:--|
| `rules` | `github` when GitHub protects the default branch, `akasha` where it does not. `akasha setup` writes `akasha` when the branch has no protection, and `akasha setup --apply` writes the rules of the plan. Do not change it by hand. Before each landing Akasha also asks GitHub: a branch without protection is always merged by Akasha, after its examination |

## How Akasha examines this file

Akasha refuses an unknown section, an unknown key, and a value of the wrong type, with the name of the key.
