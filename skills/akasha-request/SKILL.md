---
name: akasha-request
description: Do a change as an Akasha task, from the request to the checks. Use for each request to add, change, or repair a feature in a repository that has akasha.toml.
---

# Do a change as an Akasha task

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Who decides what

| Who | Decides |
|:--|:--|
| Requester | What to make, how it looks, and how people use it |
| You, the agent engine | The implementation, the scope, the impact, the data changes, and the order of the work between tasks |
| Administrator | The team rules |

Ask people only what to make, how it looks, and how they use it. Make the technical decisions yourself and record them with Akasha. Use the GitHub name of each person.

## Decisions of people

With GitHub, each decision of a person is a decision comment on the issue of the task, from the GitHub account of that person: `/approve spec r<N>`, `/approve risk <level>`, `/accept <number> r<N>`, `/reject <number> r<N> <reason>`, `/resume`, and `/cancel <reason>`. `akasha advance <task>` and `akasha show <task>` tell the exact comment and the issue.

- If the person who decides is the GitHub account of this computer, and the person gives you the decision, run the Akasha command in the step. Akasha writes the comment with that account.
- If the person is another account, the command stops and tells the comment. Give the person the comment and the issue address. Then wait. Run `akasha advance <task>` again later.
- Never write a decision comment with `gh`. Do not edit, delete, or hide a comment, and do not change the body of an issue. The guard stops these commands.
- If Akasha says that a decision comment does not count, tell the person the reason and the correct comment.
- If Akasha says that the requester is not a GitHub account, for example in a task of Akasha 1.0.0, ask the user for the GitHub name of the requester. Then run `akasha specify <task> --requester <GitHub name>`.

Without GitHub, add `--by <name>` to `approve`, `resume`, and `cancel`.

If the requester withdraws the request, run `akasha cancel <task> --reason "<reason>"`. If the requester is another account, the requester writes `/cancel <reason>` on the issue. Akasha closes the pull request of the task. If Akasha says that it cannot close the pull request, tell the user to close it on GitHub.

## Stage 1 — Request

1. Select the workflow:
   - `feature` for a new feature or a changed feature.
   - `fix` for a defect.
   - `small` for a small change with clear completion conditions.
2. Run `akasha board`. If an active task makes the same feature, the new task builds on that task.
3. Record the task: `akasha request "<title>" --workflow <workflow> --feature <feature key>`.
   - With GitHub, the requester is the GitHub account of this computer. If another person asked for the change, add `--requester <GitHub name>`. Without GitHub, always add `--requester <name>`. If Akasha says that the requester has no access to the repository, tell the user.
   - To build on an earlier task, add `--builds-on <earlier task>`.
   - For a part of a large feature, use the feature key `<feature>/<part>`.
4. If Akasha shows an overlap, do the action that Akasha shows.
5. Ask the requester questions until the completion conditions are clear. Ask what the person sees, what the person does, and which result the person expects.
6. Record each condition: `akasha specify <task> --condition "<condition>"`.
7. Record each question that has no answer: `akasha specify <task> --question "<question>"`. When all questions have answers, run `akasha specify <task> --clear-questions`.
8. Run `akasha advance <task>`.

> **NOTE:** The `fix` and `small` workflows have no specification stage. For these workflows, do steps 1 to 3 of stage 2 before you advance from the build stage.

> **NOTE:** If Akasha says that it cannot read or write the shared task board, do not continue without the board. Ask the user to log in with `gh auth login`. If Akasha also says that it saved or recorded the task, continue with that task. When `gh` works again, run the command that Akasha shows. Do not record the task again, because that makes a second task. Else do the step again.

> **NOTE:** If Akasha says that it recorded the task but cannot make its work copy, continue with that task. Do not record the task again, because that makes a second task. Repair the cause that Akasha shows, then run `akasha advance <task>`. It makes the work copy.

> **NOTE:** If Akasha says that another person or another computer holds the task, do not change the task. Tell the user who holds it. If Akasha says that another command changed the task, do the step again.

## Stage 2 — Specification and impact

1. Read the product map and the team context files that the session start notice shows. If the request said that the main checkout is behind the default branch, the files of the main checkout are old. Read the latest files from the server: `git show origin/<default branch>:<path>`. Search them with `git grep <text> origin/<default branch>`.
2. Find the files, the data, and the APIs that the change touches. Use the latest files, as in step 1. Record the scope: `akasha specify <task> --scope <file patterns>`.
3. Do the impact analysis. Record it: `akasha impact <task> --features "<text>" --data "<text>" --contracts "<text>" --tasks "<text>" --rollback "<text>"`.
   - `features`: the features that use the code that you change. Search for each caller.
   - `data`: each table, column, or file that changes, each reader and writer of it, and the order of the migration. Write "No data change" when there is none.
   - `contracts`: each API or function that other features or teams use, and its users.
   - `tasks`: each active task that touches the same feature, files, or contracts, and how the tasks combine.
   - `rollback`: how to reverse the change. A revert of the code does not restore data. For a data change, tell how to reverse the data.
4. Tell the requester the specification in simple words: what changes, what the person will see, and what does not change. Do not explain the technical details.
5. Ask the requester to approve it. If the requester is the GitHub account of this computer and approves, run `akasha approve <task> --role requester`. Else the requester writes `/approve spec r<N>` on the issue: Akasha tells the exact comment.
6. Run `akasha advance <task>`. If Akasha says that a person with a gate role must approve, ask that person. That person writes `/approve risk <level>` on the issue, or runs `akasha approve <task> --role <role>` on their own computer.

> **CAUTION:** Never record an approval for a person who did not give it.

> **NOTE:** When the completion conditions or the open questions change, the specification gets a new revision. The requester approves it again, and the task goes back to the specification stage.

## When the request changes the work of an earlier requester

An earlier requester accepted some behavior, and the tests of that task keep it. Keep that behavior when you can.

1. If the request changes behavior that an earlier requester accepted, ask your requester: keep both, or replace?
2. If your requester selects to replace, record it: `akasha impact <task> --changes-task <earlier task> "<what changes>"`. Akasha tells the earlier requester on GitHub. Do not wait for an answer.

## When another person continues the task

With GitHub, one person on one computer holds each task. Only the holder changes it.

To stop the work so that another person, or the same person on another computer, continues it:

1. Make sure that the work copy has no secret key and no file outside the scope.
2. Run `akasha handoff <task>` in the main checkout, not in the work copy. Akasha saves the work on the server and frees the task. The work copy goes away.
3. If Akasha says that it handed off the task but cannot remove the work copy, tell the user to close the programs that use the folder, then remove it.
4. Tell the user that the task is free, and give the task name.

To continue the task of another person:

1. Run `akasha board`. Find the task and its holder. If a person holds the task, ask that person to hand it off. If you hold it in another copy of the repository, hand it off there first. Do not continue before the handoff.
2. Run `akasha takeover <task>`. Akasha makes the work copy from the work on the server, and you hold the task.
3. If Akasha says that a work copy or a branch on this computer cannot go forward to the work on the server, tell the user. The user examines it and removes it. Then do step 2 again.
4. Run `akasha show <task>`. Continue at the stage that Akasha shows.

> **NOTE:** A developer can take over a stopped task without a handoff, also after the developer wrote `/resume`. Akasha tells the old holder on the issue.

## Stage 3 — Build

1. Make the change only in the work copy that Akasha shows.
2. Change only the files in the scope. If the change needs more files, record them with `akasha specify <task> --scope <file patterns>`.
3. Write an automated test for each completion condition. Then later tasks keep the behavior that the requester accepted.
4. Run `akasha advance <task>`.

## Stage 4 — Checks and repair

1. Run `akasha check <task>`. When all checks pass, Akasha saves the work and pushes the task branch.
   - If Akasha says that the task branch on the server has commits that conflict with the work copy, do the steps in the message. Then run the check again.
   - If Akasha says that it could not update the task branch on the server, tell the user the reason. Run the check again later.
2. Repair each failure. Then run the check again.
3. If Akasha stops the task after three failed repairs, stop the work. Tell the requester in simple words that a developer must examine the problem.
4. With GitHub, the developer writes `/resume` on the issue of the task. If the developer is the GitHub account of this computer and tells you to continue, run `akasha resume <task>`. Then run `akasha advance <task>`.
5. Update `.akasha/context/product-map.md` in the work copy for each feature, screen, table, or API that the change adds or changes. If nothing changes, record why: `akasha impact <task> --map-unchanged "<reason>"`.
6. When all checks pass, run `akasha advance <task>`.
7. Continue with the akasha-inspect skill. For the `small` workflow, continue with the akasha-handover skill.

> **NOTE:** Do not show the raw output of a check to the requester. Tell the result in simple words.
