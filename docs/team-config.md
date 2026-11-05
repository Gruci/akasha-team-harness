# Team config

`akasha.toml` holds the rules of the team for one repository, at the top of the repository or in `.github/` (for a
repository that allows only listed files at the top). The administrators maintain it: a teammate's task cannot change
it, or `.github/`. Each command reads it from the default branch as git fetched it last, so that each computer uses
the merged rules, also when its checkout is old.

## Example

```toml
[team]
admins = ["lead", "dba"]           # GitHub names: they set up and maintain Akasha, and help when the AI is stuck
agents = ["ops-bot"]               # GitHub names of agent accounts: a person approves their result before the merge

[risk]
paths = ["db/**", "**/migrations/**", "deploy/**"]     # only an administrator changes them

[core]
areas = ["domains/*", "src/features/*"]   # folders of one feature each
paths = ["schema/**"]                     # an administrator approves a change of their existing lines
used_by = 2                               # a file that 2 or more other areas import is core

[preview]
data = ["src/queries/**"]          # files that make data: their previews define each value that they show

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
preview = ["design/UX.md", "docs/DATA.md"]   # the words and the design of the screens; how to read the data
plan = ["docs/ARCHITECTURE.md"]
review = ["docs/RULES.md"]

[work]
folder = ".akasha/work"
branch_prefix = "akasha/"
records = "docs/tasks/akasha"      # a folder that the own checkers of the team skip

[deploy]
workflow = "Deploy"                # the workflow that deploys each merge
verify = "python scripts/smoke.py" # it passes when the change works live

[server]
rules = "akasha"                   # setup writes it
```

## `[team]`

A team has three roles: the administrators and the agent accounts, named here, and the teammates, who are each other
person with write access. Nobody reviews a task, except a change of existing lines of the core (`[core]`): an
administrator approves it on GitHub. The administrators set up and maintain Akasha and the risky parts; a teammate
approves the preview of their own request; the person who asked an agent account approves its result before the merge
(see "An agent task" in [how it works](how-it-works.md)).

| Key | Value |
|:--|:--|
| `admins` | The GitHub names of the administrators. Only they change `akasha.toml`, `.github/`, CODEOWNERS, and the paths of `[risk]`. They change the GitHub settings, and get the questions of `akasha help` and the reports of the watch |
| `own_procedure` | The GitHub names of the people who keep the own procedure of the repository outside Akasha, for example the administrator who built it. Akasha does not stop their work outside its tasks (their own work copies, edits in the main checkout, their merges), and the watch accepts their pull requests when the checks passed. The other rules (a force push, a push to the default branch, `.env`) stay |
| `agents` | The GitHub names of agent accounts: a program (the relay) runs their sessions and gives them the requests of people. Each task of such an account is an agent task, without a preview: the person approves the result before the merge. An agent account has the rules of a teammate, so it cannot also be in `admins` or `own_procedure`. An older Akasha does not know this key: it treats an agent account as a teammate, which needs a preview |

## `[risk]`

| Key | Value |
|:--|:--|
| `paths` | File patterns of the parts that only an administrator changes, for example the database and the deployment. In a teammate's task, Akasha stops an edit of a matching file, and the check `admin_only` fails; the AI asks an administrator with `akasha help`. On GitHub Free the watch reports a merge that changed one. Keep the list short: each path sends work to an administrator |

## `[core]`

The core is the code that other areas use. A teammate's task adds anything freely, also new lines in a core file. Only
a change or a delete of existing lines of a core file waits: the landing stops with BLOCKED until an administrator
approves the pull request on GitHub. Akasha never stops the edit. The administrators and the people of
`[team] own_procedure` are free of it.

| Key | Value |
|:--|:--|
| `areas` | Folder patterns of one feature each, for example `"domains/*"` or `"src/features/*"`. A file belongs to the folder of the first pattern that holds it. Without a match, the area is the first two folders of the path |
| `used_by` | A file that so many other areas import is core. A whole number of 1 or more. The default is `2`. Imports by tests do not count |
| `paths` | File patterns of files that are core in any case, for example the definitions of the database. A teammate can still edit them; only a change of their existing lines waits for the approval |

Akasha finds the imports of Python, JavaScript, and TypeScript. It does not see a call of an API by its address, a
table name in the text of SQL, or another language: put such files into `paths`.

## `[quick]`

A quick task changes only existing files that no other area uses, for example a typo or one setting (see "A quick
task" in [how it works](how-it-works.md)). Akasha knows the users of code of Python, JavaScript, and TypeScript from
the imports, and text for people (`*.md`, `*.txt`, `*.rst`, `*.adoc`) has none. It cannot tell who uses another kind
of file, for example a CSS file, a template, or a settings file: a quick task changes such a file only when it matches
`paths`.

| Key | Value |
|:--|:--|
| `paths` | File patterns of files other than code and text that a quick task can change, for example `["config/messages/*.json", "src/pages/*/*.css"]`. Do not put files that many screens read here, for example a global style sheet |

## `[preview]`

Each preview of a full task specifies the change: its rules, and the source, formula, value now, and check of each
value from data that it shows (see "The preview specifies the change" in [how it works](how-it-works.md)). This
section makes Akasha sure that a change of data shows its values: the AI cannot forget to mark them.

| Key | Value |
|:--|:--|
| `data` | File patterns of files that make data that people see, for example `["src/queries/**", "src/reports/**"]`. A task that plans one must mark one value or more in its preview, `akasha check` fails the check `data` when the change touches one and the preview defines no value, and a quick task never changes one. How a teammate reads the data for a preview (a copy of the database, a read-only account, an API) goes into a file of `[guides] preview` and `[guides] join` |

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
| `required` | The names of the required checks of the own CI of the team, as GitHub shows them. With it, Akasha installs no check of its own. Each named check must really run on a pull request that is ready: a check that only skips never passes for Akasha. The CI of the team then runs `python -m akasha check --ci --config <akasha.toml of the base branch> --base origin/<base branch>` too, for the quick check of quick tasks on the server |
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
| `review` | The AI that checks the plan reads them too |

## `[work]`

| Key | Value |
|:--|:--|
| `folder` | The folder of the work copies, in the repository. The default is `.akasha/work`, or a `worktrees` folder that the repository already ignores. Git must not track files in it |
| `branch_prefix` | The prefix of the task branches. The default is `akasha/` |
| `records` | The folder of the records of the tasks (preview, research, plan, summary), which go into git. The default is `.akasha/tasks`. Choose a folder that the own checkers of the team skip, for example a Markdown checker. A task keeps the folder that was set when it started |

## `[deploy]`

| Key | Value |
|:--|:--|
| `workflow` | The name of the workflow that deploys each merge to the default branch, as GitHub shows it. After the merge, `akasha land` waits for its run on the merge commit and says DEPLOYED, DEPLOY_FAILED, or DEPLOYING, or VERIFY_FAILED with `verify`. When the workflow does not start for a change (for example a filter of paths), the result stays MERGED |
| `verify` | A command that passes when the change works live, for example a script that opens the main pages. After a deployment that passed, `akasha land` runs it at the top of the main checkout. It fails: VERIFY_FAILED, and the AI asks an administrator and offers to undo the change. Without it, a passed deployment is DEPLOYED |

## `[server]`

| Key | Value |
|:--|:--|
| `rules` | `github` when GitHub protects the default branch, `akasha` where it does not. `akasha setup` writes `akasha` when the branch has no protection, and `akasha setup --apply` writes the rules of the plan. Do not change it by hand. Before each landing Akasha also asks GitHub: a branch whose protection does not require each check of the team is always merged by Akasha, after its examination |

## How Akasha examines this file

Akasha refuses a value of the wrong type, with the name of the key. It skips a section or a key that it does not
know, for example a setting of a newer Akasha, and the session start notice names it.
