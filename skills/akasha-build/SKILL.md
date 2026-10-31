---
name: akasha-build
description: Build a change as an Akasha task, from the request to the merge. Use for each request to add, change, or repair something in a repository that uses Akasha (it has akasha.toml), also for a small fix.
---

# Build a change with Akasha

The person decides what to make, and approves a preview of it. That is their only step. You do everything else:
the research, the plan, a review of the plan by another AI, the build, the checks, and the landing. Talk with the
person in their language, in simple words, and never ask them a technical question.

The session start notice gives the Akasha command; this skill writes it as `akasha`. It also tells the open tasks of
the team, the guides of the team (`[guides]` of `akasha.toml`), and your own tasks with their next step. When it names
a task of yours, do its next step first.

## 1. Understand the request

1. Ask what the person wants to see and do, and which result they expect, until it is clear. Ask one question at a
   time. Do not ask how to build it.
2. Run `akasha board`. If another open task changes the same screen or feature, tell the person who holds it.
3. Find the files that the change will probably touch. Run
   `akasha start "<title in the words of the person>" --name <short-name> --scope <file patterns>`.
   It makes the work copy, and a draft pull request on the board. Akasha shows an overlap with another task: tell
   the person, and continue unless they want to wait. If the name is in use, give another name.
4. If the agent app can move the session into a folder (Claude Code: `EnterWorktree` with the path of the work copy),
   move into the work copy, so that the own checks of the repository see the right paths. Leave it again
   (`ExitWorktree`) before `akasha handoff` or `akasha cancel`, and after the landing ends.

## 2. The preview: the decision of the person

1. Read the files of `[guides] preview`.
2. Write one self-contained HTML file named `preview.html` in the records folder of the task (`akasha start` and
   `akasha status` name it), in the work copy. No links to other files or sites:
   - For a screen: a mockup with the real words of the screen, realistic sample data, and the states that matter
     (empty, loading, error).
   - For a change without a screen (data, a batch job, an API, a rule): a diagram of the flow, and a table of the
     result before and after with sample values.
   - At the top, three short lines: what changes, what the person will see, and what stays the same.
3. Run `akasha preview <task>`. It opens the preview in the browser. Tell the person what they see in a few short
   lines, then ask in plain chat: "Shall I build it like this? Answer '승인' (approve), or tell me what to change."
   Never ask with AskUserQuestion or another choice tool: only a chat message that the person types is an approval.
4. When the person asks for a change, change the preview, run `akasha preview <task>` again, and ask again.
5. When the person approves, the hook records it from their own message and tells you. Never write or claim an
   approval yourself. If the person meant yes in other words, ask them to answer '승인'.

## 3. The plan and its review: no person

1. Write `research.md` in the records folder: how the code and the data work now, each caller and reader of what will
   change, and the limits. Read the files of `[guides] plan` first.
2. Write `plan.md` there: the approach, each file and the exact change, the tests for each behavior that the preview
   shows, the risks, and how to undo the change. No "TBD".
3. Run `akasha status <task>` for the plan digest. Ask the akasha-reviewer agent: "Review the plan of Akasha task
   <task>. Work copy: <path>. Plan digest: <digest>. Akasha command: <the command of the session start notice>." It
   ends with a review mark, and Akasha records it. Only the akasha-reviewer agent counts. Repair the plan, and ask
   again with the new digest, until the mark is PASS.
4. If the review shows that the result must differ from the approved preview, change the preview and get a new
   approval from the person (step 2.3). Else do not ask the person anything.
5. Only an agent app without a reviewer agent (for example Codex) reviews the plan itself, as strictly as the agent
   would, then runs `akasha review <task> --verdict pass`. Akasha refuses it in Claude Code.

## 4. Build and check

1. Change the files only in the work copy of the task. Akasha stops an edit before the approval and the review.
2. Write an automated test for each behavior that the preview shows.
3. Run `akasha check <task>` with a shell timeout of 600000 ms (10 minutes), or in the background. Repair each FAIL
   and run it again. NOT_NEEDED is a pass. When the checks pass, Akasha saves the work as a commit and pushes it.
4. If Akasha tells you of an overlap with another task after an edit, change only what your task needs in that file.
5. If you cannot repair a failure after three tries, or the cause is outside the task, run
   `akasha help <task> "<what blocks you>"` and tell the person that an administrator will look.

## 5. Land

1. Write `summary.md` in the records folder, in the language of the person: why, what changed, and how to undo it, in
   three short sections.
2. Run `akasha check <task>` again, then `akasha land <task> --wait 540` with a shell timeout of 600000 ms.
   - WAITING (exit code 3): run the same command again. If it names a check that did not run or that waits for a
     runner, or you get WAITING three times in a row, run `akasha help <task>` and tell the person.
   - FAILED: a check failed on GitHub. Repair it, run `akasha check <task>`, then land again.
   - CONFLICT: run `akasha land <task>` again. It brings the latest default branch into the work copy and names the
     files: merge as it tells, repair, check, and land again.
   - REVIEW: a reviewer must review the change. Tell the person who it is, and say: "검토가 끝나면 '이어서 해 줘'라고
     말해 주세요". Then land again, also in a later session. When a reviewer asked for changes, repair them first.
   - BLOCKED: do what the message says, then land again.
   - MERGED: tell the person in simple words what changed and where to see it. If the team deploys each merge,
     Akasha follows the deployment: DEPLOYING (exit code 3) means run the same command again, DEPLOYED means the
     change is live, and DEPLOY_FAILED means tell the person and run `akasha help <task>`. If Akasha says that the
     work copy has changes that are not on GitHub, tell the person, and start a new task for them.
3. Never ask the person to merge, to approve, or to mark the pull request ready on GitHub. Akasha lands each task.

## Between people and computers

- To stop and let another person or computer continue: `akasha handoff <task>`. To continue a task of the board:
  `akasha resume <task>`.
- To drop a task: `akasha cancel <task>`.
- To undo a merged change: start a new task ("Undo <title>") and revert the commit in its work copy. Never revert or
  push in the main checkout.

> **CAUTION:** Never merge a pull request yourself, never force a push, and never change `.akasha/state`.
