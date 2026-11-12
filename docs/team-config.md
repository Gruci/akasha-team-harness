# Team config

`akasha.toml` holds the rules of the team for one repository, at the top of the repository or in `.github/` (for a
repository that allows only listed files at the top). The administrators maintain it: a teammate's task cannot change
it, or `.github/`. Each command reads it from the default branch as git fetched it last, so that each computer uses
the merged rules, also when its checkout is old.

## Example

```toml
[team]
admins = ["lead", "dba"]           # GitHub names: they keep the rules, and approve a change of the structure
agents = ["ops-bot"]               # GitHub names of agent accounts: a person approves their result before the merge
version = "2.0.0"                  # the Akasha of the team: the CI and the watch run it, and each computer a 2.0.x

[risk]
paths = ["db/**", "**/migrations/**", "deploy/**"]     # only an administrator changes them

[core]
areas = ["domains/*", "src/features/*"]   # folders of one feature each
paths = ["schema/**"]                     # an administrator approves a change of their existing lines
used_by = 2                               # a file that 2 or more other areas import is core

[preview]
data = ["src/queries/**"]          # files that make data: their previews define each value that they show
screens = ["frontend/**", "**/*.html"]   # files that make a screen: an administrator's task without them has no preview
check = "python scripts/check_words.py"  # a check of a preview: `akasha preview` runs it once, with the path of the preview

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

[checks.queries]
command = "python -m pytest -q tests/db"
only_when = ["src/queries/**", "db/**"]
kind = "integration"               # it runs against a real database: a change of [preview] data needs it

[ops]
migrations = ["db/migrations/**"]  # a new line there that removes a table or a column fails
env = [".env.example"]             # a new setting that this file does not name fails

[size]
function = 100                     # lines of one function that a change makes or makes longer
file = 800                         # lines of one file of code: a longer file does not grow
task = 1500                        # lines of code that one task changes

[models]
work = "sonnet"                    # the model of akasha-worker
review = "opus"                    # the model of akasha-reviewer: never weaker than the worker

[ci]
required = ["checks"]              # the required checks of the own CI of the team

[guides]
join = ["docs/JOIN.md"]
preview = ["design/UX.md", "docs/DATA.md"]   # the words and the design of the screens; how to read the data
plan = ["docs/ARCHITECTURE.md"]
review = ["docs/RULES.md"]

[work]
folder = ".claude/worktrees"
branch_prefix = "akasha/"
records = "docs/tasks/akasha"      # the records of a task in work: a folder that the own checkers of the team skip
archive = "docs/tasks/done"        # the records of the merged tasks: done/2026/11/2026-11-07-<task>/

[deploy]
workflow = "Deploy"                # the workflow that deploys each merge
verify = "python scripts/smoke.py" # it passes when the change works live

[server]
rules = "akasha"                   # setup writes it
```

## `[team]`

A team has three roles: the administrators and the agent accounts, named here, and the teammates, who are each other
person with write access. Nobody reviews a task, except a change of the structure: existing lines of the core
(`[core]`), the sheet of an area, and a contract. An administrator approves it on GitHub. The administrators keep the
rules: Akasha, the map, and the risky parts. They are no reviewers and no answerers of the other tasks. A teammate
approves the preview of their own request; the person who asked an agent account approves its result before the merge
(see "An agent task" in [how it works](how-it-works.md)).

| Key | Value |
|:--|:--|
| `admins` | The GitHub names of the administrators. Only they change `akasha.toml`, `.github/`, CODEOWNERS, and the paths of `[risk]`. They change the GitHub settings, and get the questions of `akasha help` and the reports of the watch. The AI talks with them as with developers, and they can make a task without a screen (`[preview] screens`) |
| `own_procedure` | The GitHub names of the people who keep the own procedure of the repository outside Akasha, for example the administrator who built it. Akasha does not stop their work outside its tasks (their own work copies, edits in the main checkout, their merges), and the watch accepts their pull requests when the checks passed. The other rules (a force push, a push to the default branch, `.env`) stay |
| `agents` | The GitHub names of agent accounts: a program (the relay) runs their sessions and gives them the requests of people. Each task of such an account is an agent task, without a preview: the person approves the result before the merge. An agent account has the rules of a teammate, so it cannot also be in `admins` or `own_procedure`. An older Akasha does not know this key: it treats an agent account as a teammate, which needs a preview |
| `version` | The version of Akasha that the team uses, for example `"2.0.0"`. An administrator chooses it: `akasha setup` writes the running version only when the setting is empty, and never changes it after that. The CI and the watch run that version itself. A computer runs it or another patch of the same minor version (2.0.x): a patch changes no rule. An Akasha of another minor version starts, continues, and lands no task. See "Change the rules, or update Akasha" in [set up a team](admin.md) |

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

Put only files that one screen or one area reads. For example, a team whose pages each have their own style sheet and
whose settings of one job are in their own file:

```toml
[quick]
paths = [
  "src/pages/*/*.module.css",   # the style of one page: only that page imports it
  "config/jobs/*.yaml",         # the settings of one job: only that job reads its file
  "locales/*/help.json",        # the help text of the help screen
]
```

Here `src/styles/global.css` and `config/app.yaml` stay out: each screen reads them, so a change of them needs a full
task with a preview. A pattern that ends with `/` means each file under that folder.

Code of Python, JavaScript, and TypeScript needs no pattern: Akasha finds its users from the imports. Text for people
needs no pattern either. A quick task that changes only text for people needs no review of the akasha-reviewer agent:
`impact.md` and the approval of the person are enough. Each other quick task, also one of a file of `paths`, needs the
review.

## `[preview]`

Each preview of a full task specifies the change: its rules, and the source, formula, value now, and check of each
value from data that it shows (see "The preview specifies the change" in [how it works](how-it-works.md)). This
section makes Akasha sure that a change of data shows its values: the AI cannot forget to mark them.

| Key | Value |
|:--|:--|
| `screens` | File patterns of the files that make a screen, for example `["frontend/**", "templates/**", "**/*.css"]`. An administrator can start a task whose scope holds none of them with `akasha start --no-screen`: the person approves its plan in place of a preview, and the check `screen` fails when its change touches one (see "A task without a screen" in [how it works](how-it-works.md)). Name each kind of file that a screen shows: a file that this list misses can change without a preview. Without it, each task of a person has a preview |
| `data` | File patterns of files that make data that people see, for example `["src/queries/**", "src/reports/**"]`. A task that plans one must mark one value or more in its preview, `akasha check` fails the check `data` when the change touches one and the preview defines no value, and a quick task never changes one. How a teammate reads the data for a preview (a copy of the database, a read-only account, an API) goes into a file of `[guides] preview` and `[guides] join` |
| `check` | A command of the team that examines a preview, for example the words of the screen. `akasha preview` runs it once in the work copy of the task, with the path of `preview.html` as its last argument, before the person sees the preview. When it fails, Akasha does not show the preview, and gives the output of the command to the AI. Use it for a check that is needed once for each preview: a check at the end of each turn of the agent runs many times for nothing. A quick task has no such check |

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
| `kind` | `"integration"` for a check that runs against a real store, for example a database with the tables of the product. A change of a file of `[preview] data` then fails (the check `integration`) when no such check ran: a query that never ran is not proven. The check runs on the computer of the person, and on the server only where the team names it in `required` |

The commands run in the shell of the operating system: `cmd.exe` on Windows, `/bin/sh` elsewhere. A pattern: `*`
matches each character, also `/`; a leading `**/` also matches at the top; a pattern that ends with `/` matches each
file in the folder.

## `[ci]`

| Key | Value |
|:--|:--|
| `required` | The names of the required checks of the own CI of the team, as GitHub shows them. GitHub must see them pass before a merge, together with the check of Akasha (`akasha`). Akasha installs its check in each case (`.github/workflows/akasha.yml`), also beside the CI of the team: it runs the required checks of `[checks]` and the checks of Akasha on the server (first the version check, which fails when the Akasha on the server is not `[team] version`, then the quick check of quick tasks, the screen check of tasks without a screen, the evidence check: the approval of the person and the passed review in the records of the task, for the current version of what they hold, and the consistency check: a new public name that the repository has already, without an answer in the plan). The CI of the team need not run a command of Akasha: a team whose CI ran `python -m akasha check --ci` removes that step. Each named check must really run: a check that only skips never passes for Akasha |
| `runs-on` | The machine of the check of Akasha: a label, or a list of labels of a runner of the team. The default is `ubuntu-latest` |
| `python` | The Python of the check of Akasha, as text, 3.11 or higher. The default is `"3.12"` |

Akasha opens a task as a draft pull request, pushes it only after `akasha check` passed on the computer, and marks it
ready at the landing. The landing counts a run of a check that passed on the same commit while the pull request was a
draft. So the CI of the team can run during the build, not only at the end. To get this, change the workflow of the
own CI:

- Run it on draft pull requests: remove a condition such as `if: github.event.pull_request.draft == false`.
- Do not start it again when a draft gets ready: remove `ready_for_review` from `on: pull_request: types`. Keep
  `opened`, `synchronize`, and `reopened`. Where GitHub protects the default branch, GitHub decides with the latest run
  of a required check on the head, so a second run of the same commit makes the merge wait again.

A CI that skips drafts still works: its checks run once, after the landing marks the pull request ready. The check
of Akasha already runs on drafts.

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
| `folder` | The folder of the work copies, in the repository. The default is `.claude/worktrees`: Claude Code moves a session into a folder there without asking, and asks once for each task anywhere else. Git must not track files in it |
| `branch_prefix` | The prefix of the task branches. The default is `akasha/` |
| `records` | The folder of the records of a task in work (preview, research, plan, summary): `<records>/<task>/`. The default is `.docs/tasks`. Only the branch of the task has this folder: the default branch never holds it. Choose a folder that the own checkers of the team skip, for example a Markdown checker |
| `archive` | The folder of the records of the merged tasks. The default is `.docs/archive`. The landing moves the records of a task there, into `<archive>/YYYY/MM/YYYY-MM-DD-<task>/` (the date of the move), in the push that it makes anyway, and the merge brings them into the default branch. No work copy and no main checkout holds the archive of other tasks (git sparse-checkout), and Akasha reads the folder of one task only: the records of old tasks are no input of a new task, however many there are. A task changes no folder of another task in the archive: only an administrator does. A merged task gives its name free: the date keeps the folders apart, and a second task of the same name on the same day gets `YYYY-MM-DD.<number of the pull request>-<task>` |

> **IMPORTANT:** Choose `records` and `archive` when Akasha comes into the repository. Akasha refuses a later change
> of them (`akasha check`, and the check on the server): after a change, each new work copy would hold the old archive
> again. Neither folder can be in the other, in the work folder, or in `.docs/state`.

## `[deploy]`

| Key | Value |
|:--|:--|
| `workflow` | The name of the workflow that deploys each merge to the default branch, as GitHub shows it. After the merge, `akasha land` waits for its run on the merge commit and says DEPLOYED, DEPLOY_FAILED, or DEPLOYING, or VERIFY_FAILED with `verify`. When the workflow does not start for a change (for example a filter of paths), the result stays MERGED |
| `verify` | A command that passes when the change works live, for example a script that opens the main pages. After a deployment that passed, `akasha land` runs it at the top of the main checkout. It fails: VERIFY_FAILED, and the AI asks an administrator and offers to undo the change. Without it, a passed deployment is DEPLOYED |

## `[server]`

| Key | Value |
|:--|:--|
| `rules` | `github` when GitHub protects the default branch, `akasha` where it does not. `akasha setup` writes `akasha` when the branch has no protection, and `akasha setup --apply` writes the rules of the plan. Do not change it by hand. Before each landing Akasha also asks GitHub: a branch whose protection does not require each check of the team is always merged by Akasha, after its examination |

## `[definitions]`

```toml
[definitions]
on = true
```

`on = true` turns on the list of the definitions of the team: `akasha.definitions.toml` beside `akasha.toml`. A
definition gives one meaning to a business value or a feature that more than one place uses, with the code that
holds it, the way in from outside, and the test that confirms it. A new repository starts with it on; a repository
that has code turns it on when an administrator decides.

```toml
[[definition]]
key = "corp.active_count"                     # one key for one meaning: <area>.<what it is>
label = "Active companies"                    # the main word on each screen
aliases = ["Companies"]                       # other words for the same thing
meaning = "The companies that are active on the reference day. A company in liquidation does not count"
area = "domains/corp"                         # the area that keeps this meaning (needed with [core] areas)
implementation = ["domains/corp/queries/count.py::count_active"]      # the code to change
entry = ["domains/corp/api.py::count_active", "GET /api/corp/count"]  # the way in from outside (optional)
tests = ["tests/contracts/test_corp_count.py"]                        # the test that confirms the meaning
```

| With the list on | The rule |
|:--|:--|
| A value row of a preview | Names a definition: `<tr data-akasha-key="…" data-akasha-definition="<key>">`, or `"local"` for a value of this screen only. `akasha preview` refuses a row without it |
| A new public entry | A new address of the server, and a name that an entry file of an area (`public` of `[boundaries]`) newly gives out, is in the `entry` of a definition, or has a row `entry` in `## Public changes` of `plan.md` that names exactly that entry (`GET /api/health`, or `path::name`) with the reason |
| A new definition | Each person adds one. It has a key, a label, a meaning, an implementation, and tests that are in the code; the blocks are in the order of their keys |
| A change of a definition | Only a task of an administrator changes or removes a block, with a row `change` of that key in the plan. A change of blanks or comments is no change |
| A change of registered code | A task that changes a file of an `implementation` has a row `change` of that file in the plan: what stays the same for the places that use it |
| The file | A missing or broken file fails. A file without a block is a correct empty list. Only `on = false` turns the list off, in a task of an administrator |

The policy (`on`, and who is an administrator) comes from the default branch: a pull request cannot give itself the
right. `akasha map --definitions` shows the list, `akasha find` searches the labels and the aliases, and `akasha
start` names each definition that the task touches. The board tells two open tasks that add or change the same key.

## `[boundaries]`

```toml
[boundaries.areas]
private = ["domains/*/**"]                              # the files of an area
public = ["domains/*/api.py", "domains/*/index.ts"]     # are open to the outside only through these entries
except = ["app/main.py -> domains/billing/jobs/nightly.py"]     # one exact pair

[boundaries.screen-data]
from = ["frontend/**"]                                  # these files
not = ["db/**"]                                         # do not import these files

[boundaries.no-cycles]
acyclic = ["domains/*"]                                # the imports between these areas make no circle
```

Each table under `[boundaries]` is one rule with a name of the team. A rule with `private` and `public` asks one
question: is the target of an import that crosses an area the public entry of that area? Imports inside an area are
free, and an area is a folder of `[core] areas`. A rule with `from` and `not` forbids the imports of some files by
others. `except` holds exact pairs for the rule that names them.

The check `consistency` fails only an import that the change makes new, so a repository with old crossings can turn
a rule on. An entry file names what it gives out: a plain `__all__` list in Python, `export { a, b } from` in
TypeScript; else the check fails with the file. The import graph reads the `paths` of `tsconfig.json` and
`jsconfig.json`, and a note names an import that Akasha cannot follow. The rule holds for static imports. It does
not see a call through an address, or an access while the code runs. Two entries that import each other pass the
rule of the entries: a rule with `acyclic` fails a new relation between two of its areas that is on a cycle, also
when that cycle was there before. It counts an import of a type only too, so it does not prove that the code
has no cycle while it runs.

## The sheet of an area: `area.toml`

The map of the product is one sheet in the folder of each area of `[core] areas`. `akasha map --draft` writes the
first sheets, and `akasha map` joins them with the code.

```toml
purpose = "Takes an order and changes its state"    # one line: what the area keeps
owners = ["mina"]                                   # GitHub names
uses = ["catalog", "payments"]                      # the areas that its code calls
contracts = ["openapi.yaml"]                        # files of the area that other parts rely on
tables = ["orders", "order_items"]                  # the tables that only this area writes
```

| Key | Value |
|:--|:--|
| `purpose` | One line that tells what the area keeps. A sheet without it, or with a TODO, fails the check `map` |
| `owners` | The GitHub names of the people who answer for the area. `akasha map` shows them |
| `uses` | The areas that the code of this area may call: the whole folder of an area, or its last folder when no other area ends with it. A new import of another area fails until the sheet names it |
| `contracts` | File patterns inside the area. A change of existing lines of such a file waits for the approval of an administrator, as a change of core code does |
| `tables` | The tables that only this area writes. New code of another area that writes one of them (`insert into`, `update`, `delete from`) fails. A table is in one sheet only |

A change of a sheet waits for the approval of an administrator at the landing: a new area, a new arrow between two
areas, and a new owner of a table are decisions about the structure. The check `map` looks only at what a change
makes new, and runs only in a repository that has one sheet or more.

## `[ops]`

The check `ops` reads the lines that a change adds, and stops the usual ways in which code that passes its tests
still fails after the deployment. Akasha cannot see a server: the deployment, the monitoring, and the capacity of the
product are of the team, and `[deploy] verify` examines the product after each deployment.

| Key | Value |
|:--|:--|
| `migrations` | The files that change the database. The default is each file in a folder `migrations` or `migrate`. A new line there that removes or renames a table or a column fails (`migration`): the code that runs now still reads the old shape while the deployment goes on. Two migrations with one number fail too |
| `env` | The files that name each setting of the server. The default is `.env.example`, `.env.sample`, `.env.template`, or `.env.dist` in any folder. A new line that reads a setting that no such file names fails (`env`). A repository without such a file has no rule |
| `off` | Rules that the team does not use: `migration`, `env`, `timeout` (a call of another system without a time limit: `requests`, `httpx`, and `urlopen` of Python), `silent` (an error that the code catches and does nothing with: Python, JavaScript, and TypeScript) |
| `allow` | `"<rule>: <file pattern>"`: the rule does not hold for these files, for example the last task that removes an old column: `"migration: db/migrations/0042_drop_old.sql"` |

## `[size]`

| Key | Value |
|:--|:--|
| `function` | Lines of one function. A function that the change makes or makes longer is not over it (Python; the linter of the team holds it for another language). The default is `100`; `0` turns it off |
| `file` | Lines of one file of code. A file over it does not grow, and a file under it does not go over it. The default is `800` |
| `task` | Lines of code that one task changes, without tests and records. A move of a file counts as no change. The default is `1500`. An administrator gets a note in place of a failure: a rename across the repository is their task |

A limit is a signal, and the goal is code where one part changes for one reason. So the check never asks to cut an
old file into pieces: it looks only at what the change makes new or longer.

## `[models]`

| Key | Value |
|:--|:--|
| `work` | The model of the akasha-worker agent: the preview, the plan, and the build |
| `review` | The model of the akasha-reviewer agent. Without it, the agent uses the model of its own file. Keep it as strong as the worker or stronger |

`akasha status <task> --brief` names them, and the session starts each agent with its model. The checks of the
product decide whether a weaker model can build, not the trust in the model.

## `[pins]`

```toml
[pins]
policy = "new"
```

Whether the versions of the libraries and of the base images of the repository are fixed. When they float, the same
commit installs other things on another day, and a deployment that goes back installs other versions than before.
Akasha makes an administrator know and decide. It stops nothing without an answer, and it never chooses a version.

| `policy` | Meaning | The check |
|:--|:--|:--|
| no value | The administrator did not answer yet | None. `akasha doctor` tells each person in one line, and `akasha setup` asks |
| `"observe"` | Known, and left as it is. Right for a library that others install: its ranges are correct | None. Only `akasha map --report` shows the count |
| `"new"` | What is there stays, and no change adds more | The check `consistency` fails a change that adds a library without a fixed version, a base image that floats, or that takes away a lock file |
| `"all"` | Each one is fixed | It fails while a library without a fixed version or a floating base image is in the repository |

Akasha reads one list and its pair at a time: `requirements*.txt` (with the files of `-r` and `-c`), `pyproject.toml`,
and `package.json`, each with the lock in the same folder (`uv.lock`, `poetry.lock`, `pdm.lock`, `package-lock.json`,
`npm-shrinkwrap.json`, `pnpm-lock.yaml`, `yarn.lock`). With the lock, a range is fixed, and only a library without
any version counts. Without it, each line that is not exact (`name==version`, or one exact version) counts. A lock
of the frontend fixes nothing of the server. In a `Dockerfile`, an image without a tag or with a tag without a number
(`latest`, `slim`) floats; a tag without a patch version or a digest (`python:3.11-slim`) is only named. An earlier
stage of the same file and `scratch` are no image of outside.

The policy comes from the default branch, and the check also runs for a pull request that is no task. Where the
policy protects, a file that Akasha cannot read fails: it is no pass. Akasha does not judge whether a lock is old,
does not raise a version (that is the work of Dependabot or Renovate), and does not see what a deployment really
installs. A change from `"observe"` to `"new"` or `"all"` is a task of an administrator.

## `[review]`

```toml
[review]
command = "…"          # it takes the request on its standard input, and prints the answer of the reviewer
files = []             # the files of the repository that the command needs; none: only installed programs
timeout = 900          # seconds
```

A reviewer for an agent engine that has no reviewer agent of its own. `akasha review <task>` runs the command in a new
empty folder, in its own process. The request is JSON on the standard input: an id, the task, its kind, the subject
(`plan` or `change`), the digest, the absolute paths of the work copy and of the records, the Akasha command, the path
of the instruction of the reviewer, and the base commit. Nothing of the task is in the text of the command. The files
of `files` come from that base commit, not from the work copy: a task does not review itself with a reviewer that
it changed.

The answer is the whole standard output: the table of the items and the mark `AKASHA-REVIEW: <task> <digest> PASS`
or `CHANGES`, as the akasha-reviewer agent writes them. The mark must name the task and the digest of the request, and
the digest must still be the same when Akasha records it. A failure never becomes a pass. With a command, Akasha
takes no `akasha review --verdict`. Which command to use is the choice of the team: see the documents of the agent
engine for how to run it without a person.

## How Akasha examines this file

Akasha refuses a value of the wrong type, with the name of the key. It skips a section or a key that it does not
know, for example a setting of a newer Akasha, and the session start notice names it.
