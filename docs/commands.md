# Commands

The agent engine runs these commands. The session start notice gives the full command for the computer, for example
`"<python>" -X utf8 "<plugin>/akasha_run.py" <command>`. With the package installed, it is `python -m akasha <command>`
or `akasha <command>`.

| Command | Function |
|:--|:--|
| `setup` | Write the files of Akasha into the checkout. `--apply` also changes the GitHub settings (an administrator) |
| `doctor` | What this person needs to work in the repository, with the fix of each problem |
| `start "<title>" [--name <name>] [--scope <patterns>] [--quick]` | Start a task: a work copy on a new branch, and a draft pull request on the board. `--quick` starts a quick task: a small change of existing files that no other area uses, without a preview of the result and a plan. An agent account (`[team] agents`) always starts an agent task: Akasha writes the last prompt of the session into `request.md` |
| `split <task> <part> --scope <patterns>` | Make a part of a task that is ready to build, for a worker at the same time as others: a work copy `<work folder>/<task>--<part>` on a local branch from the branch of the task. The part changes only the files of its scope, and no two parts have the same files |
| `join <task> [--keep]` | Merge each part into the work copy of the task, then remove the part. A conflict stops with the files. The landing waits until each part joined |
| `upgrade <task>` | Make a quick task a full task: the person approves a preview, and the reviewer passes a plan. The change so far stays |
| `preview <task> [--text <text>] [--no-open]` | Show the preview to the person and wait for the approval. It refuses a preview of a full task without the decisions and the rules, and a value of data without its definition. `--text` writes a first draft with the decisions only, when there is no preview yet: add the rules, then show it again || `approve <task>` | Record the approval from the last message of the person after the preview (the result of an agent task), in this session |
| `review <task> --verdict pass\|changes` | Record a self-review, only where the akasha-reviewer agent does not exist (not in Claude Code) |
| `check <task> [--only <checks>]` | Run the checks of the team. When each passes, save the work and push it. With `--only`, run only those checks and save nothing: run `check <task>` before `land`. When the change touches a file of `[preview] data`, the check `data` fails while the preview defines no value |
| `land <task> [--wait <seconds>]` | Make the pull request ready and merge it when the checks pass, then follow the deployment of `[deploy]` and run its `verify`. Exit code 3: still waiting (WAITING, DEPLOYING). Exit code 4: an agent task waits for the approval of its result (ASK) |
| `result <task>` | An agent task, after the landing said ASK: the text for the person (the summary, the change between two fixed commits, the changed files). Only a message of this session after it approves the result |
| `status [<task>]` | The tasks on this computer, the records folder, the plan digest (the change digest of a quick task), and the next step |
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
