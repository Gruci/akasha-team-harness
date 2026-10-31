# How it works

## The principle

The person who asks for a change decides what to make. They decide it once, at the start, on a preview that they can
see: a mockup of the screen, or a diagram of the flow and the data. The AI does everything after that, and another AI
checks its plan in place of a person. Machines check the result. GitHub merges it.

| Step | Who | What happens |
|:--|:--|:--|
| 1. Request | The person | Says what they want, in their own words. The AI asks until it is clear |
| 2. Preview | The person | Looks at the preview in the browser. Says "승인" (approve), or what to change |
| 3. Plan | The AI and the reviewer | The AI writes the research and the plan. The akasha-reviewer agent reviews the plan until it passes |
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
- The person answers in the chat. The hook of the prompt (`UserPromptSubmit`) reads the message. Only a whole message
  from a short closed list approves: "승인", "네", "넵", "좋아요", "진행해 주세요", "이대로 진행", "ok", "go ahead",
  "LGTM", and a few more, with or without spaces, marks, and a polite end. Each other message is feedback, for example
  "좋아요, 표는 아래로" or "아직 승인 안 해요", and the agent engine changes the preview.
- The hook also runs for prompts that the person did not type: the notice of a background task, a scheduled prompt,
  a prompt of `/loop`. Such a prompt does not approve, because it is not a whole approval word. The approval also
  counts only in the session that showed the preview, and only within a day after it showed it. Where the agent
  engine gives no session (Codex), the work copy of the session decides, and only when one preview waits.
- A choice in a tool such as AskUserQuestion is not recorded: the AI asks in plain chat.
- The approval holds the digest of the preview that the person saw. When the preview changes after the approval, the
  task needs a new approval. The digest ignores the line ends, so an approval stays valid on another computer. A
  person who continues a task with `akasha resume` before its approval sees the preview again first.

## The review of the plan

Another AI reviews the plan, in place of a person who reads it.

- The agent engine writes `research.md` and `plan.md`, and asks the akasha-reviewer agent for a review, with the plan
  digest from `akasha status`.
- The reviewer reads the preview, the plan, the code, and the rules of the team (`[guides]`). It ends its answer with
  `AKASHA-REVIEW: <task> <plan digest> PASS` or `CHANGES`.
- The hook at the end of a subagent (`SubagentStop`) reads the mark and records it for that version of the plan. A
  change of the plan after a pass needs a new review. In Claude Code only the akasha-reviewer agent counts: a mark in
  the answer of another subagent does nothing.
- Only where the agent engine has no reviewer agent (Codex), the agent engine reviews the plan itself and runs
  `akasha review <task> --verdict pass`. The pull request tells that it was a self-review. Akasha refuses it in
  Claude Code, and a self-review never replaces a CHANGES of the reviewer for the same plan.

## What Akasha stops

| Before | Akasha stops | Why |
|:--|:--|:--|
| An edit | A change of the repository in the main checkout, or in a git worktree that is not a task, after the setup merged | Each change is a task, in its own work copy |
| An edit | A change of the code of a task before the approval and the passed review | The person decides first, and the plan is right first |
| An edit | A change of `.env` and of `.akasha/state` | Secret values, and the records of Akasha |
| A command | A force push, a push to the default branch (also a plain `git push` on it), a delete of the default branch | They go around the pull request, or cannot be undone |
| A command | `git worktree add` | Akasha makes the work copy of each task |
| A command | `gh pr merge` and an approval of a pull request by the agent engine | Akasha lands each task, and a reviewer approves in person |
| A command | A recursive delete outside the project | It deletes what Akasha cannot restore |
| After an edit | A secret key in the file | It must not go into git |

The hooks examine the repository that a tool acts on, not only the folder of the session: a session that started in
another folder meets the same rules when it edits the repository or runs `git -C <repository>`.

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

A change of a risky path needs the approval of a reviewer, and a change of `akasha.toml`, `.github/`, or CODEOWNERS
the approval of an administrator. The person who made the change does not count.

Who merges depends on GitHub. Before each landing, Akasha asks GitHub whether it protects the default branch:

| Repository | Who merges |
|:--|:--|
| GitHub protects the default branch (public, or private on GitHub Pro, Team, or Enterprise, after `akasha setup --apply`) | GitHub, with its auto-merge and branch protection, as the person who landed |
| GitHub does not protect it (a private repository on GitHub Free, or before `--apply`) | Akasha, on the computer of the person, after the same examination. A watch workflow reports each change that went around the rules |

In both cases the merge comes from the account of the person, so the workflows after a merge start, for example a
deployment. Where Akasha merges, a merge happens only while `akasha land` runs: a change that waits for a review
merges when the AI of the person who holds it lands it again after the review, in the same session or when the person
says "이어서 해 줘" in a later one.

When the pull request merged with work that the work copy has and GitHub lacks, Akasha keeps the work copy and says
so. A work copy that the session works in stays until `akasha tidy`.

## Many people at the same time

| Situation | What happens |
|:--|:--|
| Two people plan the same files | `akasha start` and the board show the other task and its holder |
| Two people change the same file | The hook tells each of them after the edit. The task that lands later takes the earlier change, or stops with CONFLICT |
| Two tasks land at the same time | The first merges. The second is behind: Akasha brings it up to date, and it merges after its checks pass again |
| A person stops, and another person or computer continues | `akasha handoff <task>` saves the work and frees the task. `akasha resume <task>` continues it anywhere |
| Another person took a task with `akasha resume --force` | The old computer stops pushing, landing, and closing it, and removes its copy at the next session start |
| Two teams pick the same name for a task | The second start refuses the name: on the board, on the server, and in the records of an earlier task |
| A person is stuck | `akasha help <task> "<text>"` asks the administrators on the pull request |

## Where Akasha keeps its data

| Data | Where | In git |
|:--|:--|:--|
| Team rules | `akasha.toml` | Yes |
| Records of each task | `.akasha/tasks/<task>/` | Yes, with the change |
| The board | Open pull requests with the label `akasha` | GitHub |
| Task state | `.akasha/state/` on each computer, and the block in the pull request | No |
| Problems for the retro | `.akasha/state/trace.jsonl`, and the stats in the merged pull requests | No |
