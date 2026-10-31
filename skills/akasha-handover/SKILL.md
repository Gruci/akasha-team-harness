---
name: akasha-handover
description: Write the briefing, open the pull request, and let GitHub merge it. Use when an Akasha task is at the handover stage.
---

# Hand over the change

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Write the briefing

The briefing becomes the pull request text and the body of the merge commit. A person who must revert the change later reads it. Write short, simple sentences in Simplified Technical English. Use few file names.

Write the sections in this order. Remove Tradeoffs when there was no real choice.

| Section | Content |
|:--|:--|
| `## Why` | The problem and the approach. 1 to 3 sentences |
| `## What changed` | 1 to 3 items. Name a file or a function only when it carries the change |
| `## Scope` | 1 to 3 items: what the change covers, and what it leaves out |
| `## Tradeoffs` | Only the alternatives that a reviewer would ask about |
| `## Blast Radius` | 1 or 2 sentences: what the change touches, why that is safe or risky, and how to reverse it |

Do not write `## Verification`. Akasha writes it from the real results of the checks and the inspection.

## Procedure

1. Write the briefing to a file outside the work copy.
2. Run `akasha brief <task> --file <path>`. If Akasha shows problems, correct the briefing. Then do this step again.
3. Run `akasha handover <task>`.
   Akasha merges the task branch on the server and the latest default branch, checks the change again, opens the pull request, and turns on auto-merge where GitHub merges.
4. If Akasha reports a conflict, do the steps in the message. Then do step 3 again.
   If Akasha says that a required check did not pass on the latest default branch, repair the change in the work copy. Then do step 3 again.
5. If the task builds on an earlier task, Akasha waits until the earlier task merges. Tell the requester. Do step 3 again later.
   If Akasha says that the earlier task was cancelled, run `akasha specify <task> --builds-on ""`. Remove the changes of the earlier task that this task does not need, and run `akasha check <task>`. Then do step 3 again.
6. Tell the requester: "GitHub merges the change when the server check passes."
   With the GitHub app of Akasha, the helpers bring the pull request up to date on GitHub when the default branch moves, and the server check runs again.
   If the change touches files that a code owner owns, for example a folder with a person gate, the merge also waits for the approval of an owner on GitHub. Tell the requester who must approve.
7. If the server check fails, repair the change in the work copy. Then do step 3 again. Akasha adds the repair to the same pull request.
   Akasha also writes a comment on the pull request and on the issue of the task when the server check fails, or when the pull request conflicts with the latest default branch. `akasha advance <task>` and `akasha show <task>` show it as a news line. For a conflict, do step 3 again: Akasha merges the default branch into the work copy and shows the files that conflict.
8. Later, run `akasha advance <task>`. When GitHub merged the pull request, the task is done.

> **CAUTION:** Do not merge the pull request yourself. GitHub merges it when the server check passes. Do not force push.
