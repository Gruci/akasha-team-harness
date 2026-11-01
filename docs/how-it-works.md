# How it works

## The principle

The person who asks for a change decides what to make. They decide it once, at the start, on a preview that they can
see: a mockup of the screen, or a diagram of the flow and the data. The AI does everything after that, and another AI
checks its plan in place of a person. Machines check the result. GitHub merges it.

A team has two roles. A teammate asks for changes and approves their previews. An administrator sets up the team,
reviews a change of the few risky parts, and helps when an AI is stuck.

| Step | Who | What happens |
|:--|:--|:--|
| 1. Request | The person | Says what they want, in their own words. The AI asks until it is clear |
| 2. Preview | The person | Looks at the preview in the browser. Says "approve", or what to change |
| 3. Plan | The AI | The AI writes the research and the plan. A second AI (the akasha-reviewer agent) checks the plan until it passes |
| 4. Build | The AI | Changes the code in its own work copy, with a test for each behavior of the preview |
| 5. Check | The AI and the checks | Runs the checks of the team until they pass |
| 6. Land | The AI and GitHub | Opens the pull request for review, brings it up to date, and merges it when the checks pass on GitHub |

## One task

A task is one change of one person.

| Part | Where |
|:--|:--|
| The work copy | A git worktree in `.akasha/work/<task>`, on the branch `akasha/<task>` (`[work]` changes both) |
| The board entry | A draft pull request with the label `akasha`, from the first minute. The open pull requests with the label are the board of the team |
| The records | `.akasha/tasks/<task>/` in the branch (`[work] records` changes the folder): `preview.html`, `research.md`, `plan.md`, `summary.md`. They merge with the change, so each change keeps why it looks as it does |
| The state on this computer | `.akasha/state/tasks/<task>.json`. Git ignores it |
| The state for the other computers | A hidden block at the end of the body of the pull request |

## The approval of the person

The approval is the only decision of a person, so Akasha takes it only from the person.

- The agent engine runs `akasha preview <task>`. Akasha opens the preview and keeps its digest, and in Claude Code
  also the session that showed it.
- The person answers in the chat, in their own words and in any language. The hook of the prompt
  (`UserPromptSubmit`) keeps the message, and only that hook writes it: the agent engine cannot make one up.
- The agent engine reads the message. When it approves the preview as it is, without asking for a change, the agent
  engine runs `akasha approve <task>`. Akasha records the approval with the exact words of the person, and the pull
  request shows them. A message that asks for a change or asks a question is feedback, and the agent engine changes
  the preview.
- `akasha approve` refuses without a message of the person after the preview was shown, in the session that showed
  it, within a day. The hook also runs for prompts that the person did not type, for example the notice of a
  background task: Akasha does not keep those. Where the agent engine gives no session (Codex), the work copy of the
  session decides, and only when one preview waits.
- A choice in a tool such as AskUserQuestion is not a message of the person: the AI asks in plain chat.
- The approval holds the digest of the preview that the person saw. When the preview changes after the approval, the
  task needs a new approval. The digest ignores the line ends, so an approval stays valid on another computer. A
  person who continues a task with `akasha resume` before its approval sees the preview again first.

## The review of the plan

Another AI reviews the plan, in place of a person who reads it.

- The agent engine writes `research.md` and `plan.md`, and asks the akasha-reviewer agent for a review, with the plan
  digest from `akasha status`.
- This AI reads the preview, the plan, the code, and the rules of the team (`[guides]`). It ends its answer with
  `AKASHA-REVIEW: <task> <plan digest> PASS` or `CHANGES`.
- The hook at the end of a subagent (`SubagentStop`) reads the mark and records it for that version of the plan. A
  change of the plan after a pass needs a new review. In Claude Code only the akasha-reviewer agent counts: a mark in
  the answer of another subagent does nothing.
- Only where the agent engine has no akasha-reviewer agent (Codex), the agent engine reviews the plan itself and runs
  `akasha review <task> --verdict pass`. The pull request tells that it was a self-review. Akasha refuses it in
  Claude Code, and a self-review never replaces a CHANGES of the akasha-reviewer agent for the same plan.

## What Akasha stops

| Before | Akasha stops | Why |
|:--|:--|:--|
| An edit | A change of the repository in the main checkout, or in a git worktree that is not a task, after the setup merged | Each change is a task, in its own work copy |
| An edit | A change of the code of a task before the approval and the passed review | The person decides first, and the plan is right first |
| An edit | A change of `.env` and of `.akasha/state` | Secret values, and the records of Akasha |
| A command | A force push, a push to the default branch (also a plain `git push` on it), a delete of the default branch | They go around the pull request, or cannot be undone |
| A command | `git worktree add` | Akasha makes the work copy of each task |
| A command | `gh pr merge` and an approval of a pull request by the agent engine | Akasha lands each task, and an administrator approves in person |
| A command | A recursive delete outside the project | It deletes what Akasha cannot restore |
| After an edit | A secret key in the file | It must not go into git |

The hooks examine the repository that a tool acts on, not only the folder of the session: a session that started in
another folder meets the same rules when it edits the repository or runs `git -C <repository>`.

The people of `[team] own_procedure` keep the own procedure of the repository: Akasha does not stop their work outside
its tasks (their own work copies, edits in the main checkout, their merges). For everyone else, Akasha's procedure
comes first, and the session start and each prompt say so. The rules on pushes, force pushes, `.env`, and
`.akasha/state` hold for everyone.

After an edit, Akasha also tells the agent engine when another open task plans or changes the same file. It does not
stop the work: the task that lands later takes the earlier change.

Where no Python 3.11 or higher is on the computer, the hooks cannot run. Then the session start and each prompt tell
it to the agent engine, and each edit in a repository that uses Akasha stops, so that no step goes around Akasha
without notice.

> **CAUTION:** The hooks keep a cooperative agent engine on the procedure. They are not a sandbox.

## The checks

`akasha check <task>` adds the new files to the index of git, so that a check that lists the files with git sees them,
and runs the required checks of `[checks]` in the work copy. When each check passes, Akasha saves the work as a commit
and pushes it. A file that a check makes, for example `__pycache__`, never goes into a commit: Akasha tells the agent
engine to add its pattern to `.gitignore`.

The same rules run on GitHub: the check of Akasha (`.github/workflows/akasha.yml`) runs `[checks]` with the rules of
the default branch, or the CI of the team runs its own checks (`[ci] required`).

## The landing

`akasha land <task> --wait 540` needs the approval, the passed review, passed checks on the current work, and
`summary.md`. Then it merges the latest default branch into the task, makes the pull request ready, pushes it, asks
for the reviews that the change needs, and follows the pull request:

| What Akasha sees | What it does |
|:--|:--|
| A required check runs | Waits. A check that a draft skipped is not a pass: one run must really run and pass. When a check ran more than once on the head, the latest run decides, as on GitHub |
| A required check failed | Stops with FAILED. The agent engine repairs, checks, and lands again |
| A required check was cancelled | Starts it again once. Cancelled again: stops with FAILED and asks for an administrator |
| A required check never ran, or waits for a runner | Waits; at the end of the wait it names the check, so that an administrator can correct `[ci] required` or the runner |
| The branch is behind the default branch | Asks GitHub to bring it up to date. The checks run again. When GitHub does not answer, it does not merge |
| A conflict | Stops with CONFLICT. The next landing brings the latest default branch into the work copy and names the files |
| The work copy changed during the landing | Stops with BLOCKED: the change needs its checks first |
| A change that needs a review, without it | Waits until the end of the wait, then stops with REVIEW. A review that asks for changes stops at once |
| Everything passed | Merges the pull request as one squash commit, with the summary as its body |
| `[deploy] workflow` is set | After the merge, waits for the deployment and says DEPLOYED, DEPLOY_FAILED, or DEPLOYING |

A change of a risky path, or of the rules of the team (`akasha.toml`, `.github/`, CODEOWNERS, and the files of
`[guides]`, which each AI follows), needs the approval of an administrator. The person who made the change does not
count. An approval covers the version that the administrator saw: when a file of that kind changes after it, the
change needs a new review. Akasha asks the administrators at the first check that touches such a file, so that they
review while the work goes on.

Who merges depends on GitHub. Before each landing, Akasha asks GitHub whether its protection of the default branch
requires each check of the team:

| Repository | Who merges |
|:--|:--|
| The protection requires the checks of the team (public, or private on GitHub Pro, Team, or Enterprise, after `akasha setup --apply`) | GitHub, with its auto-merge and branch protection, as the person who landed |
| No protection, or one without these checks (a private repository on GitHub Free, or before `--apply`) | Akasha, on the computer of the person, after the same examination. A watch workflow reports each change that went around the rules |

In both cases the merge comes from the account of the person, so the workflows after a merge start, for example a
deployment. Where Akasha merges, a merge happens only while `akasha land` runs: a change that waits for a review
merges when the AI of the person who holds it lands it again after the review, in the same session or when the person
asks it to continue in a later one.

Akasha never removes work that did not reach GitHub: when a pull request merged or closed, or another person took the
task, while the work copy has an edit or a commit that GitHub lacks, Akasha keeps the work copy and says so. A work
copy that the session works in stays until `akasha tidy`. A task that waits for its deployment stays until the landing
sees the end of the deployment, also across a new session.

## Many people at the same time

Each person, from any team, holds their own tasks. Any number of tasks can be open at once.

| Situation | What happens |
|:--|:--|
| A new task plans files that open tasks already plan | `akasha start` and the board show those tasks and their holders |
| Tasks change the same file | The hook tells each of them after the edit. A task that lands later takes the earlier changes, or stops with CONFLICT |
| Several tasks are ready at once | They merge one by one. Each later one is behind: Akasha brings it up to date, and it merges after its checks pass again |
| A person stops, and another person or computer continues | `akasha handoff <task>` saves the work and frees the task. `akasha resume <task>` continues it anywhere |
| Another person took a task with `akasha resume --force` | The old computer stops pushing, landing, and closing it, and removes its copy at the next session start |
| A task name is already in use | The start refuses the name: on the board, on the server, and in the records of an earlier task |
| A person is stuck | `akasha help <task> "<text>"` asks the administrators on the pull request |

## Where Akasha keeps its data

| Data | Where | In git |
|:--|:--|:--|
| Team rules | `akasha.toml` | Yes |
| Records of each task | `.akasha/tasks/<task>/` | Yes, with the change |
| The board | Open pull requests with the label `akasha` | GitHub |
| Task state | `.akasha/state/` on each computer, and the block in the pull request | No |
| Problems for the retro | `.akasha/state/trace.jsonl`, and the stats in the merged pull requests | No |
