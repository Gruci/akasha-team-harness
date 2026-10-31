---
name: akasha-inspect
description: Show the result to the requester in a preview and record the inspection. Use when an Akasha task is at the inspection stage.
---

# Inspect the feature with the requester

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Procedure

1. Run `akasha show <task>`. Read the completion conditions.
2. Run `akasha preview <task>`. Akasha reserves the port of the task on this computer, runs the seed command of the team in the work copy, and shows the filled preview values. Use only these values: another task can use a different port or database.
   - If Akasha shows `[FAIL] seed`, read the output. Repair the cause, then run `akasha preview <task>` again. If the cause is outside the task, for example a database server that does not answer, tell the user.
   - If Akasha shows no preview command, ask the user how to start the product. Use the port that Akasha shows.
3. Start the preview with the preview command in the work copy of the task. Show each completion condition to the requester with sample data.
   - The preview runs on this computer. If the requester is on another computer, the requester needs access to the preview here, for example in the same network. Else ask the user how the requester can see it.
4. For each condition, ask the requester: "Is this the correct result?"
5. Record each answer. If the requester is the GitHub account of this computer, run `akasha accept <task> --condition <number> --result yes`, or `--result no --reason "<reason>"`. Else the requester writes `/accept <number> r<N>` or `/reject <number> r<N> <reason>` on the issue of the task. `akasha show <task>` shows the numbers and the revision `r<N>`. Without GitHub, run `akasha accept <task> --condition <number> --result yes`, or `--result no`, with the answer of the requester.
6. If an answer is no, repair the change in the work copy. Then do stage 4 of the akasha-request skill again.
7. When all answers are yes, run `akasha advance <task>`.
8. If Akasha says that the server rules are not on, tell an administrator. Correct the GitHub settings with the akasha-setup skill.
   - If Akasha says that a server file is different from the file that the Akasha on this computer makes, tell the user to update Akasha first. The version stays 1.0.0, so `/plugin update` and a plain `pip install` keep the old copy. In Claude Code, the user closes Claude Code, removes the folder `.claude/plugins/cache/akasha` in the home folder, runs `claude plugin install akasha@akasha` in a terminal, and opens Claude Code again. For Codex, the user runs `pip install --force-reinstall "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`. Then run `akasha advance <task>` again. If the file is still different, tell an administrator.
9. Continue with the akasha-handover skill.

> **CAUTION:** Only the requester can accept a result. Do not accept a result for the requester.
