---
name: akasha-inspect
description: Show the result to the requester in a preview and record the inspection. Use when an Akasha task is at the inspection stage.
---

# Inspect the feature with the requester

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Procedure

1. Run `akasha show <task>`. Read the preview command and the completion conditions.
2. Start the preview with that command in the work copy of the task.
3. Show each completion condition to the requester with sample data.
4. For each condition, ask the requester: "Is this the correct result?"
5. Record each answer: `akasha accept <task> --condition "<condition>" --result yes` or `--result no`.
6. If an answer is no, repair the change in the work copy. Then do stage 4 of the akasha-request skill again.
7. When all answers are yes, run `akasha advance <task>`.
8. Continue with the akasha-handover skill.

> **CAUTION:** Only the requester can accept a result. Do not accept a result for the requester.
