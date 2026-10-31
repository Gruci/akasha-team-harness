# Commands

The agent engine runs these commands. The session start notice gives the full command for the computer, for example
`"<python>" -X utf8 "<plugin>/akasha_run.py" <command>`. With the package installed, it is `python -m akasha <command>`
or `akasha <command>`.

| Command | Function |
|:--|:--|
| `setup` | Write the files of Akasha into the checkout. `--apply` also changes the GitHub settings (an administrator) |
| `doctor` | What this person needs to work in the repository, with the fix of each problem |
| `start "<title>" [--name <name>] [--scope <patterns>]` | Start a task: a work copy on a new branch, and a draft pull request on the board |
| `preview <task> [--text <text>] [--no-open]` | Show the preview to the person and wait for the approval |
| `approve <task>` | Record the approval from the last message of the person after the preview, in this session |
| `review <task> --verdict pass\|changes` | Record a self-review, only where no reviewer agent exists (not in Claude Code) |
| `check <task> [--only <checks>]` | Run the checks of the team. When each passes, save the work and push it. With `--only`, run only those checks and save nothing: run `check <task>` before `land` |
| `land <task> [--wait <seconds>]` | Make the pull request ready and merge it when the checks pass, then follow the deployment of `[deploy]`. Exit code 3: still waiting (WAITING, DEPLOYING) |
| `status [<task>]` | The tasks on this computer, the records folder, the plan digest, and the next step |
| `board` | The open tasks of the team |
| `resume <task or #number> [--force]` | Continue a task of the board on this computer. It runs `[checks] setup` in the new work copy |
| `handoff <task>` | Save the work on the server and free the task |
| `cancel <task> [--force]` | Stop a task for good: close its pull request and remove the work copy. When another person holds it, only remove the copy here |
| `help <task> "<text>"` | Ask the administrators on the pull request of the task |
| `ask "<text>"` | Ask the administrators a question that is not a change (data, the server), in an issue |
| `tidy` | Remove the work copies of the tasks whose pull request merged or closed, or that another person holds now |
| `retro` | What stops the work again and again |
| `version` | The version of Akasha |

The results of `land`: MERGED, DEPLOYED, and CLOSED end the task (exit code 0). WAITING and DEPLOYING ask for the same
command again (exit code 3). FAILED, CONFLICT, REVIEW, BLOCKED, and DEPLOY_FAILED tell what to do (exit code 1).

The workflows run `check --ci` (the check of Akasha) and `server watch` (the watch). The hooks run `hook --event`
through `hook.sh`, which finds Python 3.11 or higher. A shell line that is exactly one of these commands with the
launcher of the plugin runs without a permission prompt: `start`, `preview`, `approve`, `status`, `check`, `land`,
`board`, `help`, `ask`, `handoff`, `resume` (without `--force`), `tidy`, `doctor`, `version`, `retro`.
