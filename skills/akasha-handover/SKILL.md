---
name: akasha-handover
description: Open the pull request with the handover document. Use when an Akasha task is at the handover stage.
---

# Hand over the change to a developer

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Procedure

1. Run `akasha handover <task>`.
   Akasha checks the change again on the latest default branch, pushes the branch, and opens the pull request.
2. If Akasha reports a conflict, do the steps in the message. Then do step 1 again.
3. If Akasha says that the required checks or branch protection are not on, tell an administrator.
   Correct the GitHub settings with the akasha-setup skill. Then do step 1 again.
4. Tell the requester the address of the pull request.
5. Tell the requester that a developer reviews and merges the pull request.
6. If the developer asks for changes, make them in the work copy. Then do step 1 again.
   Akasha adds the changes to the same pull request.

> **CAUTION:** Do not merge the pull request. A developer merges it. Do not force push.
