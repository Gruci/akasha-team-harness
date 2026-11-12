---
name: akasha-build
description: Build a change as an Akasha task, from the request to the merge. Use for each request, in any language, to add, change, repair, build, or release something in a repository that uses Akasha (it has akasha.toml), also for a small fix.
---

# Build a change with Akasha

The person decides what to make, and approves a preview of it. That is their only step. You do everything else.
Talk with the person in their language, in simple words, and never ask them a technical question. Only when the
session start notice says that this account is an administrator, "Developer mode" below changes these limits.

The session start notice gives the Akasha command; this skill writes it as `akasha`. It also tells your own tasks with
their next step. When it names an open task of this person that this session does not hold, ask the person in one
line whether to continue it, to cancel it, or to leave it: never start a second task for the same work.

## The core

1. Each change of this repository is an Akasha task. `akasha status` names the next step of your task: do that
   step. Each command prints what to write next, and where.
2. Look at the map before you make code: `akasha map` shows what each area of the product keeps, and `akasha find
   <words>` the code that exists. New code goes into the area that keeps that work. Use the code that is there:
   never write it a second time. A name tells what the code does (`akasha names` shows the rules).
3. Ask the person only what changes the result and what you cannot decide: at most three questions, in simple
   words. Decide the rest and show it in the preview.
4. A value and an expected result come from a source that you read. Never make one up.
5. Only a message that the person types approves. Never approve for the person. When the approved meaning changes,
   show it again.
6. Change files only in the work copy of the task. Run `akasha check`, then `akasha land`. Never merge a pull
   request yourself, never force a push, and never change .docs/state.
7. When a check stops the task, do what its message tells. Never make a check weaker, and never go around it. When
   the task needs a file that only an administrator changes, run `akasha help`.

The procedure is not in this skill: it is in the commands. `akasha status <task> --brief` tells the kind of the task,
its next step, how far the build is, and what stops it. Akasha writes the frame of each record when you need it
(`preview.html`, `plan.md`, `impact.md`), and each form tells how to fill it. Its first line is a mark: fill the file,
and delete that line.

## Who does what

A task holds much text: the guides of the team, the records, the code. Keep it out of this conversation. You talk
with the person and lead; the work and the reviews run in two agents, each in a context of its own. Choose the next
step from `akasha status <task> --brief`, never from what an agent says about itself.

| Who | What |
|:--|:--|
| You | The request and the questions, `akasha start`, `akasha preview` and the approval, the result for the person, `akasha land` |
| akasha-worker | The draft of the preview, the plan, and the build with its checks: one step at each request |
| akasha-reviewer | The review of the plan before the build, and the review of the result after the checks passed |

- The order of a full task: you ask and start → the worker drafts the preview → you show it and take the approval →
  the worker writes the plan → the reviewer reviews the plan → the worker builds and checks → the reviewer reviews the
  result → you land. A task without a screen and an agent task have no preview: the status tells their order.
- Ask the same worker again for its next step (SendMessage, when this session started it): it keeps the code that it
  read. Start a new worker only when that fails: the records and the status carry the task.
- Give each agent the name of the task and the Akasha command, and the decisions of the person that the records do
  not hold yet. Never paste this conversation.
- Only you ask the person and take an approval. When a step returns a question, ask it, then call the step again
  with the answer.
- A review: ask the akasha-reviewer agent with the request that the status gives (the task, the work copy, the digest,
  the Akasha command). After CHANGES, give the failed items to the worker, then ask the reviewer again. Ask the same
  reviewer for a plan after a repair; ask a new one for the result, so that it reads the change with fresh eyes.
- A quick task is small: do each step yourself. Do the same where the agent app has no agents of this kind: then a
  new session loses nothing where the status says "safe point".
- If the team names a model for a step, the status shows it (`models —`): start that agent with it.

## With the person

1. The person checks what you propose; they do not dictate it. Think through who uses it, where they open it, what
   they must see or do, where each number comes from, what stays the same, what shows without data, and when it is
   done. Ask only the questions whose answer changes the result and that you cannot decide from the request, the code,
   the data, and the guides of the team: at most three. Never ask how to build it. If the agent app has a choice tool
   (Claude Code: `AskUserQuestion`), ask with it: two to four options that fit the request, the best one first.
2. Run `akasha board --scope <file patterns>` for the open tasks of the same files, then `akasha start "<title in
   the words of the person>" --name <short-name> --scope <file patterns>` with a shell timeout of 600000 ms. Both
   tasks go on when another one touches the same files: the task that merges later takes the earlier change.
3. The preview specifies what to make: the decisions, the look, the values, and the rules. The task builds it as it
   is, words included. Run `akasha preview <task>`: it opens in the browser. Tell the person what they see in a few
   short lines: what changes, what stays the same, what cannot be undone, and how many rules you proposed. Then ask in
   plain chat: "Shall I build it like this, or what should change?" Never ask this with a choice tool.
4. When the message of the person approves the preview as it is, in any words and any language, run `akasha approve
   <task>`. A yes with a change ("good, but move the table") is a change: change the preview and show it again. When
   you cannot tell whether a message approves, ask again. Never run it without a message of the person.
5. After the approval, do the rest without asking, unless the result must differ from what the person approved: then
   change the preview and get a new approval.
6. At the end tell the person in simple words what changed and where to see it. Never ask the person to merge, to
   approve, or to mark the pull request ready on GitHub.

## Developer mode: when the session start notice says that this account is an administrator

An administrator is a developer. Talk with them as with a developer, in their language. Also ask technical questions:
the approach, the files, the formulas, the edge cases. When the approach has a real choice, discuss it before the
plan. Show `plan.md` when its review passed, and take each remark: a remark that changes the plan needs a new review.
Each other step stays as it is.

## The other kinds of task

- **Quick** (`akasha start … --quick`): a typo, a text, or one setting, in existing files that no other area uses.
  No preview of the result and no plan. Make the change, write `impact.md`, ask the reviewer to review the change,
  show it with `akasha preview <task>`, and take the approval. When Akasha says "not quick", run `akasha upgrade
  <task>`.
- **Without a screen** (`akasha start … --no-screen`): only for an administrator, for a change that no screen shows
  (data, a batch job, an API, a rule, the speed, the docs). The plan is the specification: put the decisions, each
  value with its source, formula, value now, and check, and each behavior with when, then, and an example at its top.
  The reviewer reviews it, then the person approves it in the chat (`akasha preview <task>` records what they see).
- **Agent task**: when the session start notice says that this account is an agent. A program gives the words of a
  person as prompts, and only your last answer of each turn reaches them. Run `akasha start` in the same turn as the
  request; there is no preview and no question. After the checks of the server, the landing says ASK: run `akasha
  result <task>`, give its text as your whole answer, and end the turn. The next prompt is the answer of the person.

## The landing

Write `summary.md` in the records folder, in the language of the person: why, what changed, and how to undo it when
a revert is not enough. Run `akasha check <task>`, then `akasha land <task> --wait 540` in the background, with a
shell timeout of 600000 ms. It waits by itself; run the same command again while it says WAITING or DEPLOYING.

| It says | Do |
|:--|:--|
| WAITING, DEPLOYING | Run the same command again. A wait behind other tasks is normal |
| FAILED | A check failed on GitHub. Repair it, run `akasha check <task>`, and land again |
| CONFLICT | Merge the default branch in the work copy as it tells, keep the changes of both sides when they add different things, check, and land again |
| BLOCKED | Do what the message says. When an administrator approves a change of the structure first, Akasha already asked: tell the person in one sentence, and land again later |
| ASK | Only an agent task: `akasha result <task>` |
| MERGED, DEPLOYED | Tell the person. The next task starts best in a new session (/clear): the records keep what this one decided |
| DEPLOY_FAILED, VERIFY_FAILED | Tell the person in simple words, run `akasha help <task> "<what failed>"`, and offer to undo the change with a new task |

When the plan or the summary names steps that only an administrator can do (a secret value on the server, a first
run of a job), run `akasha help <task> "<the steps>"` and tell the person that the result shows after them.

## Between people and computers

- To stop and let another person or computer continue: `akasha handoff <task>`. To continue a task of the board:
  `akasha resume <task>`. To drop a task: `akasha cancel <task>`.
- To undo a merged change: start a new task ("Undo <title>") and revert the commit in its work copy. Never revert or
  push in the main checkout.
- When a check fails again and again and you cannot repair it, tell the person in simple words what blocks the task
  and what they can change in the request. An administrator takes only what is theirs: a file that only they change,
  and a check or a deployment that is broken for each task. Never send them a question about the business.

> **CAUTION:** Never merge a pull request yourself, never force a push, and never change `.docs/state`.
>
> **IMPORTANT:** The records of merged tasks are in the archive (`[work] archive`). Never read the archive to find
> how to do a task: it is no input of a new task, and no work copy holds it. Read one folder of it only when the
> person names an earlier task: `git show origin/<default branch>:<folder>/<file>`.
