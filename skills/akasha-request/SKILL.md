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

If the requester withdraws the request, run `akasha cancel <task> --by <requester>`.

## Stage 1 — Request

1. Select the workflow:
   - `feature` for a new feature or a changed feature.
   - `fix` for a defect.
   - `small` for a small change with clear completion conditions.
2. Run `akasha board`. If an active task makes the same feature, the new task builds on that task.
3. Record the task: `akasha request "<title>" --requester <name> --workflow <workflow> --feature <feature key>`.
   - To build on an earlier task, add `--builds-on <earlier task>`.
   - For a part of a large feature, use the feature key `<feature>/<part>`.
4. If Akasha shows an overlap, do the action that Akasha shows.
5. Ask the requester questions until the completion conditions are clear. Ask what the person sees, what the person does, and which result the person expects.
6. Record each condition: `akasha specify <task> --condition "<condition>"`.
7. Record each question that has no answer: `akasha specify <task> --question "<question>"`. When all questions have answers, run `akasha specify <task> --clear-questions`.
8. Run `akasha advance <task>`.

> **NOTE:** The `fix` and `small` workflows have no specification stage. For these workflows, do steps 1 to 3 of stage 2 before you advance from the build stage.

> **NOTE:** If Akasha says that it cannot read or write the shared task board, do not continue without the board. Ask the user to log in with `gh auth login`. Then do the step again.

## Stage 2 — Specification and impact

1. Read the product map and the team context files that the session start notice shows.
2. Find the files, the data, and the APIs that the change touches. Record the scope: `akasha specify <task> --scope <file patterns>`.
3. Do the impact analysis. Record it: `akasha impact <task> --features "<text>" --data "<text>" --contracts "<text>" --tasks "<text>" --rollback "<text>"`.
   - `features`: the features that use the code that you change. Search for each caller.
   - `data`: each table, column, or file that changes, each reader and writer of it, and the order of the migration. Write "No data change" when there is none.
   - `contracts`: each API or function that other features or teams use, and its users.
   - `tasks`: each active task that touches the same feature, files, or contracts, and how the tasks combine.
   - `rollback`: how to reverse the change. A revert of the code does not restore data. For a data change, tell how to reverse the data.
4. Tell the requester the specification in simple words: what changes, what the person will see, and what does not change. Do not explain the technical details.
5. Ask the requester to approve it. Record the approval: `akasha approve <task> --role requester --by <name>`.
6. Run `akasha advance <task>`. If Akasha says that a person with a gate role must approve, ask that person. Record the approval with `--role <role>`.

> **CAUTION:** Never record an approval for a person who did not give it.

## When the request changes the work of an earlier requester

An earlier requester accepted some behavior, and the tests of that task keep it. Keep that behavior when you can.

1. If the request changes behavior that an earlier requester accepted, ask your requester: keep both, or replace?
2. If your requester selects to replace, record it: `akasha impact <task> --changes-task <earlier task> "<what changes>"`. Akasha tells the earlier requester on GitHub. Do not wait for an answer.

## Stage 3 — Build

1. Make the change only in the work copy that Akasha shows.
2. Change only the files in the scope. If the change needs more files, record them with `akasha specify <task> --scope <file patterns>`.
3. Write an automated test for each completion condition. Then later tasks keep the behavior that the requester accepted.
4. Run `akasha advance <task>`.

## Stage 4 — Checks and repair

1. Run `akasha check <task>`. When all checks pass, Akasha saves the work and pushes the task branch.
2. Repair each failure. Then run the check again.
3. If Akasha stops the task after three failed repairs, stop the work. Tell the requester in simple words that a developer must examine the problem.
4. When the developer tells you to continue, record it: `akasha resume <task> --by <developer>`.
5. Update `.akasha/context/product-map.md` in the work copy for each feature, screen, table, or API that the change adds or changes. If nothing changes, record why: `akasha impact <task> --map-unchanged "<reason>"`.
6. When all checks pass, run `akasha advance <task>`.
7. Continue with the akasha-inspect skill. For the `small` workflow, continue with the akasha-handover skill.

> **NOTE:** Do not show the raw output of a check to the requester. Tell the result in simple words.
