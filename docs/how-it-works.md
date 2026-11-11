# How it works

## The principle

The person who asks for a change decides what to make. They decide it once, at the start, on a preview that
specifies it: the look (a mockup of the screen, or a diagram of the flow and the data), each value from data with its
source and formula, and each rule with an example. The AI asks only what changes the result and what it cannot
decide; it proposes the rest in the preview, where the person checks it. The person does not dictate formulas or
edge cases. The AI does everything after that, and another AI checks its plan in place of a person. Machines check
the result. GitHub merges it.

A team has three roles. A teammate asks for changes and approves their previews, and never reads code. An
administrator sets up and maintains Akasha and the few risky parts (the database, the deployment), and helps when an
AI is stuck. An agent account works from the requests of people that a program gives it, for example the diagnosis
of a failed job: the person approves its result before the merge (see "An agent task"). An administrator is a
developer: the AI talks technically with them, shows the research and the plan, and for a change without a screen
asks them to approve the plan in place of a preview (see "A task without a screen"). Nobody reviews a task, except
one kind of change: when a task changes existing lines of the core (code that other areas use), an administrator
approves it on GitHub before it lands.

| Step | Who | What happens |
|:--|:--|:--|
| 1. Request | The person | Says what they want, in their own words. The AI asks until it is clear |
| 2. Preview | The person | Looks at the preview in the browser: the look, the values, and the rules. Says "approve", or what to change |
| 3. Plan | The AI | The AI writes the research and the plan. A second AI (the akasha-reviewer agent) checks the plan until it passes |
| 4. Build | The AI | Changes the code in its own work copy, with a test for each example of the rules and each value of the preview |
| 5. Check | The AI and the checks | Runs the checks of the team until they pass |
| 6. Land | The AI and GitHub | Makes the pull request ready, brings it up to date, and merges it when the checks pass on GitHub |

## One task

A task is one change of one person.

| Part | Where |
|:--|:--|
| The work copy | A git worktree in `.claude/worktrees/<task>`, on the branch `akasha/<task>` (`[work]` changes both). Claude Code moves a session into it without asking |
| The board entry | A draft pull request with the label `akasha`, from the first minute. The open pull requests with the label are the board of the team |
| What the start shows | `akasha start` prints what to follow first, then the code as it is now: the guides of the team (`[guides]`), the rules for names of the languages of the scope, the usual word of nearby code for each kind of work (only where one word is usual; else the count as a fact, and no verdict), the public names of the areas of the scope (the map: names, signatures, and the first line of each description, in at most 12,000 characters), and the components that more than one area uses. The map is what the code is now, not a model |
| The records | `.docs/tasks/<task>/` in the branch while the task is in work (`[work] records`): `preview.html`, `research.md`, `plan.md`, `summary.md`. The landing moves them to `.docs/archive/YYYY/MM/YYYY-MM-DD-<task>/` (`[work] archive`), and they merge with the change, so each change keeps why it looks as it does. No work copy holds the archive of other tasks |
| The state on this computer | `.docs/state/tasks/<task>.json`. Git ignores it |
| The state for the other computers | A hidden block at the end of the body of the pull request |

## The approval of the person

The approval of the preview is the only decision of the person, so Akasha takes it only from the person. (An administrator also approves a change of the core, see "The core".)

- The agent engine runs `akasha preview <task>`. Akasha opens the preview and keeps its digest, and in Claude Code
  also the session that showed it.
- The person answers in the chat, in their own words and in any language. The hook of the prompt
  (`UserPromptSubmit`) keeps the message, and only that hook writes it: the agent engine cannot make one up.
- The agent engine reads the message. When it approves the preview as it is, without asking for a change, the agent
  engine runs `akasha approve <task>`. Akasha records the approval with the exact words of the person on this
  computer (`.docs/state`). The pull request and the squash commit name who approved and when, not the words. A message that asks for a change or asks a question is feedback, and the agent engine changes
  the preview.
- `akasha approve` refuses without a message of the person after the preview was shown, in the session that showed
  it, within a day. The hook also runs for prompts that the person did not type, for example the notice of a
  background task: Akasha does not keep those. Where the agent engine gives no session (Codex), the work copy of the
  session decides, and only when one preview waits.
- In a task without a screen, the person approves the plan in the same way, after its review: the approval holds
  the digest of `plan.md` (see "A task without a screen").
- A choice in a tool such as AskUserQuestion is not a message of the person: the AI asks for the approval in plain
  chat. The questions before the preview (who uses it, where, what) can use such a tool: they are not the approval.
- At the top of the preview, a box (`<section id="akasha-decisions">`) shows each question that the AI asked and the
  answer of the person. `akasha preview` refuses a preview without it. The digest covers the box, so the approval is
  also the record of the answers.
- The approval holds the digest of the preview that the person saw. When the preview changes after the approval, the
  task needs a new approval. The digest ignores the line ends, so an approval stays valid on another computer. A
  person who continues a task with `akasha resume` before its approval sees the preview again first.

## The preview specifies the change

The task builds the approved preview as it is, words included. So the preview is short, in the words of the screens
of the team (`[guides] preview` first), and drawn with the parts that the app already has. Below the look it has two
boxes. They are the specification, not the screen: the task never builds them.

| Box | One row for | Cells (`data-akasha-field`) |
|:--|:--|:--|
| The values `<section id="akasha-data">` | each value of the look that comes from data, marked `data-akasha-value="<key>"`, in the row `<tr data-akasha-key="<key>">` | `source` (the table and field, the API, the file), `formula`, `value` (its value now, read from the source), `check` (the query or command that gives it again) |
| The rules `<section id="akasha-rules">` | each behavior that the person can notice, in the row `<tr data-akasha-rule="<key>" data-akasha-from="person\|ai">` | `when`, `then`, `example` (one real case that a test checks as it is) |

`data-akasha-from` tells who decided a rule: `person` in an answer, or `ai` as a proposal. The person checks the
proposals; the approval makes them decisions as well.

```html
<p>Orders last month: <a href="#akasha-key-orders" data-akasha-value="orders">312</a></p>
<section id="akasha-data"><table>
  <tr id="akasha-key-orders" data-akasha-key="orders">
    <td>Orders last month</td>
    <td data-akasha-field="source">orders.id, orders.status</td>
    <td data-akasha-field="formula">orders of last month that are not cancelled</td>
    <td data-akasha-field="value">312 (2026-11-05 09:00)</td>
    <td data-akasha-field="check"><details><summary>SQL</summary>SELECT COUNT(*) FROM orders WHERE …</details></td>
  </tr>
</table></section>
<section id="akasha-rules"><table>
  <tr data-akasha-rule="empty" data-akasha-from="ai">
    <td>Proposed</td>
    <td data-akasha-field="when">a month without orders</td>
    <td data-akasha-field="then">0 and "No orders"</td>
    <td data-akasha-field="example">February 2026 → 0 · No orders</td>
  </tr>
</table></section>
```

| Akasha refuses | When |
|:--|:--|
| `akasha preview` | A preview of a full task without a rule, a rule without its three cells or without `data-akasha-from`, or a marked value without its row and its four cells |
| `akasha preview` | A task that plans a file of `[preview] data`, with a preview that marks no value |
| `akasha check` (`data`) | A change of a file of `[preview] data`, while the preview defines no value |

A quick task and an agent task have no such boxes: the preview of a quick task is the change itself, and an agent
task has no preview. Whether a source is real and a formula is right, the reviewer judges (R3, R5), and the person
can run the check again.

## The review of the plan

Another AI reviews the plan, in place of a person who reads it.

- The agent engine writes `research.md` and `plan.md`, and asks the akasha-reviewer agent for a review, with the plan
  digest from `akasha status`.
- This AI reads the preview, the plan, the code, and the rules of the team (`[guides]`). It judges ten written items,
  one row each with its evidence, and ends its answer with `AKASHA-REVIEW: <task> <plan digest> PASS` or `CHANGES`.
- The hook at the end of a subagent (`SubagentStop`) reads the mark and records it for that version of the plan. A
  change of the plan after a pass needs a new review. In Claude Code only the akasha-reviewer agent counts: a mark in
  the answer of another subagent does nothing.
- A PASS mark counts only when each item has a row that is PASS, or N/A where it may be. Else Akasha records CHANGES
  and the next step tells why. The whole answer goes into `review.md` in the records, and the pull request shows the
  verdict of the items, so each change keeps why its plan passed.
- A review after a repair of the plan does not judge each item again. Akasha keeps the rows of the last review of the
  reviewer and the plan that it read. `akasha status <task> --review` names the items that did not pass and shows the
  change of `plan.md` since then. The reviewer judges those items again, and each item whose part of the plan changed,
  and answers `KEPT` for each other item; any doubt means that it judges the item again. Akasha replaces a KEPT row
  with the row of the last review only when that row was PASS or N/A, else the PASS mark does not count. So
  `review.md` still has a row for each item (a kept row tells its round), and the verdict still holds the digest of
  the current plan. A quick task keeps nothing.
- The verdict holds one digest of each file that the review read: `plan.md` and `research.md`, with `preview.html`
  (a full task) or `request.md` (an agent task). A change of one of them needs a new review, also a typo: a preview
  that the person approved again, or a research that changed, does not keep an old PASS.
- A new public name that the repository has already needs an answer (the check `consistency` of `akasha check`
  and of the server): the same body under another name (Python), the same name in another file of the same area,
  or the same name as code that other areas use. The AI uses the existing code, or adds one row to the table
  `## Public changes` of `plan.md` (`different`, `wraps`, or `replaces`, the `path::name`, and the reason) and asks
  the reviewer again, who judges the reason (R10). A quick task has no plan: it uses the existing code, or
  `akasha upgrade` makes it a full task. All else is advice in `note —` lines and never stops a task: the same
  name in another area, a new public function of shared code without a description, and a name whose first word
  differs from the usual word of nearby code (a question, with the count from the code before the change).
- Akasha writes the frame of each record when the AI needs it: `preview.html` at the start, `research.md` and
  `plan.md` at the approval (at the start for a task without a preview), `impact.md` for a quick task. Each form
  tells how to fill it. Its first line is a mark, and a file that still has it counts as not written.
- A task belongs to the session of the agent engine that works on it. The start notice of another session names
  the task without a next step, and the guard stops its edits of that work copy. `akasha status <task> --resume`
  moves the task to the session that runs it, after the person asked for it; a preview that the other session
  showed is shown again there. A session after `/clear` is another session. An old activity never moves a task
  by itself. A subagent has the session of its main agent.
- In Claude Code the steps of a task run in agents of their own (akasha-preview, akasha-planner, akasha-builder,
  akasha-lander), each in a new context. The main session talks with the person, takes the approvals, and chooses
  the next step from `akasha status <task> --brief`. Only a message that the person types approves: a report of
  a subagent arrives as a prompt too, and Akasha never keeps it as the words of the person.
- The evidence is in the records, so the server reads it: `akasha approve` writes `approval.json` (what the person
  approved by its digest, who, and when; never their words), and `review.md` holds the verdict. The check `evidence`
  of the server fails a pull request that changes product files without a task, without them, or with evidence of
  an older version. It stops evidence that is missing or old; it does not prove who the person was. The approval
  of the result of an agent task is not in the records: the landing and the watch examine it.

| Item | It passes when |
|:--|:--|
| R1 Preview | Each rule of the preview has a step, each value from data is defined, no step builds what the person did not see, and no step builds the boxes or marks of the preview into the screen (an agent task: what `request.md` asks, and nothing more) |
| R2 Exact | Each step names the exact file and the change: no "TBD", "later", or "as above" |
| R3 Real | Each file, function, table, and caller that the plan names is in the code as the plan tells, and each source of the values is real and gives the value by its formula |
| R4 Reach | The plan names each other feature, table, API, and caller that the change touches, and keeps each one working |
| R5 Tests | A test for each example of the rules and each value, with the expected values of the preview. N/A only for a change without a behavior, for example a text |
| R6 Undo | When a revert of the squash commit does not undo the change (a database, data, a setting of a server, an outside service, a notice that was sent), the plan tells the order to undo it. N/A when a revert is enough |
| R7 Rules | The plan follows the rules of the team (`[guides] plan`, `[guides] review`) |
| R8 Decisions | The plan keeps each decision of the box at the top of the preview, each rule, and each definition of a value, also the rules that the AI proposed (an agent task: the cause — the code and the data confirm it, and the plan repairs it, not only the symptom) |
| R9 Core | When code that other areas use already does what the task needs, the plan uses it or extends it, and does not copy it. An existing line there changes only when the task needs it, with the reason, and each caller keeps working. N/A when the plan changes no such code |
| R10 Reuse | The plan uses the code that exists: for each new function, class, component, or query, `research.md` names what the search found, and the plan calls or extends that code, or tells why it cannot. To extend is to serve one more case of the same responsibility. Each new name tells what the code does. N/A when the plan makes no new code |

An item fails when the result, built as the plan says, would be wrong, would break a feature, or would miss a
behavior, or when the plan alone is not enough to build it. A point that does not change the result (a name, a
sentence, a better way) is a note, and fails nothing. A quick task has three items in place of these: Q1 Title (it
does what the title says, and nothing more), Q2 Reach (it reaches no other screen), and Q3 Safe (it breaks nothing).
- Only where the agent engine has no akasha-reviewer agent (Codex), the agent engine reviews the plan itself and runs
  `akasha review <task> --verdict pass`. The pull request tells that it was a self-review. Akasha refuses it in
  Claude Code, and a self-review never replaces a CHANGES of the akasha-reviewer agent for the same plan.

## A quick task

A typo or one setting needs no preview of the result and no plan. A quick task (`akasha start --quick`) skips them,
and keeps the review of another AI (not for a change of only text), the approval of the person, the checks, and the
landing.

| Part | How it works |
|:--|:--|
| What is quick | Akasha decides from what the change touches, not from its size. A quick change only changes existing files: it adds and deletes no file, so a new screen never comes in without a preview. No changed file is a core file (`[core]`): one line of a button that many screens use is not quick, also a new line. It touches no file that only an administrator changes, and no file of `[preview] data`. A file other than code and text matches `[quick] paths` |
| The same for each person | The administrators and the people of `[team] own_procedure` are free of the core approval, not of these rules: when they need more, they make a full task |
| The order | The AI makes the change, then writes `impact.md` in the records: each changed file, which screens use it, and why no other screen changes |
| The review | The akasha-reviewer agent reviews the change with `impact.md`, and finds the users that an import does not show (a setting key, a CSS class, a text key). Its mark holds the digest of the change and of `impact.md`. A change of only text for people (`*.md`, `*.txt`, `*.rst`, `*.adoc`) needs no review: no code reads it, and the person reads all of it in the preview. `impact.md` and the approval of the person are enough |
| The approval | `akasha preview` makes the preview from the change itself, and the person approves it in the chat as for each task. The approval holds the digest of the change |
| A later change | A change of the code after the review or the approval needs both again. The landing stops until they hold for the current change |
| Not quick | `akasha check` fails the check `quick`, and the landing stops. `akasha upgrade <task>` makes it a full task: the change stays, and the person approves a preview first |
| On GitHub | The server check runs the same rules for each pull request whose records have `impact.md`, and fails the check `quick` when the change is not a quick change. The check of Akasha runs them, also beside the own CI of a team (`[ci] required`). The watch asks for a passed review in the same way as `akasha status`: for each quick task, except one that changed only text for people |

## An agent task

An agent account (`[team] agents`) has no person in its session. A program, the relay, runs the session: it gives the
request of a person as a prompt, for example the diagnosis of a failed job and what to change, and it sends the answers
of the session to that person. The request decides what to make, so an agent task has no preview. The person decides
once, at the end, on the result.

| Part | How it works |
|:--|:--|
| Who | The GitHub name decides. Each task of an agent account is an agent task; a person cannot make one, and an agent account makes no other kind |
| The request | The hook of the prompt keeps each prompt of an agent session. `akasha start` writes the last prompt of the session, of the last ten minutes, into `request.md` in the records, word for word. The agent engine cannot make one up |
| The plan | As for each task: research, plan, and the akasha-reviewer agent, which reads `request.md` in place of a preview. No code changes before the review passes |
| The summary | `summary.md` tells the problem, the cause, what changed, what other areas it reaches, and how to undo it when a revert is not enough |
| The landing | When the checks of GitHub passed and the branch is up to date, `akasha land` stops with ASK (exit code 4) and does not merge. Where GitHub merges with its auto-merge, Akasha turns it on only after the approval |
| The result | `akasha result <task>` gives the text for the person: the summary, a link to the change between two fixed commits, and the changed files. It writes nothing into the work copy, so the checks do not run again |
| The approval | The answer of the person is the next prompt. When it approves the result, `akasha approve <task>` records it with the digest of the change and of `summary.md`. The relay can name the person on the first line: `[akasha-from: <name>]` |
| A later change | A change of the code or of `summary.md` after the approval needs a new one. A merge of the default branch keeps it: the change starts where the task meets the default branch |
| The rules | As for a teammate: the locked files and the core approval of an administrator hold |
| On GitHub | The watch reports an agent task of a person, a task of an agent account that is not an agent task, and an agent task without an approved result |

Akasha trusts the relay to give only the words of a person as prompts. The relay keeps the GitHub key and the last
word on the merge; the hooks keep a cooperative agent engine on the procedure.

## A task without a screen

A change of data, a batch job, an API, a rule, the speed, or the docs has no screen to show in a preview. For an
administrator, the AI works in developer mode: it asks technical questions, discusses the approach, and shows
`research.md` and `plan.md`. The administrator approves the plan in place of a preview. A teammate approves a preview,
as before.

| Part | How it works |
|:--|:--|
| Who | Only an administrator (`[team] admins`). The session start notice tells the AI that the account is an administrator, and the akasha-build skill switches to developer mode |
| What has no screen | `[preview] screens` names the files that make a screen. `akasha start --no-screen` refuses a start without `--scope`, a scope that holds one of them, a team without `[preview] screens`, and `--quick` with it |
| The order | The research, the plan, the review of the akasha-reviewer agent until PASS, then the approval of the plan by the person, then the build |
| The plan | The specification: at its top each question and the answer of the person, then each value from data with its source, formula, value now, and check, and each behavior with an example. The reviewer judges R1 (scope), R5 (tests), and R8 (decisions) against it |
| The approval | `akasha preview <task>` refuses a plan that did not pass the review, and records that the person sees this version. The person approves it in the chat, and `akasha approve <task>` records the approval with the digest of `plan.md` |
| A later change | A change of the plan after the approval needs a new review and a new approval. Akasha stops the edits of the code, the next step, and the landing until both hold for the current plan |
| The check `screen` | `akasha check` fails it when the change touches a file of `[preview] screens`. The check `data` does not run: the plan defines the values, and the reviewer judges them |
| On GitHub | The server check (`akasha check --ci`) runs the same rule for each pull request whose records hold `plan.md` without `preview.html`, `request.md`, or `impact.md`. The watch reports such a task of a person who is not an administrator, without an approved plan, or with a change of a screen file |

## What Akasha stops

| Before | Akasha stops | Why |
|:--|:--|:--|
| An edit | A change of the repository in the main checkout, or in a git worktree that is not a task, after the setup merged | Each change is a task, in its own work copy |
| An edit | A change of the code of a task before the approval and the passed review (a task without a screen: the passed review, then the approval of that plan) | The person decides first, and the plan is right first |
| A preview | A preview of a full task without its rules, or with a value from data that it does not define (see "The preview specifies the change") | The person approves what to make, with a way to check it |
| An edit | A change of `.env` and of `.docs/state` | Secret values, and the records of Akasha |
| An edit | In a teammate's task, a change of `akasha.toml`, `.github/`, CODEOWNERS, or a path of `[risk]` | The administrators maintain them. The AI asks with `akasha help`, and the check `admin_only` also fails on such a change |
| A command | A force push, a push to the default branch (also a plain `git push` on it), a delete of the default branch | They go around the pull request, or cannot be undone |
| A command | `git worktree add` | Akasha makes the work copy of each task, and of each part of a task (`akasha split`) |
| A command | `gh pr merge` and an approval of a pull request by the agent engine | Akasha lands each task, and needs no approval of a pull request |
| A command | A recursive delete outside the project | It deletes what Akasha cannot restore |
| After an edit | A secret key in the file | It must not go into git |

The hooks examine the repository that a tool acts on, not only the folder of the session: a session that started in
another folder meets the same rules when it edits the repository or runs `git -C <repository>`.

The people of `[team] own_procedure` keep the own procedure of the repository: Akasha does not stop their work outside
its tasks (their own work copies, edits in the main checkout, their merges). For everyone else, Akasha's procedure
comes first, and the session start and each prompt say so. The rules on pushes, force pushes, `.env`, and
`.docs/state` hold for everyone.

Before a start, `akasha board --scope <patterns>` names each open task that plans or already changes the same files,
and the AI reads what it changes before it plans. Nobody waits, and the person decides nothing more. After an edit,
Akasha also tells the agent engine when another open task plans or changes the same file. It does not stop the work:
each task keeps its own pull request, and the task that lands later takes the earlier change.

Where no Python 3.11 or higher is on the computer, the hooks cannot run. Then the session start and each prompt tell
it to the agent engine, and each edit in a repository that uses Akasha stops, so that no step goes around Akasha
without notice.

> **CAUTION:** The hooks keep a cooperative agent engine on the procedure. They are not a sandbox.

## The core

A teammate's task can add anything. Only one kind of change waits for an administrator: a change or a delete of
existing lines of a core file. Other screens use that code, and nobody of them saw the change.

| Part | How it works |
|:--|:--|
| A core file | A file that `[core] used_by` or more other areas import (the default is 2), or a file of `[core] paths`. An area is a folder of `[core] areas`, else the first two folders of the path. Imports by tests do not count |
| Free | A new file, and new lines in a core file. `git diff --numstat` decides: a file without deleted lines is free |
| The edit | Akasha never stops it. `akasha start` names the core files of the scope, and `akasha check` names the core files whose existing lines changed, so that the AI uses that code and extends it, and does not copy it into a new function |
| The landing | Waits with BLOCKED until an administrator approves the pull request on GitHub (Review changes → Approve). Akasha asks the administrators once for each version of the work. A later change of the core files needs a new approval, and a later "Request changes" of the same administrator takes it back |
| Who is free of it | The administrators and the people of `[team] own_procedure` |

Akasha finds the users of a file in the imports of Python, JavaScript, and TypeScript. It does not see a call of an
API by its address, a table name in the text of SQL, or code in another language: for those, list the files in
`[core] paths`. The akasha-reviewer agent and the check after the deployment (`[deploy] verify`) also guard them.

## The checks

`akasha check <task>` adds the new files to the index of git, so that a check that lists the files with git sees them,
and runs the required checks of `[checks]` in the work copy. When each check passes, Akasha saves the work as a commit
and pushes it. A file that a check makes, for example `__pycache__`, never goes into a commit: Akasha tells the agent
engine to add its pattern to `.gitignore`.

The same rules run on GitHub: the check of Akasha (`.github/workflows/akasha.yml`) runs `[checks]` with the rules of
the default branch, or the CI of the team runs its own checks (`[ci] required`).

## The landing

`akasha land <task> --wait 540` needs the approval, the passed review, passed checks on the current work, and
`summary.md`. Then it merges the latest default branch into the task, makes the pull request ready, pushes it, and
follows the pull request:

| What Akasha sees | What it does |
|:--|:--|
| A required check runs | Waits. A check that a draft skipped is not a pass: one run must really run and pass. When a check ran more than once on the head, the latest run that ended decides. A run that passed while the pull request was a draft counts: a second run of the same commit, which marking it ready started, does not make the landing wait (see `[ci]` in [team config](team-config.md)) |
| A required check failed | Stops with FAILED. The agent engine repairs, checks, and lands again |
| A required check was cancelled | Starts it again once. Cancelled again: stops with FAILED and asks for an administrator |
| A required check never ran, or waits for a runner | Waits; at the end of the wait it names the check, so that an administrator can correct `[ci] required` or the runner |
| The branch is behind the default branch | When the task is the first of the line of the landings, asks GitHub to bring it up to date. The checks run again. When GitHub does not answer, it does not merge |
| Another task came to the landing first | Waits with WAITING behind it, and does not come up to date: the task that came first merges first, so the checks of each task run again once, not at each merge of another task. Nothing wakes a task that waits: when the command ends, `akasha land <task> --wait 540` again goes on from the same place of the line |
| The first task of the line cannot go on | The landing that waits behind it goes on without it: a failed check, a conflict, a wait for a person, or no step for three minutes after its turn came. A comment on that pull request tells it (and the label `akasha-skipped`), and its auto-merge goes off. Its next `akasha land` puts it at the end of the line |
| A conflict | Stops with CONFLICT. The next landing brings the latest default branch into the work copy and names the files |
| The work copy changed during the landing | Stops with BLOCKED: the change needs its checks first |
| The task changes existing lines of the core, and no administrator approved it | Stops with BLOCKED, and asks the administrators on the pull request once for each version of the work. The AI tells the person and lands again later |
| A rule of the repository on GitHub asks for a review | Stops with BLOCKED at the end of the wait: Akasha asks for no review, except the approval of a core change, so an administrator removes the rule |
| Everything passed | Merges the pull request as one squash commit, with the summary as its body |
| `[deploy] workflow` is set | After the merge, waits for the deployment and says DEPLOYED, DEPLOY_FAILED, or DEPLOYING, or VERIFY_FAILED with `verify` (next row) |
| `[deploy] verify` is set, and the deployment passed | Runs the command at the top of the main checkout. It passes: DEPLOYED. It fails: VERIFY_FAILED, and the AI asks an administrator and offers to undo the change |

No person reviews the pull request, except a change of existing lines of the core: an administrator approves it (see
"The core"). The preview approval of the person, the plan check of the second AI, and the checks of the team guard
each task. The parts that only an administrator changes never reach the landing from a teammate's
task: the guard stops the edit, and the check `admin_only` fails.

Who merges depends on GitHub. Before each landing, Akasha asks GitHub whether its protection of the default branch
requires each check of the team:

| Repository | Who merges |
|:--|:--|
| The protection requires the checks of the team (public, or private on GitHub Pro, Team, or Enterprise, after `akasha setup --apply`) | GitHub, with its auto-merge and branch protection, as the person who landed |
| No protection, or one without these checks (a private repository on GitHub Free, or before `--apply`) | Akasha, on the computer of the person, after the same examination. A watch workflow reports each change that went around the rules |

In both cases the merge comes from the account of the person, so the workflows after a merge start, for example a
deployment. Where Akasha merges, a merge happens only while `akasha land` runs: a change that waits for its checks
merges when the AI of the person who holds it lands it again, in the same session or when the person asks it to
continue in a later one.

Akasha never removes work that did not reach GitHub: when a pull request merged or closed, or another person took the
task, while the work copy has an edit or a commit that GitHub lacks, Akasha keeps the work copy and says so. A work
copy that the session works in stays until `akasha tidy`. A task that waits for its deployment stays until the landing
sees the end of the deployment, also across a new session.

## Many people at the same time

Each person, from any team, holds their own tasks. Any number of tasks can be open at once.

| Situation | What happens |
|:--|:--|
| A new task plans files that open tasks already plan | `akasha start` and the board show those tasks and their holders |
| Tasks change the same file | Before the start, the AI reads what the other task changes. The hook tells each task after the edit. Each keeps its own pull request: a task that lands later takes the earlier changes, or stops with CONFLICT, and its AI keeps the changes of both sides, checks again, and lands |
| Several tasks are ready at once | They merge one by one, in the order in which they came to the landing. Only the first one comes up to date with the default branch; the others wait for their turn, so no merge starts the checks of each other task again. The line is no lock: each computer reads the pull requests and counts in the same way |
| A person stops, and another person or computer continues | `akasha handoff <task>` saves the work and frees the task. `akasha resume <task>` continues it anywhere |
| Another person took a task with `akasha resume --force` | The old computer stops pushing, landing, and closing it, and removes its copy at the next session start |
| A task name is already in use | The start refuses the name: on the board, on the server, and in the records of an earlier task |
| A person is stuck | `akasha help <task> "<text>"` asks the administrators on the pull request |

## Workers at the same time: the parts of a task

A large task can go to several workers (AI agents) at the same time, for example one for the server and one for the
screen. The person approves one preview and the reviewer passes one plan for the whole task; the parts share them.

| Part | How it works |
|:--|:--|
| When | After the approval and the review: `akasha split <task> <part> --scope <patterns>` refuses a task that is not ready to build, and a quick task |
| The work copy | `<work folder>/<task>--<part>`, on the local branch `<branch of the task>--<part>` from the work of the task so far. It never goes to GitHub and never shows on the board |
| The files | Each part has a scope, and no two parts have the same files: a scope that holds a file or a pattern of another part is refused. An edit outside the scope stops, so that the parts do not conflict. The records of the task change only in its own work copy |
| The rules | The rules of the task hold in each part: the files of the administrators, and the build only after the approval and the review |
| The join | `akasha join <task>` saves each part, merges it into the work copy of the task, and removes it. A conflict with the work copy of the task stops the join with the files, and the work copy stays as before that part |
| The landing | Waits until each part joined, then runs as for each task: one pull request |
| Cancel and hand off | `akasha cancel` removes the parts; a part with work that did not join needs `--force`. `akasha handoff` needs the join first, because the parts are only on this computer |

## Where Akasha keeps its data

| Data | Where | In git |
|:--|:--|:--|
| Team rules | `akasha.toml` | Yes |
| Records of a task in work | `.docs/tasks/<task>/` | In the branch of the task only |
| Records of each merged task | `.docs/archive/YYYY/MM/YYYY-MM-DD-<task>/` | Yes, with the change |
| The board | Open pull requests with the label `akasha` | GitHub |
| Task state | `.docs/state/` on each computer, and the block in the pull request | No |
| Problems for the retro | `.docs/state/trace.jsonl`, and the stats in the merged pull requests | No |
