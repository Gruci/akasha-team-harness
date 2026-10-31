# Coordination

Many people can use Akasha in one repository at the same time. The coordinator keeps their tasks apart, and nobody waits for another person.

## The principle

Each person talks only to their own agent engine. The agent engines align through shared state: the git branches, the shared task board, and the product map. The board holds the state of the tasks and the notices. It is not a channel for questions between people.

## The shared task board

Each task has one GitHub issue with the label `akasha`. The title of the issue is `[akasha] <task title>`.

The issue holds the state of the task, so that each computer can continue the task. The top of the issue body is for people: the requester, the holder, the stage, the status, the risk level, the revision of the specification, the numbered completion conditions with their inspection results, the approvals that Akasha counted, and the decision comments to copy. Below it, a JSON block with the name `akasha-scope` holds each field of the task. The agent engine on each computer reads these blocks. Each block contains:

- the task name, the requester, the workflow, the stage, and the status,
- the feature key, the scope, the contracts, and the risk level,
- the completion conditions, the open questions, the inspection results, and the approvals,
- the impact analysis, the briefing, the checks, the count of failed repairs, and the notes,
- the earlier task, the branch, the base commit, and the pull request,
- the holder, the revision, the commit of the last handoff, and the format,
- the revision of the specification, and the comments of the last stop and of the last `/resume`.

| Field | Meaning |
|:--|:--|
| `holder`, `holder_host` | The GitHub name of the person who holds the task, and the mark of the copy of the repository where that person works. Each copy of the repository has a random mark in `.akasha/state/machine.json` |
| `revision` | Goes up by one at each write. Akasha uses it to find the newer state |
| `wip` | The commit that the last handoff pushed |
| `format` | The shape of the block. Akasha writes `2` |
| `spec_rev` | The revision of the specification. It goes up when the completion conditions or the open questions change. Each decision comment names it |
| `stopped_comment`, `resumed` | The number of the comment of Akasha that stopped the task, and of the last `/resume` that opened it again. Only a later `/resume` counts |

The approvals and the inspection results in the body only show what Akasha counted. They are not proof of a decision: each time that Akasha reads a task, it counts them again from the decision comments on the issue. See [Roles](roles.md).

Five fields stay on the computer and never go on the issue: the work copy folder, the revision of the issue that this computer saw last, the output of a setup command that failed, the preview port of the task on this computer, and a mark that `preview` prepared the preview of the task on this computer. The output of a setup command can show paths and secret values. The issue only tells that the setup command failed. `show <task>` on the computer of the work copy shows the output.

| Event | What occurs to the issue |
|:--|:--|
| A task starts | Akasha makes the issue |
| A task changes | Akasha updates the issue |
| The pull request merges | The pull request closes the issue |
| A task is cancelled | Akasha closes the open pull request of the task, then the issue |

Each command reads the task from its issue, and takes only these five fields from the task file on this computer. When the issue tells that another person or another copy of the repository holds the task now, or another status, Akasha saves that in the task file here too. Thus the notices of the hooks on this computer stop. Before a write, Akasha reads the issue again. If another computer or another command wrote the issue after this command read it, the command stops and does not write over the newer state. Do the step again. A comment does not change the revision, so a comment never stops a command.

When the task file on this computer has changes that the issue did not get, and nobody wrote the issue since, the next command for the task puts them on the issue. But such a task file does not change the result of a decision of a person, and it does not move the task past a gate, because the agent engine can edit it. The requester, the holder, and the workflow stay. The stage does not go past the stage on the issue, so the next `advance` examines the gates again. The risk level and the count of failed repairs do not go down. A stopped task stays stopped until a `/resume` counts, and the status of the issue stays. See [Roles](roles.md). A task can have no issue, because this computer recorded it before `origin` was on GitHub, or because its first board write failed: the next command for it puts it on the board, and the person on this computer holds it.

Each task name is unique in the repository. The name has the letters a to z and the digits of the title in lower case, and eight random characters, for example `add-a-date-filter-1f3a9c0b`. A title without these letters and digits, for example a Korean title, gives `task-<random characters>`. Before a task starts, Akasha makes sure that no task file, no branch on this computer or on the server, and no issue on the board has the same name.

When `origin` is a GitHub repository, the board must work. If `gh` cannot read or write the board, the command stops and tells you to examine `gh auth status`. Thus nobody works on a task that the other people cannot see. This also applies to the comments that Akasha writes on the issues.

If a write fails after Akasha saved the change on this computer, the message names the task. When `gh` works again, run `specify <task>`, or the next command for the task. It puts the saved task on the board. Do not record the task again, because that makes a second task.

For a new task at the build stage, Akasha finds the start commit of the work copy before it records the task. If the branch of the earlier task is not there yet, the request stops, and Akasha records nothing. If Akasha recorded the task but cannot make its work copy, the message names the task. When the cause is repaired, run `advance <task>`. It makes the work copy.

With GitHub, the board shows the open issues, and the active tasks on this computer that have no issue yet. A task file of a task that has a closed issue is old, for example after this computer handed off the task and another computer finished it. That task file does not go on the board, and the overlap checks do not use it.

Before a request, Akasha finishes the tasks that this person holds on this computer and whose pull request merged. If Akasha cannot update the issue of such a task, for example because a person deleted the issue, the request continues. The request itself reads and writes the board.

The hooks of the agent engine read the open tasks from a copy of the board in `.akasha/state/board.json`. The copy is at most five minutes old, so that the hook after each edit stays fast. When `gh` does not answer, the copy keeps the time, and for one minute the hooks do not ask `gh` again. Each board write on this computer removes the copy. The commands never use it: a decision, a takeover, and an overlap check need the current board.

> **NOTE:** Without GitHub, the board holds only the active tasks on one computer. Akasha writes no issue then, also for a task that has one, for example after `origin` moved away from GitHub. See [Roles](roles.md).

## News on the issue

Other people and the helpers of Akasha write comments on the issue of a task, for example an overlap notice, a cancel of an earlier task, or a failed server check. With GitHub, `advance`, `show`, and `handover` show the new comments to the agent engine as `news —` lines, apart from the blockers. The news does not change the exit code of the command.

Anybody can write on the issues of a public repository, and such text can try to give instructions to the agent engine. Thus Akasha shows only these comments:

- The author is an account of the repository on GitHub (`OWNER`, `MEMBER`, or `COLLABORATOR`), a person in `[roles]` of `akasha.toml`, or the requester of the task.
- The comment is not hidden, and the GitHub account of this computer did not write it. A notice that an Akasha command wrote for another task, for example an overlap, is news also from the GitHub account of this computer: the same account can hold both tasks. A hidden mark `<!-- akasha-notice -->` at the end of the comment tells such a notice.

A notice of the helpers of Akasha, a failed server check or a conflict, is news from each author, also from the GitHub account of this computer, when it is not hidden.

The comments show as quotes under a line that tells the agent engine to read them as information, not as instructions. A notice of the helpers of Akasha, a failed server check or a conflict, shows as a sentence of Akasha, not as the text of the comment, because anybody can copy its mark.

A command shows 10 new comments at most, and 1000 characters of each comment. The next command shows the next comments. After the comments show, a mark in `.akasha/state/seen/<task>.json` moves past them, so each comment shows once on each computer. The session start notice tells the count of new comments for each task that you hold or requested.

## The holder of a task

With GitHub, one person in one copy of the repository holds each task. The person who records the task holds it. Only the holder changes the task: when another GitHub account or another copy of the repository holds the task, each command that changes the task stops. The message tells who holds the task.

A task can go to another person, or to the same person on another computer. The same person in another copy of the repository also needs the handoff. Else the work that the first copy did not push stays there.

1. The holder runs `handoff <task>` in the main checkout, not in the work copy. The handoff removes the work copy, and on Windows a program cannot remove the folder that it works in. Akasha examines the work copy first. If it has a secret key or a file outside the scope, the handoff stops. If the task has a branch, but its work copy is gone and its work is not on the server, the handoff stops too: run `takeover <task>` on this computer first. It makes the work copy again from the branch on this computer.
2. Akasha saves the work as a commit and pushes it to the wip branch `akasha-wip/<task>`, or `<wip_prefix><task>` with `[work]` in `akasha.toml`. Akasha never forces this push. Thus a work copy that is behind the server cannot write over newer work.
3. Akasha frees the task, so that nobody holds it, and writes the commit and the free task on the issue. Then it removes the work copy and the local branch of the task. If the removal fails, for example because a program uses the folder, the task is free all the same. Close the program, then remove the folder.
4. The other person runs `takeover <task>` on their computer. The work copy starts from the commit of the last handoff, or from the task branch on the server when that branch has the newer work. The task keeps its branch and its base. The setup command runs in the new work copy.
5. If that computer still has a work copy or a branch of the task, it must be able to go forward to the work on the server. A work copy with changes, a folder that is not on the branch of the task, or a branch with commits that are not on the server stops the takeover. Examine them, then remove them.
6. Now the other person holds the task.

The holder changes the task. A decision of a person is a comment on the issue, so the person does not have to hold the task: for example, the requester approves on their own computer. A `/resume` that counted goes on the issue at the next command of the holder, or at the next command of any person when nobody holds the task. A `/cancel` that counted goes on the issue at the next Akasha command for the task on any computer, also the `cancel` command itself. Thus no other computer compares a new task with a cancelled task.

A cancel stops the open pull request of the task: Akasha turns off its auto-merge, removes the label `akasha-merge`, and closes it. Thus the cancelled change does not merge.

- Before the cancel goes on the issue, the command that writes it does these steps with the GitHub account of its computer, also a command that counts a `/cancel` late. It also deletes the wip branch, and writes a notice with an `@` mention of the requester on the issue of each active task that builds on the cancelled task.
- The `cancel` command does this at once, also when another person holds the task. If the account cannot close the pull request, the command tells it, and the cancel does not go on the issue yet. Then close the pull request on GitHub, and do the step again.
- A `/cancel` that a person writes on GitHub counts at the next Akasha command for the task. Until then, GitHub can merge the pull request. Thus a person who cancels on GitHub also closes the pull request there, or uses the `cancel` command.

The work copy stays.

A developer can take over a stopped task when its holder did not hand it off, also after a developer wrote `/resume`. Then the takeover writes the `/resume` on the issue, and the task is open. `[roles] developers` names the developers. When the list is empty, each person can do it. Akasha writes a notice with an `@` mention on the issue of the task for the old holder. When a check stops the task, Akasha saves the work on the wip branch, as a handoff does. A work copy with a secret key or a file outside the scope stays only on the computer of the holder: then the work copy of the developer starts without that work.

When the copy of the holder is gone, nobody can hand off an open task: for example after a new clone, a broken computer, or `git clean -xdf`, which removes `.akasha/state/` with the mark of the copy. Then run `takeover <task> --force`. The same GitHub account in another copy can do it, and a developer can do it. The work copy starts from the work on the server: the work that the old copy did not push is not in the task. Akasha writes a notice with an `@` mention on the issue for the old holder.

When the handover pushes a task branch that has the commit of the last handoff, Akasha deletes the wip branch on the server. A cancel also deletes it.

A takeover never starts without the commit of the last handoff. When no wip branch has it, for example after the team changed `wip_prefix` two times, Akasha fetches the commit by its name. When the server does not have it, the takeover stops: push the commit to the wip branch from a computer that has it, then do the takeover again. When the server has no work of the task at all, because no check passed and nobody handed it off, the work copy starts from the branch of the task on this computer, else from the base of the task.

The handoff pushes to the wip branch, not to the task branch. The task branch on the server always passed the checks, and later tasks build on it.

If another person took over a task while this computer still has its work copy, each command for the task on this computer stops and tells you to examine the work copy, save what you need, and remove it.

> **NOTE:** Without GitHub, nobody holds a task, and the handoff and the takeover are not available.

## Overlap checks

The coordinator compares a task with each active task on the board. A task is active when it is open or stopped. The coordinator does this check when a task starts, when the scope of a task gets wider, and when its feature key changes. A new task goes on the board before the check. Thus two tasks that start at the same time find each other. After a change of the scope or of the feature key, Akasha compares only what changed: the new file patterns, their new contracts, and the new feature key. When `advance` finds that the real changes touch a public contract that the task did not have, Akasha compares only the new contracts again. Thus Akasha does not tell the same overlap two times.

| Overlap | Test | Action |
|:--|:--|:--|
| Same feature | The two tasks have the same feature key | Build the new task on the earlier task |
| Same files | The scopes of the two tasks can match the same file | Both tasks continue. Akasha does not set the sequence: the task that merges later gets the earlier change at its handover, or when the helpers bring its pull request up to date. If the changes conflict, Akasha tells that task |
| Same contract | The two tasks change the same public contract | Akasha tells the requester of the other task |

For each overlap, Akasha shows the overlap to the agent engine of the task. It also writes the overlap on the issue of the other task with an `@` mention of its requester, and GitHub tells the people who follow that issue. A command that changes the task writes these comments after its board write: when the board write fails, the next command finds the same overlaps again. The agent engine of the other task sees the comment as news, also when the same GitHub account holds both tasks.

The file test is careful. Two patterns touch when the part before the first wildcard of one pattern starts with the same part of the other pattern. For example, `src/search/**` and `src/search/date.py` touch. `src/search/**` and `src/billing/**` do not touch.

### During the work

After each edit in the work copy of a task that this copy of the repository holds, the hook compares the file with the scopes of the other open tasks. The path is relative to the top of the work copy, as in a scope. These do not count:

- the task itself, the task that it builds on, and the tasks that build on it,
- the files in the team context and in the map folder, because they are outside each scope,
- the files outside the work copies.

The agent engine gets the notice once for each pair of tasks, until the scope of the other task changes. `.akasha/state/seen.json` keeps the notices that the agent engine got. The notice does not stop the edit. With GitHub, the other tasks come from the copy of the board of the hooks. When `gh` does not answer, the hook gives no notice, and the next hooks do not wait for `gh` for one minute. Without GitHub, the hook compares the file with the other tasks on this computer.

## Stack tasks of one feature

When two people want the same feature, the second task builds on the first task. Nobody waits for an answer.

1. The second task starts with `request --builds-on <earlier task>`. Its work copy starts from the branch of the earlier task on the server. Akasha reads the name of that branch from the task, also when another computer made it. Only when the server does not have the branch, the work copy starts from the branch on this computer, for example in a repository without a server.
2. Akasha pushes the branch of each task when each of its checks passes or is NOT_NEEDED. Thus the branch on the server always passed the checks. The server can have newer commits on the branch, for example a merge of the default branch that GitHub made in the pull request. Then the server refuses the push, and Akasha merges these commits into the work copy. When the merge changed files, Akasha runs the checks again on the merged work, and pushes it only when each check passes or is NOT_NEEDED again. A conflict stops the check: the message tells how to repair it. When the push fails again, the check tells the answer of the server, and a note on the task tells that the branch on the server is older. The answer of the server stays on this computer, because it can show paths and secrets, for example from a pre-push hook. The next push that works removes the note. Without a server, nothing goes out. The handover merges the task branch from the server before the latest default branch, so that its check runs on all of the work.
3. The agent engine writes a test for each completion condition. Thus the checks of the later task keep the behavior that the earlier requester accepted.
4. The later task hands over only after the earlier task merged. Else its pull request would carry changes that the earlier requester did not accept. If the earlier task is cancelled, the handover stops and tells it. Then run `specify <task> --builds-on ""`. The base of the task goes back to the default branch, and the changes of the earlier task in the work copy become changes of the later task. Remove the changes that the later task does not need.
5. A large feature gets the feature keys `<feature>/<part>`. A part that needs another part builds on it. Each key has its own map file, so the parts do not change the same file of the product map.

## When a later request changes accepted behavior

1. The agent engine asks only the person who is present: keep both, or replace?
2. If the person selects to replace, the agent engine records it with `impact --changes-task`. Akasha writes a notice with an `@` mention on the issue of the earlier task.
3. GitHub tells the earlier requester. That person reacts with a new request when necessary.

## Work copies

Each task builds in its own work copy: a git worktree in `.akasha/work/<task>`, on the task branch `akasha/<task>`. `[work]` in `akasha.toml` can give another folder and other prefixes, for a repository that already uses these names ([Team config](team-config.md)).

- Each task keeps its branch, also after a takeover on another computer or a change of `[work]`. Thus its pull request and its branch on the server stay the same. A work copy of the task that this computer still has stays in its folder.
- Git does not track the work copies. When no ignore file names the work folder, Akasha adds it to `.git/info/exclude` at the first work copy on each computer. Akasha stops when git tracks files in the work folder: git ignores the folder, also in each work copy, so the new files of a task there would not go into the task.
- A work copy starts from the latest default branch on the server, or from the branch of the earlier task. Akasha asks the server for the name of its default branch: GitHub tells it, else git asks the server. Thus a clone from before the team renamed the default branch starts from the correct branch.
- While a task builds, Akasha stops edits in the main checkout.
- Two tasks never write in the same folder.
- When the pull request merges, Akasha removes the work copy. First the cleanup command of `[preview]` removes the preview database of the task, and then the preview port is free. See [Preview resources](#preview-resources).
- When a task is cancelled, the work copy, the preview database, and the preview port stay. A person removes the work copy after a review of the changes.
- After a handoff, the work copy and the local branch of the task go away, and the preview port is free. The preview database stays. A takeover makes a new work copy from the work on the server. When this computer takes the task over again and finishes it, the cleanup command removes the database. When another computer finishes the task, the database stays on this computer: remove it yourself.
- When the work copy of a task is gone, `check` tells how to make it again. With GitHub, `takeover <task>` on this computer makes it from the work on the server, else from the branch on this computer. Without GitHub, git makes it from the branch: `git worktree prune`, then `git worktree add <work copy> <branch>`.
- A folder that is not on the branch of the task is not its work copy, for example an empty folder after a failed removal. In such a folder, git works on the main checkout. Thus `check`, `handover`, and `handoff` stop there and do not save or push the changes of the main checkout.
- The guard, the overlap notice after an edit, and the notice at the end of each turn look only at the work copies on this computer.

## The main checkout

The agent engine writes the specification and the impact analysis before the work copy exists. Thus it reads the product map, the team context, and the code in the main checkout. Git does not update that checkout by itself, so it can be older than the work that other people merged.

At each request, Akasha fetches the default branch. When the main checkout is on the default branch and has no changes, Akasha brings it forward to the latest commit (`git merge --ff-only`). Else the request tells how many commits the checkout is behind. Then the agent engine reads the latest files from the server:

- `git show origin/<default branch>:<path>` shows one file.
- `git grep <text> origin/<default branch>` searches all files.

## Preview resources

Two previews must not use the same database or the same port. The coordinator gives each task its own values.

| Placeholder | Value |
|:--|:--|
| `{task}` | The task name. Each character that is not a letter, a digit, or `_` changes to `_` |
| `{port}` | The preview port of the task on this computer, from 4100 to 4899 |

Write the placeholders in `[preview]` of `akasha.toml` ([Team config](team-config.md)).

The agent engine starts the preview at the inspection. Before it starts the preview, it runs `preview <task>`:

1. Akasha reserves the port of the task. A task keeps its port. A new port starts at a port that the task name gives, and Akasha goes through the range from there. It skips each port that another task of the same person on this computer reserved, also in another copy of the repository. It also skips each port that a program uses now: Akasha cannot bind the port on `127.0.0.1` or `0.0.0.0`, or a program answers on `127.0.0.1` or `::1`.
2. Akasha runs the seed command of `[preview]` in the work copy, with the placeholders filled. The seed command makes the database of the task and puts sample data in it.
3. Akasha shows the port and the filled values of `[preview]`. The agent engine starts the preview with the preview command in the work copy.

The reservations come first, because a preview runs only at the inspection: a port that no program uses now can be the port of another task. They are in `~/.akasha/ports.json` in the home folder of the person, for each copy of a repository and each task, with a lock file. A reservation that nothing needs any more goes away at the next reservation: the copy of the repository is gone, or the task has no work copy on this computer.

The port, the database, and the output of the seed command stay on this computer. The issue never holds them. When the seed command fails, `preview` shows its output and stops with the exit code 1. The server check never runs the seed command.

| Event | The preview database | The preview port |
|:--|:--|:--|
| The pull request merges, and Akasha removes the work copy | The cleanup command of `[preview]` removes it in the work copy first | Free |
| The task is cancelled | Stays, as the work copy does | Stays until the work copy goes away |
| A handoff | Stays. When this computer takes the task over again and finishes it, the cleanup command removes it | Free |

The cleanup command runs only for a task that `preview` prepared on this computer, also before a handoff. When the cleanup command uses `{port}` and a handoff freed the port, Akasha reserves a port for the task again. When the cleanup command fails, the work copy, the database, and the port stay, and the next request runs the cleanup command again. `request` and `advance` tell this with a `note —` line. To stop it, remove the database yourself, then remove the work copy with `git worktree remove <work copy>`.

> **NOTE:** The commands of `[preview]` run in the shell of the operating system, as the checks do: `cmd.exe` on Windows, and `/bin/sh` on macOS and Linux.
