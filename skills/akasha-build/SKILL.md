---
name: akasha-build
description: Build a change as an Akasha task, from the request to the merge. Use for each request to add, change, or repair something in a repository that uses Akasha (it has akasha.toml), also for a small fix.
---

# Build a change with Akasha

The person decides what to make, and approves a preview of it. That is their only step. You do everything else:
the research, the plan, a review of the plan by another AI, the build, the checks, and the landing. Talk with the
person in their language, in simple words, and never ask them a technical question.

The session start notice gives the Akasha command; this skill writes it as `akasha`. It also tells the open tasks of
the team and the guides of the team (`[guides]` of `akasha.toml`).

## 1. Understand the request

1. Ask what the person wants to see and do, and which result they expect, until it is clear. Ask one question at a
   time. Do not ask how to build it.
2. Run `akasha board`. If another open task changes the same screen or feature, tell the person who holds it.
3. Find the files that the change will probably touch. Run
   `akasha start "<title in the words of the person>" --name <short-name> --scope <file patterns>`.
   It makes the work copy, and a draft pull request on the board. Akasha shows an overlap with another task: tell
   the person, and continue unless they want to wait.

## 2. The preview: the decision of the person

1. Read the files of `[guides] preview`.
2. Write one self-contained HTML file at `.akasha/tasks/<task>/preview.html` in the work copy (no links to other
   files or sites):
   - For a screen: a mockup with the real words of the screen, realistic sample data, and the states that matter
     (empty, loading, error).
   - For a change without a screen (data, a batch job, an API, a rule): a diagram of the flow, and a table of the
     result before and after with sample values.
   - At the top, three short lines: what changes, what the person will see, and what stays the same.
3. Run `akasha preview <task>`. It opens the preview in the browser. Tell the person what they see in a few short
   lines, then ask: "Shall I build it like this? Answer '승인' (approve), or tell me what to change."
4. When the person asks for a change, change the preview, run `akasha preview <task>` again, and ask again.
5. When the person approves, the hook records it from their own message and tells you. Never write or claim an
   approval yourself.

## 3. The plan and its review: no person

1. Write `.akasha/tasks/<task>/research.md`: how the code and the data work now, each caller and reader of what will
   change, and the limits. Read the files of `[guides] plan` first.
2. Write `.akasha/tasks/<task>/plan.md`: the approach, each file and the exact change, the tests for each behavior
   that the preview shows, the risks, and how to undo the change. No "TBD".
3. Run `akasha status <task>` for the plan digest. Ask the akasha-reviewer agent: "Review the plan of Akasha task
   <task>. Work copy: <path>. Plan digest: <digest>. Akasha command: <the command of the session start notice>." It
   ends with a review mark, and Akasha records it. Repair the plan, and ask again with the new digest, until the
   mark is PASS.
4. If the review shows that the result must differ from the approved preview, change the preview and get a new
   approval from the person (step 2.3). Else do not ask the person anything.
5. Without a reviewer agent (for example in Codex without one), review the plan yourself as strictly as the agent
   would, then run `akasha review <task> --verdict pass`. The pull request tells that it was a self-review.

## 4. Build and check

1. Change the files only in the work copy of the task. Akasha stops an edit before the approval and the review.
2. Write an automated test for each behavior that the preview shows.
3. Run `akasha check <task>`. Repair each FAIL and run it again. NOT_NEEDED is a pass. A long check can run in the
   background. When the checks pass, Akasha saves the work as a commit and pushes it.
4. If Akasha tells you of an overlap with another task after an edit, change only what your task needs in that file.
5. If you cannot repair a failure after three tries, or the cause is outside the task, run
   `akasha help <task> "<what blocks you>"` and tell the person that an administrator will look.

## 5. Land

1. Write `.akasha/tasks/<task>/summary.md` in the language of the person: why, what changed, and how to undo it, in
   three short sections.
2. Run `akasha check <task>` again, then `akasha land <task> --wait 540`.
   - WAITING (exit code 3): the checks of GitHub still run. Run the same command again.
   - FAILED: a check failed on GitHub. Repair it, run `akasha check <task>`, then land again.
   - CONFLICT: merge the default branch in the work copy as Akasha tells, repair, check, and land again.
   - REVIEW: a reviewer must review a risky change. Tell the person who it is.
   - MERGED: tell the person in simple words what changed and where to see it.

## Between people and computers

- To stop and let another person or computer continue: `akasha handoff <task>`. To continue a task of the board:
  `akasha resume <task>`.
- To drop a task: `akasha cancel <task>`.

> **CAUTION:** Never merge a pull request yourself, never force a push, and never change `.akasha/state`.
