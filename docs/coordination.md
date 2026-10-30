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
| `format` | `2`. An issue without a format is from Akasha 1.0.0 |
| `spec_rev` | The revision of the specification. It goes up when the completion conditions or the open questions change. Each decision comment names it |
| `stopped_comment`, `resumed` | The number of the comment of Akasha that stopped the task, and of the last `/resume` that opened it again. Only a later `/resume` counts |

The approvals and the inspection results in the body only show what Akasha counted. They are not proof of a decision: each time that Akasha reads a task, it counts them again from the decision comments on the issue. See [Roles](roles.md).

Three fields stay on the computer and never go on the issue: the work copy folder, the revision of the issue that this computer saw last, and the output of a setup command that failed. The output of a setup command can show paths and secret values. The issue only tells that the setup command failed. `show <task>` on the computer of the work copy shows the output. Akasha 1.0.0 wrote this output in a note. Before such a task goes on its issue in the new format, the output moves from the note to this computer. A setup command that passes later removes the old output.

| Event | What occurs to the issue |
|:--|:--|
| A task starts | Akasha makes the issue |
| A task changes | Akasha updates the issue |
| The pull request merges | The pull request closes the issue |
| A task is cancelled | Akasha closes the open pull request of the task, then the issue |

Each command reads the task from its issue, and takes only these three fields from the task file on this computer. Before a write, Akasha reads the issue again. If another computer or another command wrote the issue after this command read it, the command stops and does not write over the newer state. Do the step again. A comment does not change the revision, so a comment never stops a command.

When the task file on this computer has changes that the issue did not get, and nobody wrote the issue since, the next command for the task puts them on the issue. But such a task file does not change the result of a decision of a person: the requester stays, a stopped task stays stopped until a `/resume` counts, and a done or a cancelled task stays so. See [Roles](roles.md). When the computer with the task file of an Akasha 1.0.0 task runs a command for it, Akasha writes the issue in the new format, and the person on that computer holds the task. Until then, nobody can take over that task on another computer. The same applies to a task that has no issue, because this computer recorded it before `origin` was on GitHub, or because its first board write failed: the next command for it puts it on the board, and the person on this computer holds it. If an issue body has no format after this computer wrote the new format, for example because Akasha 1.0.0 still runs in one agent engine, the next command of the holder writes the whole task over it.

Each task name is unique in the repository. The name has the letters a to z and the digits of the title in lower case, and eight random characters, for example `add-a-date-filter-1f3a9c0b`. A title without these letters and digits, for example a Korean title, gives `task-<random characters>`. Before a task starts, Akasha makes sure that no task file, no branch on this computer or on the server, and no issue on the board has the same name.

When `origin` is a GitHub repository, the board must work. If `gh` cannot read or write the board, the command stops and tells you to examine `gh auth status`. Thus nobody works on a task that the other people cannot see. This also applies to the comments that Akasha writes on the issues.

If a write fails after Akasha saved the change on this computer, the message names the task. When `gh` works again, run `specify <task>`, or the next command for the task. It puts the saved task on the board. Do not record the task again, because that makes a second task.

For a new task at the build stage, Akasha finds the start commit of the work copy before it records the task. If the branch of the earlier task is not there yet, the request stops, and Akasha records nothing. If Akasha recorded the task but cannot make its work copy, the message names the task. When the cause is repaired, run `advance <task>`. It makes the work copy.

With GitHub, the board shows the open issues, and the active tasks on this computer that have no issue yet. A task file of a task that has a closed issue is old, for example after this computer handed off the task and another computer finished it. That task file does not go on the board, and the overlap checks do not use it.

Before a request, Akasha finishes the tasks that this person holds on this computer and whose pull request merged. If Akasha cannot update the issue of such a task, for example because a person deleted the issue, the request continues. The request itself reads and writes the board.

> **NOTE:** Without GitHub, the board holds only the active tasks on one computer.

## The holder of a task

With GitHub, one person in one copy of the repository holds each task. The person who records the task holds it. Only the holder changes the task: when another GitHub account or another copy of the repository holds the task, each command that changes the task stops. The message tells who holds the task.

A task can go to another person, or to the same person on another computer. The same person in another copy of the repository also needs the handoff. Else the work that the first copy did not push stays there.

1. The holder runs `handoff <task>` in the main checkout, not in the work copy. The handoff removes the work copy, and on Windows a program cannot remove the folder that it works in. Akasha examines the work copy first. If it has a secret key or a file outside the scope, the handoff stops.
2. Akasha saves the work as a commit and pushes it to the wip branch `akasha-wip/<task>`. Akasha never forces this push. Thus a work copy that is behind the server cannot write over newer work.
3. Akasha frees the task, so that nobody holds it, and writes the commit and the free task on the issue. Then it removes the work copy and the local branch of the task. If the removal fails, for example because a program uses the folder, the task is free all the same. Close the program, then remove the folder.
4. The other person runs `takeover <task>` on their computer. The work copy starts from the commit of the last handoff, or from the task branch on the server when that branch has the newer work. The task keeps its branch and its base. The setup command runs in the new work copy.
5. If that computer still has a work copy or a branch of the task, it must be able to go forward to the work on the server. A work copy with changes, a folder that is not on the branch of the task, or a branch with commits that are not on the server stops the takeover. Examine them, then remove them.
6. Now the other person holds the task.

The holder changes the task. A decision of a person is a comment on the issue, so the person does not have to hold the task: for example, the requester approves on their own computer. A `/resume` or a `/cancel` that counted goes on the issue at the next command of the holder, or at the next command of any person when nobody holds the task.

A cancel stops the open pull request of the task: Akasha turns off its auto-merge, removes the label `akasha-merge`, and closes it. Thus the cancelled change does not merge.

- The `cancel` command does this at once, also when another person holds the task. It uses the GitHub account of the person who cancels. If that account cannot close the pull request, the command tells it. Then close the pull request on GitHub.
- Before the cancel goes on the issue, the command that writes it does the same steps, also a command that counts a `/cancel` late. It also deletes the wip branch, and writes a notice with an `@` mention of the requester on the issue of each active task that builds on the cancelled task.
- A `/cancel` that a person writes on GitHub counts at the next command of the holder. Until then, GitHub can merge the pull request. Thus a person who cancels on GitHub also closes the pull request there, or uses the `cancel` command.

The work copy stays.

A developer can take over a stopped task when its holder did not hand it off, also after a developer wrote `/resume`. Then the takeover writes the `/resume` on the issue, and the task is open. `[roles] developers` names the developers. When the list is empty, each person can do it. Akasha writes a notice with an `@` mention on the issue of the task for the old holder.

When the handover pushes the task branch, Akasha deletes the wip branch on the server. A cancel also deletes it.

The handoff pushes to the wip branch, not to the task branch `akasha/<task>`. The task branch on the server always passed the checks, and later tasks build on it.

If another person took over a task while this computer still has its work copy, each command for the task on this computer stops and tells you to examine the work copy, save what you need, and remove it.

> **NOTE:** Without GitHub, nobody holds a task, and the handoff and the takeover are not available.

## Overlap checks

The coordinator compares a task with each active task on the board. A task is active when it is open or stopped. The coordinator does this check when a task starts and when the scope of a task gets wider. A new task goes on the board before the check. Thus two tasks that start at the same time find each other.

| Overlap | Test | Action |
|:--|:--|:--|
| Same feature | The two tasks have the same feature key | Build the new task on the earlier task |
| Same files | The scopes of the two tasks can match the same file | The earlier task merges first |
| Same contract | The two tasks change the same public contract | Akasha tells the requester of the other task |

For each overlap, Akasha shows the overlap to the agent engine of the new task. It also writes the overlap on the issue of the other task, and GitHub tells the people who follow that issue.

The file test is careful. Two patterns touch when the part before the first wildcard of one pattern starts with the same part of the other pattern. For example, `src/search/**` and `src/search/date.py` touch. `src/search/**` and `src/billing/**` do not touch.

## Stack tasks of one feature

When two people want the same feature, the second task builds on the first task. Nobody waits for an answer.

1. The second task starts with `request --builds-on <earlier task>`. Its work copy starts from the branch of the earlier task on the server. Akasha reads the name of that branch from the task, also when another computer made it. Only when the server does not have the branch, the work copy starts from the branch on this computer, for example in a repository without a server.
2. Akasha pushes the branch of each task when all its checks pass. Thus the branch on the server always passed the checks. The server can have newer commits on the branch, for example a merge of the default branch that GitHub made in the pull request. Then the server refuses the push, and Akasha merges these commits into the work copy. When the merge changed files, Akasha runs the checks again on the merged work, and pushes it only when they pass. A conflict stops the check: the message tells how to repair it. When the push fails again, the check tells the answer of the server, and a note on the task tells that the branch on the server is older. The answer of the server stays on this computer, because it can show paths and secrets, for example from a pre-push hook. The next push that works removes the note. Without a server, nothing goes out.
3. The agent engine writes a test for each completion condition. Thus the checks of the later task keep the behavior that the earlier requester accepted.
4. The later task hands over only after the earlier task merged. Else its pull request would carry changes that the earlier requester did not accept. If the earlier task is cancelled, the handover stops and tells it. Then run `specify <task> --builds-on ""`. The base of the task goes back to the default branch, and the changes of the earlier task in the work copy become changes of the later task. Remove the changes that the later task does not need.
5. A large feature gets the feature keys `<feature>/<part>`. A part that needs another part builds on it.

## When a later request changes accepted behavior

1. The agent engine asks only the person who is present: keep both, or replace?
2. If the person selects to replace, the agent engine records it with `impact --changes-task`. Akasha writes a notice with an `@` mention on the issue of the earlier task.
3. GitHub tells the earlier requester. That person reacts with a new request when necessary.

## Work copies

Each task builds in its own work copy: a git worktree in `.akasha/work/<task>`, on the branch `akasha/<task>`.

- A work copy starts from the latest default branch on the server, or from the branch of the earlier task. Akasha asks the server for the name of its default branch: GitHub tells it, else git asks the server. Thus a clone from before the team renamed the default branch starts from the correct branch.
- While a task builds, Akasha stops edits in the main checkout.
- Two tasks never write in the same folder.
- When the pull request merges, Akasha removes the work copy.
- When a task is cancelled, the work copy stays. A person removes it after a review of the changes.
- After a handoff, the work copy and the local branch of the task go away. A takeover makes a new work copy from the work on the server.
- A folder that is not on the branch of the task is not its work copy, for example an empty folder after a failed removal. In such a folder, git works on the main checkout. Thus `check`, `handover`, and `handoff` stop there and do not save or push the changes of the main checkout.
- The guard and the notice at the end of each turn look only at the work copies on this computer.

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
| `{port}` | A port from 4100 to 4899. The same task always gets the same port |

Write the placeholders in `[preview]` of `akasha.toml`.

> **NOTE:** The port comes from the task name. Two tasks can get the same port, but the probability is low.
