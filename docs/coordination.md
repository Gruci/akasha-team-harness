# Coordination

Many people can use Akasha in one repository at the same time. The coordinator keeps their tasks apart, and nobody waits for another person.

## The principle

Each person talks only to their own agent engine. The agent engines align through shared state: the git branches, the shared task board, and the product map. The board holds the state of the tasks and the notices. It is not a channel for questions between people.

## The shared task board

Each task has one GitHub issue with the label `akasha`. The title of the issue is `[akasha] <task title>`.

The issue body holds a JSON block with the name `akasha-scope`. The agent engine on each computer reads these blocks. Each block contains:

- the task name, the requester, the workflow, the stage, and the status,
- the feature key, the scope, the contracts, and the risk level,
- the completion conditions and the inspection results,
- the earlier task and the pull request.

| Event | What occurs to the issue |
|:--|:--|
| A task starts | Akasha makes the issue |
| A task changes | Akasha updates the issue |
| The pull request merges | The pull request closes the issue |
| A task is cancelled | Akasha closes the issue |

> **NOTE:** Without GitHub, the board holds only the active tasks on one computer.

## Overlap checks

The coordinator compares a task with each active task on the board. A task is active when it is open or stopped. The coordinator does this check when a task starts and when the scope of a task gets wider.

| Overlap | Test | Action |
|:--|:--|:--|
| Same feature | The two tasks have the same feature key | Build the new task on the earlier task |
| Same files | The scopes of the two tasks can match the same file | The earlier task merges first |
| Same contract | The two tasks change the same public contract | Akasha tells the requester of the other task |

For each overlap, Akasha shows the overlap to the agent engine of the new task. It also writes the overlap on the issue of the other task, and GitHub tells the people who follow that issue.

The file test is careful. Two patterns touch when the part before the first wildcard of one pattern starts with the same part of the other pattern. For example, `src/search/**` and `src/search/date.py` touch. `src/search/**` and `src/billing/**` do not touch.

## Stack tasks of one feature

When two people want the same feature, the second task builds on the first task. Nobody waits for an answer.

1. The second task starts with `request --builds-on <earlier task>`. Its work copy starts from the branch of the earlier task.
2. Akasha pushes the branch of each task when all its checks pass. Thus the branch on the server always passed the checks.
3. The agent engine writes a test for each completion condition. Thus the checks of the later task keep the behavior that the earlier requester accepted.
4. The later task hands over only after the earlier task merged. Else its pull request would carry changes that the earlier requester did not accept.
5. A large feature gets the feature keys `<feature>/<part>`. A part that needs another part builds on it.

## When a later request changes accepted behavior

1. The agent engine asks only the person who is present: keep both, or replace?
2. If the person selects to replace, the agent engine records it with `impact --changes-task`. Akasha writes a notice with an `@` mention on the issue of the earlier task.
3. GitHub tells the earlier requester. That person reacts with a new request when necessary.

## Work copies

Each task builds in its own work copy: a git worktree in `.akasha/work/<task>`, on the branch `akasha/<task>`.

- A work copy starts from the latest default branch on the server, or from the branch of the earlier task.
- While a task builds, Akasha stops edits in the main checkout.
- Two tasks never write in the same folder.
- When the pull request merges, Akasha removes the work copy.
- When a task is cancelled, the work copy stays. A person removes it after a review of the changes.

## Preview resources

Two previews must not use the same database or the same port. The coordinator gives each task its own values.

| Placeholder | Value |
|:--|:--|
| `{task}` | The task name. Each character that is not a letter, a digit, or `_` changes to `_` |
| `{port}` | A port from 4100 to 4899. The same task always gets the same port |

Write the placeholders in `[preview]` of `akasha.toml`.

> **NOTE:** The port comes from the task name. Two tasks can get the same port, but the probability is low.
