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
| `review <task> --verdict pass\|changes` | Record a self-review, where no reviewer agent exists |
| `check <task> [--only <checks>]` | Run the checks of the team. When each passes, save the work and push it |
| `land <task> [--wait <seconds>]` | Make the pull request ready and merge it when the checks pass. Exit code 3: still waiting |
| `status [<task>]` | The tasks on this computer, the plan digest, and the next step |
| `board` | The open tasks of the team |
| `resume <task or #number> [--force]` | Continue a task of the board on this computer |
| `handoff <task>` | Save the work on the server and free the task |
| `cancel <task> [--force]` | Stop a task for good: close its pull request and remove the work copy |
| `help <task> "<text>"` | Ask the administrators on the pull request of the task |
| `tidy` | Remove the work copies of the tasks whose pull request merged or closed |
| `retro` | What stops the work again and again |
| `version` | The version of Akasha |

The workflows run `check --ci` (the check of Akasha) and `server watch` (the watch). The hooks run `hook --event`.
