# Commands

The agent engine runs these commands. The session start notice gives the full command for the computer, for example
`"<python>" -X utf8 "<plugin>/akasha_run.py" <command>`. With the package installed, it is `python -m akasha <command>`
or `akasha <command>`.

| Command | Function |
|:--|:--|
| `setup --new [--stack <languages>] [--areas <folder>] [--entries <files>]` | The first setup of a repository that starts now. Beside the files of `setup`, it turns the definitions on with an empty `akasha.definitions.toml` (its head holds a correct first example), writes the structure guide `docs/architecture.md` from a template (the six rules of the structure are fixed text; the administrator answers the blanks), names it in `[guides] plan` and `review`, and puts it and the rule files of the lint into `[risk] paths`, so that a task does not change the standard that judges it. With `--areas "domains/*" --entries api.py,index.ts` it writes `[core] areas` and the boundary of the entries. `--stack python,typescript` chooses the languages; without it, Akasha finds them by the files and the manifests (`pyproject.toml`, `package.json`, `go.mod`). Each language gets its tests and its lint as required checks, each with its files in `only_when`. Both options are only for the first setup |
| `setup` | Write the files of Akasha into the checkout. `--apply` also changes the GitHub settings (an administrator). It writes the running version into an empty `[team] version`, and never changes a version that is there: an administrator changes it. It pins that version for Claude Code, Codex, and the workflows, and refuses a version without a release tag in the public repository |
| `doctor` | What this person needs to work in the repository, with the fix of each problem. It fails when this computer runs another Akasha than `[team] version`, older or newer |
| `start "<title>" [--name <name>] [--scope <patterns>] [--quick] [--no-screen]` | Start a task: a work copy on a new branch, and a draft pull request on the board. `--quick` starts a quick task: a small change of existing files that no other area uses, without a preview of the result and a plan. `--no-screen` starts a task without a screen, only for an administrator: it needs `--scope`, the scope holds no file of `[preview] screens`, and the person approves the plan in place of a preview. It does not go with `--quick`. An agent account (`[team] agents`) always starts an agent task: Akasha writes the last prompt of the session into `request.md` |
| `split <task> <part> --scope <patterns>` | Make a part of a task that is ready to build, for a worker at the same time as others: a work copy `<work folder>/<task>--<part>` on a local branch from the branch of the task. The part changes only the files of its scope, and no two parts have the same files |
| `join <task> [--keep]` | Merge each part into the work copy of the task, then remove the part. A conflict stops with the files. The landing waits until each part joined |
| `upgrade <task>` | Make a quick task a full task: the person approves a preview, and the reviewer passes a plan. The change so far stays |
| `preview <task> --check` | Only examine the preview, as `preview` does: show nothing, and change no state of the task. A step in a new context uses it |
| `preview <task> [--text <text>] [--no-open]` | Show the preview to the person and wait for the approval. It refuses a preview of a full task without the decisions and the rules, and a value of data without its definition. `--text` writes a first draft with the decisions only, when there is no preview yet: add the rules, then show it again. For a task without a screen, it records that the person sees the plan as the reviewer passed it |
| `approve <task>` | Record the approval from the last message of the person after the preview (the result of an agent task, the plan of a task without a screen), in this session. It writes `approval.json` into the records: what the person approved by its digest, who, and when; never their words |
| `approve <task> --here` | For an agent engine without a hook for the words of the person: the person runs it in their own terminal. It shows the task, the work copy, the branch, the subject, and its digest, and takes the name of the task as the approval. It refuses when the input is no terminal, when the name is another one, and when the subject changed while the person read. It sees only that a terminal is there: it does not prove that a person typed |
| `review <task> --verdict pass\|changes` | Record a self-review, only where the akasha-reviewer agent does not exist (not in Claude Code) and the team has no reviewer command |
| `review <task>` | Run the reviewer command of the team (`[review] command`) in its own process, and record its verdict. A timeout, an exit code that is not zero, a missing row, or a wrong mark is a failure, never a pass |
| `check <task> [--only <checks>]` | Run the consistency check (a new public name that the repository has already needs an answer in `## Public changes` of `plan.md`), then the checks of the team. When each passes, save the work and push it. With `--only`, run only those checks and save nothing: run `check <task>` before `land`. When the change touches a file of `[preview] data`, the check `data` fails while the preview defines no value. In a task without a screen, the check `screen` fails when the change touches a file of `[preview] screens` |
| `land <task> [--wait <seconds>]` | Make the pull request ready and merge it when the checks pass, then follow the deployment of `[deploy]` and run its `verify`. Exit code 3: still waiting (WAITING, DEPLOYING). Exit code 4: an agent task waits for the approval of its result (ASK) |
| `result <task>` | An agent task, after the landing said ASK: the text for the person (the summary, the change between two fixed commits, the changed files). Only a message of this session after it approves the result |
| `status [<task>]` | The tasks on this computer, the records folder, the plan digest (the change digest of a quick task), and the next step |
| `status <task> --brief` | One screen for a step in a new context and for the session that leads the steps: the kind, the work copy, the records, the next step, the digest of the review and its verdict, what stops the task, the guides of the team, and whether a new session loses nothing here |
| `status <task> --resume [--here]` | Continue the task in this session. The session that held it before is stopped at its next edit, and a preview that it showed is shown again here, so that the words of the person count. `--here`: the person runs it in their own terminal, for an agent engine without hooks. A plain `status` moves nothing |
| `status <task> --review` | For the reviewer: the items that did not pass the last review, the items that it may keep, the change of `plan.md` since then with the other files of the review that changed, and the rules for names of the task with the commands that show the code that is there |
| `map [<folder or file>]` | The public names of the code. Without a path: each area with the count of its public names. With a path: each public name with its file, line, signature, and the first line of its description; never a body. It reads Python with `ast` and JavaScript and TypeScript with patterns, and names what it could not read (a syntax error, `__all__` made while the code runs, `module.exports`, `export * from`). Tests, the records, and the work folder are not in it |
| `map --report` | For an administrator, before the team turns on a rule: the files that several areas import, the addresses that several screens call, the names and the bodies that are there more than once, the usual words of the names, the imports that cross a boundary, the areas that import each other, the path of the lint of names (installed, the rule on, wired to a required check, or not confirmed), the languages without a required check, and the versions that float. Each line is `observed` (a fact of the code now) or `policy` (what the team wrote). It makes no rule |
| `map --definitions` | The definitions of the team with their code, their entries, and their tests |
| `map --parts` | The component files that more than one area imports, with the count of the files and of the areas. The count is how far a change reaches, not a model to follow |
| `map --addresses [<start>]` | Each address of the server (the decorators of Python such as `@router.get`), its handler, and the screen files that hold the address as text |
| `find <words>` | Search the words of the names, the descriptions, the signatures, and the paths of the public names: the 20 best |
| `names [<language>]` | The rules for names: the whole card, or the entries of one language. `akasha start` and `status --review` give the lines that fit the task |
| `board [--scope <patterns>]` | The open tasks of the team. With `--scope`, only the open tasks that plan or already change files of these patterns, before a start: the AI reads what they change before it plans |
| `resume <task or #number> [--force]` | Continue a task of the board on this computer. It runs `[checks] setup` in the new work copy |
| `handoff <task>` | Save the work on the server and free the task |
| `cancel <task> [--force]` | Stop a task for good: close its pull request and remove the work copy. When another person holds it, only remove the copy here |
| `help <task> "<text>"` | Ask the administrators on the pull request of the task |
| `ask "<text>"` | Ask the administrators a question that is not a change (data, the server), in an issue |
| `tidy` | Remove the work copies of the tasks whose pull request merged or closed, or that another person holds now |
| `retro` | What stops the work again and again |
| `version` | The version of Akasha |

The results of `land`: MERGED, DEPLOYED, and CLOSED end the task (exit code 0). WAITING and DEPLOYING ask for the same
command again (exit code 3). ASK stops an agent task before the merge until the person approved its result (exit
code 4): run `result <task>`, give its text as the answer, and end the turn. FAILED, CONFLICT, BLOCKED, DEPLOY_FAILED,
and VERIFY_FAILED tell what to do (exit code 1).
BLOCKED also comes when a core change waits for the approval of an administrator. VERIFY_FAILED means that the change
is live, but the command of `[deploy] verify` failed.

The workflows run `check --ci` (the check of Akasha) and `server watch` (the watch). The hooks run `hook --event`
through `hook.sh`, which finds Python 3.11 or higher. A shell line that is exactly one of these commands with the
launcher of the plugin runs without a permission prompt: `start`, `upgrade`, `split`, `join`, `preview`, `approve`, `status`, `check`, `land`,
`result`, `board`, `help`, `ask`, `handoff`, `resume` (without `--force`), `tidy`, `doctor`, `version`, `retro`.
