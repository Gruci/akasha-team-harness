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
| The records | `.akasha/tasks/<task>/` in the branch: `preview.html`, `research.md`, `plan.md`, `summary.md`. They merge with the change, so each change keeps why it looks as it does |
| The state on this computer | `.akasha/state/tasks/<task>.json`. Git ignores it |
| The state for the other computers | A hidden block at the end of the body of the pull request |

## The approval of the person

The approval is the only decision of a person, so Akasha takes it only from the person.

- The agent engine runs `akasha preview <task>`. Akasha opens the preview and keeps its digest.
- The person answers in the chat. The hook of the prompt (`UserPromptSubmit`) reads the message of the person. A short
  message that approves, for example "승인", "좋아 진행해", or "ok, go ahead", records the approval. A message that asks
  for a change, for example "승인 말고 버튼 색 바꿔", is feedback, and the agent engine changes the preview.
- The agent engine cannot make an approval: Claude Code and Codex run that hook only for what the person sends.
- The approval holds the digest of the preview that the person saw. When the preview changes after the approval, the
  task needs a new approval. The digest ignores the line ends, so an approval stays valid on another computer.

## The review of the plan

Another AI reviews the plan, in place of a person who reads it.

- The agent engine writes `research.md` and `plan.md`, and asks the akasha-reviewer agent for a review, with the plan
  digest from `akasha status`.
- The reviewer reads the preview, the plan, the code, and the rules of the team (`[guides]`). It ends its answer with
  `AKASHA-REVIEW: <task> <plan digest> PASS` or `CHANGES`.
- The hook at the end of a subagent (`SubagentStop`) reads the mark and records it for that version of the plan. A
  change of the plan after a pass needs a new review.
- Without a reviewer agent, the agent engine reviews the plan itself and runs `akasha review <task> --verdict pass`.
  The pull request tells that it was a self-review.

## What Akasha stops

| Before | Akasha stops | Why |
|:--|:--|:--|
| An edit | A change of the repository in the main checkout, after the setup merged | Each change is a task, in its own work copy |
| An edit | A change of the code of a task before the approval and the passed review | The person decides first, and the plan is right first |
| An edit | A change of `.env` and of `.akasha/state` | Secret values, and the records of Akasha |
| A command | A force push, a push to the default branch, a delete of the default branch | They go around the pull request, or cannot be undone |
| A command | `gh pr merge` and an approval of a pull request by the agent engine | Akasha lands each task, and a reviewer approves in person |
| A command | A recursive delete outside the project | It deletes what Akasha cannot restore |
| After an edit | A secret key in the file | It must not go into git |

After an edit, Akasha also tells the agent engine when another open task plans or changes the same file. It does not
stop the work: the task that lands later takes the earlier change.

> **CAUTION:** The hooks keep a cooperative agent engine on the procedure. They are not a sandbox.

## The checks

`akasha check <task>` runs the required checks of `[checks]` in the work copy. When each check passes, Akasha saves
the work as a commit and pushes it. A file that a check makes, for example `__pycache__`, never goes into a commit:
Akasha tells the agent engine to add its pattern to `.gitignore`.

The same rules run on GitHub: the check of Akasha (`.github/workflows/akasha.yml`) runs `[checks]` with the rules of
the default branch, or the CI of the team runs its own checks (`[ci] required`).

## The landing

`akasha land <task> --wait 540` needs the approval, the passed review, passed checks on the current work, and
`summary.md`. Then it merges the latest default branch into the task, pushes it, makes the pull request ready, asks the
reviewers of a risky path for a review, and follows the pull request:

| What Akasha sees | What it does |
|:--|:--|
| A required check runs | Waits. A check that a draft skipped is not a pass: one run must really run and pass |
| A required check failed | Stops with FAILED. The agent engine repairs, checks, and lands again |
| The branch is behind the default branch | Asks GitHub to bring it up to date. The checks run again |
| A conflict | Stops with CONFLICT. The agent engine merges and repairs in the work copy |
| A risky path without the review of a reviewer | Stops with REVIEW |
| Everything passed | Merges the pull request as one squash commit, with the summary as its body |

Who merges depends on the GitHub plan:

| Repository | `[server] rules` | Who merges |
|:--|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | `github` | GitHub, with its auto-merge and branch protection, as the person who landed |
| Private on GitHub Free | `akasha` | Akasha, on the computer of the person, after the same examination. A watch workflow reports each change that went around the rules |

In both cases the merge comes from the account of the person, so the workflows after a merge start, for example a
deployment.

## Many people at the same time

| Situation | What happens |
|:--|:--|
| Two people plan the same files | `akasha start` and the board show the other task and its holder |
| Two people change the same file | The hook tells each of them after the edit. The task that lands later takes the earlier change, or stops with CONFLICT |
| Two tasks land at the same time | The first merges. The second is behind: Akasha brings it up to date, and it merges after its checks pass again |
| A person stops, and another person or computer continues | `akasha handoff <task>` saves the work and frees the task. `akasha resume <task>` continues it anywhere |
| A person is stuck | `akasha help <task> "<text>"` asks the administrators on the pull request |

## Where Akasha keeps its data

| Data | Where | In git |
|:--|:--|:--|
| Team rules | `akasha.toml` | Yes |
| Records of each task | `.akasha/tasks/<task>/` | Yes, with the change |
| The board | Open pull requests with the label `akasha` | GitHub |
| Task state | `.akasha/state/` on each computer, and the block in the pull request | No |
| Problems for the retro | `.akasha/state/trace.jsonl`, and the stats in the merged pull requests | No |
