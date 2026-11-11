---
name: akasha-build
description: Build a change as an Akasha task, from the request to the merge. Use for each request, in any language, to add, change, repair, build, or release something in a repository that uses Akasha (it has akasha.toml), also for a small fix.
---

# Build a change with Akasha

The person decides what to make, and approves a preview of it. That is their only step. You do everything else:
the research, the plan, a review of the plan by another AI, the build, the checks, and the landing. Talk with the
person in their language, in simple words, and never ask them a technical question. Only when the session start
notice says that this account is an administrator, "Developer mode" below changes these limits.

The session start notice gives the Akasha command; this skill writes it as `akasha`. It also tells the open tasks of
the team, the guides of the team (`[guides]` of `akasha.toml`), and your own tasks with their next step. When it names
a task of yours, do its next step first.

## The core

1. Each change of this repository is an Akasha task. `akasha status` names the next step of your task: do that
   step. Each command prints what to write next, and where.
2. Ask the person only what changes the result and what you cannot decide: at most three questions, in simple
   words. Decide the rest and show it in the preview.
3. Use the code that exists. `akasha start` prints the rules to follow first, then what is near your task and where
   it is; `akasha find <words>` searches it. The list shows the code as it is now. It is not a model: the guides of
   the team, the definitions, and the entries of an area tell which path to use and how to build. A name tells what
   the code does: follow the rules for names that `akasha start` prints (`akasha names` shows each rule).
4. A value and an expected result come from a source that you read. Never make one up.
5. Only a message that the person types approves. Never approve for the person. When the approved meaning changes,
   show it again.
6. Change files only in the work copy of the task. Run `akasha check`, then `akasha land`. Never merge a pull
   request yourself, never force a push, and never change .docs/state.
7. After three failed tries, or when the task needs a file that only an administrator changes, run `akasha help`.

Akasha writes the frame of each record when you need it: `preview.html` at the start, `research.md` and `plan.md`
at the approval (at the start for a task without a preview), `impact.md` for a quick task. Each form tells how to
fill it. Its first line is a mark: a file that still has it counts as not written. Fill the file, and delete that
line.

## The steps in new contexts

A task holds much text: the guides of the team, the records, and the answers of the reviewer. Keep it out of this
conversation. You talk with the person and lead the steps, and each step runs in an agent of its own, in a new
context. The records and `akasha status <task> --brief` carry the task from one step to the next. Choose the next
step from `akasha status <task> --brief`, never from what a step says about itself.

| Task | The order. "You" is this session |
|:--|:--|
| full | You: the request and the questions → akasha-preview → you: `akasha preview`, and the approval → akasha-planner ⇄ akasha-reviewer → akasha-builder → akasha-lander → you: the result |
| without a screen | You: the request and the questions → akasha-planner ⇄ akasha-reviewer → you: the plan, and the approval → akasha-builder → akasha-lander → you: the result |
| agent task | You: the request → akasha-planner ⇄ akasha-reviewer → akasha-builder → akasha-lander, which stops at ASK → you: `akasha result`, and the approval → akasha-lander |
| quick | You do each step yourself: it is small |

- Give each agent the name of the task and the Akasha command, and the decisions of the person that the records do
  not hold yet. Never paste this conversation.
- Only you ask the person and take an approval. When a step returns a question, ask it, then call the step again
  with the answer.
- The review: call akasha-planner, then akasha-reviewer. After CHANGES, call akasha-planner again with the failed
  items, then the reviewer again. The reviewer returns a short report; its whole answer is in `review.md`.
- A step returns a failure or a stop as it is. Do what `akasha status <task> --brief` says next.
- Run akasha-lander in the background, and tell the person the result when it returns.
- The sections below tell what each step does. Follow them yourself only for a quick task, and where the agent app
  has no agents of this kind: then do the steps in this session, and where `akasha status <task> --brief` says
  "safe point", a new session loses nothing.

## 1. Understand the request

1. The person checks what you propose; they do not dictate it. Go through these seven questions:
   - Who uses it? Must some people not see it?
   - Where do they open it (which screen or menu)?
   - What must they see or do?
   - For data: where does it come from, how is each number computed, and how new must it be?
   - What changes in what exists now, and what stays the same?
   - What shows when there is no data, or when an entry is wrong?
   - When is it done? What will the person check?

   Ask only the questions whose answer changes the result and that you cannot decide from the request, the code, the
   data, and the guides of the team: at most three, in simple words. Never ask how to build it: no formula, no field,
   no edge case. Decide the rest yourself, and show it in the preview as your proposal (step 2), where the person can
   check it.

   If the agent app has a choice tool (Claude Code: `AskUserQuestion`), ask these questions with it: up to four
   questions in one call, each with two to four options that fit the request, in the words of the person. Put the
   option that you think fits best first. Never make an option that only leads the person to your own idea: the tool
   always lets the person type another answer. Without a choice tool, ask one question at a time in the chat.
   The choice tool is only for these questions. The approval of the preview (step 2) is always a message that the
   person types.
2. Read the files of `[guides] build`: they can name shared files that many tasks change, for example a list of
   routes or menus. Find the files that the change will probably touch, without those shared files.
3. Run `akasha board --scope <file patterns>`. When it names an open task that plans or changes the same files, read
   what it changes (`gh pr view <number>` and `gh pr diff <number>`), write it into `research.md` later, keep your
   change clear of its lines where the request allows it, and name it in `summary.md`. Do not ask the person to wait
   or to choose: both tasks go on, the task that merges later takes the earlier change, and its AI resolves a conflict
   and checks again before its merge (step 5).
4. Run `akasha start "<title in the words of the person>" --name <short-name> --scope <file patterns>` with a shell
   timeout of 600000 ms. It makes the work copy, and a draft pull request on the board. When it says that the plan
   needs a review, tell the person who will review. If the name is in use, give another name.

## Developer mode: when the session start notice says that this account is an administrator

An administrator is a developer. Talk with them as with a developer, in their language. Each other step of this skill
stays as it is.

1. In step 1, also ask technical questions with the choice tool: the approach, the files, the formulas, the data, the
   edge cases, and the tests. Name the files, the functions, and the tables. Put the option that you think fits best
   first, and ask only what you cannot decide from the code, the data, and the guides of the team.
2. When the approach has a real choice, discuss it with the person before you write the plan. Tell what the research
   found.
3. Show `research.md` and `plan.md`. When the review passes (step 3.3), give the person their paths and a short
   summary: the approach, each file and its change, the tests, and the risks. Take each remark: a remark that changes
   the plan needs a new review.
4. A change with a screen still has a preview (step 2), and only a message that the person types approves it.
5. A change without a screen has a plan in place of a preview: see the next section.

## A task without a screen: an administrator approves the plan

Only for an administrator, and only for a change that no screen shows: data, a batch job, an API, a rule, the speed,
or the docs. `[preview] screens` of `akasha.toml` names the files that make a screen. Akasha refuses the start when
the scope holds one of them, and the check `screen` fails when the change touches one. Without `[preview] screens`,
or when the change also needs a screen, make a full task with a preview.

1. Do step 1 in developer mode. Then run `akasha start "<title in the words of the person>" --name <short-name>
   --scope <file patterns> --no-screen` with a shell timeout of 600000 ms.
2. Write `research.md` and `plan.md` as in steps 3.1 and 3.2. The plan is the specification, so put at its top the
   decisions: each question that you asked and the answer of the person, one line each. For each value that comes
   from data, the plan gives its source, its formula, its value now with the time that you read it, and the query or
   command that gives it again. For each behavior that the person can notice, the plan gives when, then, and one real
   example. Plan a test for each value and each example.
3. Ask the akasha-reviewer agent to review the plan, as in step 3.3, until the mark is PASS.
4. Run `akasha preview <task>`: Akasha records that the person sees this version of the plan. Show the plan in the
   chat: the approach, each file and its change, the tests, the risks, and how to undo it when a revert is not
   enough, with the paths of
   `research.md` and `plan.md`. Then ask in plain chat: "Shall I build it like this, or what should change?" Never ask
   with AskUserQuestion or another choice tool: only a message that the person types counts.
5. When the person asks for a change, change the plan, ask the reviewer again, run `akasha preview <task>` again, and
   ask again. When the message of the person approves the plan as it is, run `akasha approve <task>`, as in step 2.6.
6. Continue with step 4 and step 5. A change of the plan after the approval needs the review and the approval again:
   Akasha stops the edits of the code until then. When the check `screen` fails, undo the change of that file, or
   cancel the task and start a full task with a preview.

## A quick task: a typo or one setting

A quick task has no preview of the result and no plan. Use it only for a small change of existing files that no other
area uses, for example a typo, a text, or one setting. Akasha decides from what the change touches, not from its
size: one line of a button that many screens use is not a quick change, and a quick change adds and deletes no file.
Skip the questions of step 1 that the request already answers.

1. Do steps 1.2 and 1.3 (the files, and the open tasks of the same files). Then run `akasha start "<title in the words
   of the person>" --name <short-name> --scope <file patterns> --quick`. When it says "not quick", run
   `akasha upgrade <task>` and follow the full steps from step 1.
2. Make the change in the work copy (step 4.1 tells how to move into it).
3. Write `impact.md` in the records folder, in the language of the person: each changed file, which screens use it
   (search for its imports, setting keys, CSS classes, and text keys), and why no other screen changes.
4. Run `akasha status <task>` for the change digest. Ask the akasha-reviewer agent: "Review the change of the Akasha
   quick task <task>. Work copy: <path>. Change digest: <digest>. Akasha command: <the command of the session start
   notice>." Repair until the mark is PASS. When the reviewer says that the change reaches other screens, run
   `akasha upgrade <task>`. When each changed file is text for people (`*.md`, `*.txt`, `*.rst`, `*.adoc`), skip
   this step: no code reads such a file, and the person reads all of the change in step 5.
5. Run `akasha preview <task>`: Akasha makes the preview from the change. Tell the person in a few short lines what
   changes, and ask in plain chat whether it is good. As in step 2, only a message that the person types approves it:
   then run `akasha approve <task>`.
6. Continue with step 4.3 (check) and step 5 (land). A change of the code after the review or the approval needs both
   again (only the approval, for a change of only text). When a check named `quick` fails, the change is not a quick change: run `akasha upgrade <task>`.

## An agent task: when the session start notice says that this account is an agent

A program (the relay) runs this session. Each prompt is the words of a person: first their request, for example the
diagnosis of a failed job and what to change, later their answer. The person does not see this session: only your last
answer of each turn reaches them. The request decides what to make, so there is no preview and no question of step 1.
The person approves the result before the merge. That is their only step.

1. Run `akasha start "<title>" --name <short-name> --scope <file patterns>` at once, in the same turn as the request:
   Akasha writes the prompt into `request.md` in the records folder. When it says that it found no request, end the
   turn and ask the person to send the request again. When it names an overlap with another task, read what that task
   changes as in step 1.3, go on, and name it in `summary.md`, under what other areas the change reaches.
2. Do step 3 (the plan and its review). Read `request.md` in place of a preview. When the request cannot work as it
   says, end the turn with a short question to the person, in their language.
3. Do step 4 (build and check).
4. Write `summary.md` in the language of the request, in five short sections: the problem, the cause, what changed,
   what other areas it reaches, and how to undo it when a revert is not enough.
5. Run `akasha check <task>`, then `akasha land <task> --wait 540` with a shell timeout of 600000 ms. When it says ASK
   (exit code 4), run `akasha result <task>`. Give its text as your whole answer, without other words, and end the
   turn: the relay sends it to the person.
6. The next prompt is the answer of the person. When it approves the result as it is, run `akasha approve <task>`,
   then `akasha land <task> --wait 540`, and give the end of step 5 in simple words (MERGED, DEPLOYED, …). When it
   asks for a change, change the work, run `akasha check <task>`, and land again: the landing asks again. Never
   approve without a prompt of the person.

## 2. The preview: the decision of the person

The preview specifies what to make: the person approves it, and the task builds it as it is, words included. It has
four parts, in this order: the decisions, the look, the values, and the rules. Akasha refuses a preview without the
decisions and the rules, and a value of data without its definition.

1. Read the files of `[guides] preview`: the design and the words of the screens of the team, and how a teammate reads
   the data.
2. Write one self-contained HTML file named `preview.html` in the records folder of the task (`akasha start` and
   `akasha status` name it), in the work copy. No links to other files or sites:
   - The decisions, at the very top: a box `<section id="akasha-decisions">` with a title of one line (what changes),
     and each question that you asked with the answer of the person, one line each: for a choice, the option that
     they chose; for typed words, what they decided, in plain words and never as a quote (the preview goes into git).
     The approval of the preview is the record of these answers.
   - The look: for a screen, a mockup with the real words of the screen and the states that matter (empty, loading,
     error). Draw it with the parts, the colors, the spacing, and the controls that the app already has: the task
     builds it as it is. For a change without a screen (data, a batch job, an API, a rule), a diagram of the flow and
     a table of the result before and after.
   - The values: never make up a value that comes from data. Read the source first, as `[guides] preview` tells, and
     find the source and the formula in the code and the data. Mark each such value of the look with
     `data-akasha-value="<key>"` and a link to its row. Below the look, a box `<section id="akasha-data">` with one row
     `<tr data-akasha-key="<key>">` for each value, with the cells `data-akasha-field="source"` (the table and field,
     the API, or the file), `"formula"` (how the source becomes the value), `"value"` (its value now, with the time
     that you read it), and `"check"` (the query or the command that gives it again; fold a long one in
     `<details>`). When `akasha start` said `data —`, the preview must mark one value or more.
   - The rules: a box `<section id="akasha-rules">` with one row `<tr data-akasha-rule="<key>"
     data-akasha-from="person|ai">` for each behavior that the person can notice (who sees it, a filter, an order,
     no data, a wrong entry), with the cells `data-akasha-field="when"`, `"then"`, and `"example"`: one real case
     that a test can check as it is. `person` marks a rule that the person decided in an answer, `ai` a rule that you
     decided: show which is which on the page. Do not list each edge case; the plan decides what the screen does not
     show. A new part that the app does not have yet is a rule with `ai`.
   - The boxes and the marks are the specification, not the screen: the task never builds them into the app.
3. The words of the preview are the words of the product. Follow the rules for words of `[guides] preview` first.
   Then: write in the language of the person and in the tone of the screens of the team; use the words of the
   person, and one name for one thing in the whole preview; one fact in a sentence, with no filler, no praise, no
   sales words, and no emoji; a label names what the person gets, not what the code does; a number has its unit and
   its date. Write nothing that explains Akasha or the boxes. Read the preview once more, and cut each word that
   changes no decision of the person. Hide personal data: the preview goes into git.
4. Run `akasha preview <task>`. It opens the preview in the browser. Tell the person what they see in a few short
   lines, and how many rules you proposed for them to check, then ask in plain chat, in the language of the person:
   "Shall I build it like this, or what should change?"
   Never ask with AskUserQuestion or another choice tool: only a message that the person types counts.
5. When the person asks for a change or asks a question, change the preview or answer, run `akasha preview <task>`
   again after a change, and ask again.
6. When the message of the person approves the preview as it is, in any words and any language, run
   `akasha approve <task>`. It records the approval with the exact words of the person on this computer; the pull
   request names only who approved and when. When a message mixes a yes
   with a change ("good, but move the table"), it is a change. When you cannot tell, ask. Never approve for the
   person, and never run it without a message of the person.

## 3. The plan and its review: no person

1. Write `research.md` in the records folder: how the code and the data work now, each caller and reader of what will
   change, and the limits. Read the files of `[guides] plan` first.
2. Write `plan.md` there: the approach, each file and the exact change, a test for each example of the rules and each
   value of the box of the values, the risks, and how to undo the change when a revert is not enough. The plan
   keeps each rule and each
   definition of the preview, also the ones that you proposed: the approval made them decisions. No "TBD". List each step that only an administrator can do, for
   example a new secret value on the server or a first run of a job; `summary.md` repeats them.
3. Run `akasha status <task>` for the plan digest. Ask the akasha-reviewer agent: "Review the plan of Akasha task
   <task>. Work copy: <path>. Plan digest: <digest>. Akasha command: <the command of the session start notice>." It
   judges ten items, one row each, ends with a review mark, and Akasha records it with the answer in `review.md`.
   Only the akasha-reviewer agent counts. Repair each item that failed, run `akasha status <task>` for the new plan
   digest, and ask again until the mark is PASS. Ask again by sending this to the same akasha-reviewer agent with
   SendMessage, when this session started it: "Plan digest is now <digest>. Run `<Akasha command> status <task>
   --review` again, judge what it names, and answer in the full form with the mark for <digest>." It keeps what it
   read. Ask a new akasha-reviewer agent with the request above instead when SendMessage fails, when that agent
   already reviewed three rounds (a long conversation loses the code that it read), or when after its answer
   `akasha status <task> --review` shows neither `Round … passed this version of the plan` nor
   `Last review: … digest <digest>`. On a review after a repair, the reviewer judges again only the items that failed and the items that
   the change of the plan touches, and keeps the rest (`akasha status <task> --review` tells it which): do not ask it
   to judge each item again. When the next step says that a PASS mark did not count, an item had no row or a kept
   row had not passed: ask again.
4. If the review shows that the result must differ from the approved preview, change the preview and get a new
   approval from the person (step 2.4). Else do not ask the person anything (an administrator: "Developer mode" step 3).
5. Only an agent app without the akasha-reviewer agent (for example Codex) reviews the plan itself, as strictly as
   the agent would, then runs `akasha review <task> --verdict pass`. Akasha refuses it in Claude Code.
6. Core files: when `akasha start` or `akasha check` names a core file (code that other areas use, or a path of
   `[core]`), use what it has, and extend it when the task needs it. Do not copy its code into a new function to go
   around the approval. When the task changes or deletes its existing lines, write why in `plan.md`, and keep each
   caller working. Then tell the person in one simple sentence that an administrator checks that part before it goes
   live.

## 4. Build and check

1. If the agent app can move the session into a folder (Claude Code: `EnterWorktree` with the path of the work copy),
   move into the work copy now, so that the own checks of the repository see the right paths. Leave it again
   (`ExitWorktree`) before `akasha handoff` or `akasha cancel`, and after the landing ends. Change the files only in
   the work copy of the task. Akasha stops an edit before the approval and the review.
2. Write an automated test for each example of the rules, and for each value of the box of the values: compute it
   from its source by its formula. The expected values come from the preview, never from what the new code makes.
   To give the work to several workers at the same time (for example subagents of an orchestrator), never make
   work copies with `git worktree add`: Akasha stops it. Run `akasha split <task> <part> --scope <file patterns>`
   for each worker, with files that no other part has, and give the worker the work copy and the scope that Akasha
   prints. When each worker is done, run `akasha join <task>`. When the join stops with a conflict, repair it in the
   part that it names, and join again. Then continue with the checks.
3. Run `akasha check <task>` in the background, or with a shell timeout of 600000 ms (10 minutes). Repair each FAIL
   and run it again. NOT_NEEDED is a pass. When the checks pass, Akasha saves the work as a commit and pushes it.
   Only an administrator changes `akasha.toml`, `.github/`, and the paths of `[risk]` (for example the database and
   the deployment). When Akasha stops such an edit, or the check `admin_only` fails, undo that part and run
   `akasha help <task> "<what the task needs there>"`. Tell the person in simple words that an administrator does that
   part; build the rest.
4. If Akasha tells you of an overlap with another task after an edit, change only what your task needs in that file.
   An overlap only in a shared file that `[guides] build` names is normal: do not alarm the person.
5. If you cannot repair a failure after three tries, or the cause is outside the task, run
   `akasha help <task> "<what blocks you>"` and tell the person that an administrator will look.

## 5. Land

1. Write `summary.md` in the records folder, in the language of the person: why, what changed, and how to undo it when a
   revert is not enough, in
   three short sections.
2. Run `akasha check <task>` again, then `akasha land <task> --wait 540` with a shell timeout of 600000 ms.
   - WAITING (exit code 3): run the same command again. When other tasks merged first, the wait is normal. Only when
     it names a check that did not run, or a check that waits long for a runner, run `akasha help <task>` and tell
     the person.
   - FAILED: a check failed on GitHub. Repair it, run `akasha check <task>`, then land again.
   - ASK (exit code 4): only an agent task. Do step 5 of "An agent task".
   - CONFLICT: Akasha names the files. Merge the default branch in the work copy as it tells, and keep the changes of
     both sides when they add different things (for example two new rows of a list). If `[guides] build` tells how to
     merge a shared file, do as it tells. Check, and land again.
   - BLOCKED: do what the message says, then land again. When it says that an administrator approves a core change
     first, Akasha already asked the administrators: tell the person in one simple sentence that an administrator
     checks one part, and land again later. Do not ask again with `akasha help`.
   - MERGED: tell the person in simple words what changed and where to see it. If the team deploys each merge,
     Akasha follows the deployment: DEPLOYING (exit code 3) means run the same command again, DEPLOYED means the
     change is live, and DEPLOY_FAILED means tell the person and run `akasha help <task>`. VERIFY_FAILED means the
     change is live, but the check of the team after the deployment failed: tell the person in simple words,
     run `akasha help <task> "<the check after the deployment failed>"`, and offer to undo the change with a new
     task. If the plan or the summary
     names steps that only an administrator can do (for example a secret value on the server, or a first run of a job),
     run `akasha help <task> "<the steps>"` and tell the person that the result shows after them. If Akasha says that
     the work copy has changes that are not on GitHub, tell the person, and start a new task for them.
   - When the landing ended (MERGED in a team without a deployment, DEPLOYED, or DEPLOY_FAILED or VERIFY_FAILED
     after `akasha help`), and the task is not an agent task: tell the person that the next task starts best in a
     new session (/clear). The records of this task keep what it decided, and a long session reads its whole past
     again at each answer.
3. Never ask the person to merge, to approve, or to mark the pull request ready on GitHub. Akasha lands each task.

## Between people and computers

- To stop and let another person or computer continue: `akasha handoff <task>`. To continue a task of the board:
  `akasha resume <task>`.
- To drop a task: `akasha cancel <task>`.
- A question that is not a change of the repository, for example about missing data or the server: run
  `akasha ask "<the question>"`. It asks the administrators in an issue. Do not start a task for it.
- To undo a merged change: start a new task ("Undo <title>") and revert the commit in its work copy. Never revert or
  push in the main checkout.

> **CAUTION:** Never merge a pull request yourself, never force a push, and never change `.docs/state`.
>
> **IMPORTANT:** The records of merged tasks are in the archive (`[work] archive`). Never read the archive to find
> how to do a task: it is no input of a new task, and no work copy holds it. Read one folder of it only when the
> person names an earlier task: `git show origin/<default branch>:<folder>/<file>`.
