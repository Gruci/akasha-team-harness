---
name: akasha-request
description: Do a change as an Akasha task, from the request to the checks. Use for each request to add, change, or repair a feature in a repository that has akasha.toml.
---

# Do a change as an Akasha task

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Who answers which question

| Person | Questions |
|:--|:--|
| Requester | The goal, the use scenario, the completion conditions, and the business rules |
| Developer | Risk, code structure, and data |
| Administrator | The team rules |

Do not ask the requester technical questions.

## Stage 1 — Request

1. Select the workflow:
   - `feature` for a new feature or a changed feature.
   - `fix` for a defect.
   - `small` for a small change with clear completion conditions.
2. Record the task: `akasha request "<title>" --requester <name> --workflow <workflow> --feature <feature key>`.
3. If Akasha shows an overlap, tell the requester. Do the action that Akasha shows.
4. Ask the requester questions until the completion conditions are clear. Ask about dates, permissions, and the current behavior.
5. Record each condition: `akasha specify <task> --condition "<condition>"`.
6. Record each question that is not answered: `akasha specify <task> --question "<question>"`.
7. When all questions have answers, run `akasha specify <task> --clear-questions`.
8. Run `akasha advance <task>`.

> **NOTE:** The `fix` and `small` workflows have no specification stage. For these workflows, do step 1 of stage 2 before you advance.

## Stage 2 — Specification and risk

1. Find the files that the change needs. Record them: `akasha specify <task> --scope <file patterns>`.
   Akasha sets the risk level from these files and shows each overlap with other tasks.
2. Run `akasha show <task>`. Read the risk level and the risk reasons.
3. Write a short specification for the requester in simple words. Tell what changes, what does not change, and the risk level.
4. Ask the requester to approve it. Record the approval: `akasha approve <task> --role requester --by <name>`.
5. Run `akasha advance <task>`.
6. If Akasha says that a developer must approve the risk level, ask a developer. Record the approval with `--role developer`. Then do step 5 again.

> **CAUTION:** Never record an approval for a person who did not give it.

## Stage 3 — Build

1. Make the change only in the work copy that Akasha shows.
2. Change only the files in the scope of the task. If the change needs more files, tell the requester why. Then record the files with `akasha specify <task> --scope <file patterns>`.
3. Run `akasha advance <task>`.

## Stage 4 — Checks and repair

1. Run `akasha check <task>`.
2. Repair each failure. Then run the check again.
3. If Akasha stops the task after three failed repairs, stop the work. Tell the requester in simple words that a developer must examine the problem.
4. When the developer tells you to continue, record it: `akasha resume <task> --by <developer>`.
5. When all checks pass, run `akasha advance <task>`.
6. Continue with the akasha-inspect skill. For the `small` workflow, continue with the akasha-handover skill.

> **NOTE:** Do not show the raw output of a check to the requester. Tell the result in simple words.
