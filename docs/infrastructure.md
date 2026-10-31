# Infrastructure

The infrastructure manager keeps the GitHub settings of the repository the same as the team config. These settings are the third enforcement layer. They operate also when a person does not use Akasha.

## Server rules: GitHub first, Akasha's helpers second

GitHub's own branch protection and auto-merge come first. Akasha's helpers merge and undo only where the GitHub plan has none. In each repository, the helpers also bring the pull requests of the tasks up to date, because GitHub does not do it.

| Repository | `[server] rules` | Who enforces the rules |
|:--|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | `github` | GitHub: branch protection, the required check, code owners, and auto-merge |
| Private on GitHub Free | `akasha` | Akasha's helpers: `akasha-merge` and `akasha-watch` |

The setup tries GitHub's branch protection first. When GitHub refuses it because of the plan, the setup records `rules = "akasha"` in `akasha.toml`. When the plan changes, run the setup again. Then GitHub's rules take over.

The helpers are always installed. Before they merge or undo, they examine the default branch on GitHub. While GitHub protects it, they do not merge or undo. They still bring the pull requests up to date, and they tell the holder of a task when its check fails.

## What Akasha installs

| Item | Location | Function |
|:--|:--|:--|
| Required check `akasha` | `.github/workflows/akasha.yml` | Runs the required checks of the team on each pull request |
| Merge helper | `.github/workflows/akasha-merge.yml` | Brings a pull request with the label `akasha-merge` up to date, and tells about a failed check. Merges the pull request after the check passes, where GitHub has no auto-merge |
| Watch helper | `.github/workflows/akasha-watch.yml` | Undoes a change on the default branch that went around the check, where GitHub has no branch protection. With the GitHub app, it brings the pull requests up to date after each push |
| CODEOWNERS block | The CODEOWNERS file of the repository | Gives the team rules to the administrators, and each gate to its people |
| Pull request template | `.github/pull_request_template.md` | Gives the sections of the briefing to people who open a pull request by hand. Akasha keeps a template that the team already has |
| Branch protection | The GitHub settings of the default branch | Stops a merge without the required check, when the plan has it |
| Repository settings | The GitHub settings of the repository | Permit auto-merge and squash merges, and delete a merged branch |

## The required check

The check runs on each pull request and on each merge queue run. It runs on the machine of `[ci] runs-on` with the Python of `[ci] python` in `akasha.toml`, by default `ubuntu-latest` and Python 3.12. Its steps use bash, also on a Windows runner:

1. It installs Akasha. The repository variable `AKASHA_SOURCE` can name another source, for example a mirror or a fork. It installs Akasha again on each run, also when the machine has it: a runner of the team keeps its Python between runs.
2. It takes `akasha.toml` from the default branch.
3. It runs the `setup` command of the team.
4. It runs the required checks on the files that the pull request changes. A check with `only_when` runs only when the pull request changes a file that it examines, or a file of `run_all_when`. Akasha runs in the UTF-8 mode of Python, so that it can write each result also on a Windows runner.

The rules come from the default branch. Thus a pull request that makes the checks weaker cannot pass with its own rules.

Akasha makes `akasha.yml` from its template and `[ci]`. The examination of the server rules compares `akasha.yml` on the default branch with the file that the Akasha of this computer makes from `[ci]` on the default branch. It does the same for the two helpers. When a file is different, the handover of the task waits until an administrator sets up Akasha again.

The merge and watch helpers always run on `ubuntu-latest`, because they can write to the repository. [Team config](team-config.md) tells the keys of `[ci]` and what a Windows runner needs.

> **CAUTION:** In a public repository, a pull request from a fork runs its code in the required check. On a runner of the team, that code runs on a machine of the team. In this condition, Akasha shows a warning. `infra --apply` and `setup --approve-infra` show it for the team config in the checkout, when they write `akasha.yml`. `infra` and `setup` show it for the team config on the default branch. The warning does not stop a handover.

## GitHub branch protection and auto-merge

| Setting | Value |
|:--|:--|
| Required status check | `akasha` |
| The branch must be up to date before a merge | Yes |
| Approvals | None, except the code owners below |
| Code owner review | Required |
| Force push | Not permitted |
| Deletion of the default branch | Not permitted |
| Administrators can go around the rules | Yes |
| Auto-merge, squash merge, deletion of merged branches | On |

A pull request that changes no file with a code owner merges when the required check passes. Each merge is one squash commit with the briefing as its body.

The branch must be up to date, but GitHub does not bring a branch up to date. Akasha's helpers do it ([Pull requests that are behind](#pull-requests-that-are-behind)).

## Akasha's helpers

| Helper | When it runs | What it does |
|:--|:--|:--|
| `akasha-merge` | After each run of the check `akasha` on a pull request, and after each approval of a pull request | Works on a pull request with the label `akasha-merge` from a branch of the repository, not from a fork. When the check passed and the branch is behind, it brings the branch up to date. Where GitHub has no auto-merge, it merges the pull request when the check passed on its latest commit, the branch is up to date, and an owner of each changed file with owners approved. Then it closes the linked board issue and brings the other pull requests with the label up to date. Each run also examines the other pull requests with the label. When the check failed, it tells the holder of the task |
| `akasha-watch` | After each push to the default branch | Where GitHub has no branch protection, it examines each new commit and opens an issue for each problem. It undoes a commit without a pull request and a passed check. It also undoes a commit that changed an owned file without the approval of an owner. With the GitHub app, it also brings each pull request with the label up to date |

Before the merge helper merges, it applies the rules of the watch. The code owners come from the team config on the default branch, and the last review of each person counts: a later comment does not take an approval back. As in the branch protection that Akasha sets, an approval stays after later commits: the helpers bring a pull request up to date with a merge commit, and a new approval after each update would stop each merge. When an owner did not approve, the helper writes one comment on the pull request with the names of the owners, and it does not merge. The approval of an owner starts the merge helper again. Thus the watch does not undo a merge of the helper.

The merge helper runs one run at a time. GitHub keeps only the newest waiting run and cancels the others. Thus each run also examines the other pull requests with the label, the oldest first: it merges a pull request that is ready, and it brings up to date or comments on a pull request that is behind. A waiting run that GitHub cancels is then no loss.

The watch reports a force push and a push of an administrator, and it does not undo them. This agrees with GitHub protection, where administrators can go around the rules.

The watch undoes on the latest default branch on the server. When another push came first and the server refuses the push of the watch, the watch fetches and undoes again, three times at most. Each undo commit starts with `Akasha undid <commit>`. The watch keeps such a commit only when a helper pushed it and it is the exact reverse of an earlier commit on the branch. A helper is a GitHub app, for example the app of Akasha, or the account whose token is in the secret `AKASHA_TOKEN`. Thus a person cannot put a change on the branch with a copy of the subject, or undo a change with a copy of an undo. The watch does not examine the undone commit again: when the rules changed, two runs that do not agree would undo each other without end.

When GitHub does not answer, the helpers do nothing, and their run fails. For example, the watch does not read a failed answer as "no merged pull request".

> **CAUTION:** GitHub protection stops a bad change before it merges. The watch undoes it right after it arrives. For a change of data, the undo of the code does not undo the data.

## Pull requests that are behind

The server rules merge only a branch that is up to date with the default branch. When one task merges, the other pull requests are behind, and GitHub does not bring them up to date. Thus Akasha does it, in both kinds of repository:

1. The handover gives the label `akasha-merge` to each pull request of a task. Where GitHub merges, the label only selects the pull requests that the helpers bring up to date. `infra --apply` gives the label to each open pull request of a task that does not have it: a pull request from a branch of the repository, not from a fork, that a task on the board names. Each person can copy the mark of a task into a pull request, so the mark alone is not sufficient.
2. After each push to the default branch, the `update` job of `akasha-watch` examines each open pull request with the label. It skips a draft, a pull request from a fork, a pull request whose check failed on its latest commit, and a pull request whose task is not open or stopped. It asks GitHub to merge the default branch into each pull request that is behind.
3. The check runs again on the new commit. When it passes, the pull request merges.
4. When the check passes on a branch that is behind, the merge helper also brings the branch up to date.

| Result of an update | What Akasha does |
|:--|:--|
| A conflict | One comment on the pull request and one on the issue of the task, for each commit. The comment names the holder of the task, or the author of the pull request when nobody holds the task. The holder does the handover again and repairs the conflict in the work copy |
| The pull request got a new commit | Nothing. The new commit starts the check |
| Another failure, for example a limit of the GitHub API | The run tells it. Nothing goes on the pull request |

When the check fails on a pull request with the label, the merge helper writes one comment on the pull request and one on the issue of the task, for each commit.

The update makes a merge commit on the task branch on the server. Thus the handover merges the task branch from the server first, then the latest default branch. When the server refuses the push of the handover, Akasha merges both again and pushes once more. It never forces the push.

> **NOTE:** When n pull requests wait at the same time, each merge makes the others run the check again: about n(n+1)/2 runs in total. A new commit on a pull request stops the check of its older commit. The GitHub merge queue costs less, but only the repositories of an organization can use it.

## The GitHub app of Akasha

A merge or a push with the workflow token starts no other workflow, for example a deployment on the default branch. After an update with the workflow token, the check of the pull request waits until a person approves its run. Thus the helpers use the token of a GitHub app when the repository has one.

| Item | Value |
|:--|:--|
| Repository variable `AKASHA_APP_CLIENT_ID` | The Client ID of the app |
| Repository secret `AKASHA_APP_KEY` | A private key of the app |
| Permissions of the app | Contents, Pull requests, Issues, and Workflows: read and write. Checks: read |

The helpers use the first token that they have: the token of the app, the secret `AKASHA_TOKEN`, then the workflow token. The `update` job of `akasha-watch` runs only with the app. Without the app and without `AKASHA_TOKEN`, the helpers do not bring a pull request up to date, and where GitHub has no auto-merge, the merge helper asks for the handover again on a pull request that is behind, once for each commit.

An app is better than a personal token in `AKASHA_TOKEN`: it belongs to no person, its token expires after one hour, and it can have access to one repository only.

> **CAUTION:** Without the Workflows permission, the merge helper cannot merge a pull request that changes `.github/workflows/`, and the watch cannot undo such a commit. The watch needs this permission.

When the variable is missing in the repository and in its organization, `infra` and `setup` tell an administrator. This notice does not stop a handover. Akasha asks only an administrator, because the documents of GitHub do not agree on who can read the variables. The `akasha-setup` skill tells how to make the app.

## CODEOWNERS

Akasha writes its lines between `# akasha:start` and `# akasha:end`, at the end of the CODEOWNERS file. It keeps the other lines of the team.

- `akasha.toml`, `.akasha/workflows/`, `.github/`, and the CODEOWNERS file belong to the administrators.
- Each gate in `[approval]` gives the risk patterns of its level to the people with the gate roles.
- `.akasha/context/` and the map folder have no owner, so that an update of the product map does not stop a merge. A risk pattern can match a map file, for example `**/auth/**` and `.akasha/context/map/auth/login.md`. Thus, when a gate gives risk patterns to people, Akasha writes a line without owners for the map folder and for `.akasha/context/product-map.md` after the risk patterns. That line also wins over a line of your team for the map folder. Without a gate, a line of your team that owns the map folder, for example `docs/`, makes each update of a map file wait for that review.

A plain GitHub name gets the prefix `@`.

> **NOTE:** In CODEOWNERS, the last matching line wins. A line of the team for all files, for example `* @team-leads`, makes each pull request wait for that review.

The Akasha block is last, so for the files of its lines, a line of the team has no effect. When a line of the team covers a file of a line of the block, `infra --apply` and `setup --approve-infra` show a warning with the two lines, for example for `/.github/workflows/ @ops` and the line of the block for `/.github/`. Akasha compares the common patterns: `*`, `?`, `**`, a folder, and a pattern with or without a leading `/`. The warning does not stop a handover.

## Procedure: examine and correct the settings

1. Run `infra`. Akasha shows each setting that is different from the team config. It reads the server files and the team config from the default branch. It also shows the warnings that do not stop a handover, for example a runner of the team in a public repository.
2. Ask an administrator to approve the correction.
3. On the computer of the administrator, run `infra --apply`. Akasha writes the server files with the values of the team config in the checkout, sets branch protection or records the helpers, and changes the repository settings. It shows the warnings for the team config in the checkout. Akasha does not trust a typed name: the GitHub account of the computer must be in `[roles] administrators`, when the list names people, and must administer the repository on GitHub. `--by` is optional, and it must be that account. Without GitHub, `--by <administrator>` names the administrator.
4. Make a new branch. Commit the server files and `akasha.toml` on it and open a pull request.
5. Ask an administrator to merge the pull request.
6. Run `infra` again. Make sure that it shows no problem.

The `akasha-setup` skill does these steps for the first setup.

> **CAUTION:** Akasha changes the GitHub settings only with the approval of an administrator that `[roles]` names. With GitHub, that administrator is the GitHub account of the computer.

## When a person opens the repository

Each person installs Akasha. Nobody has to do a setup in a repository that is ready. At the start of each session, Akasha examines the server rules and tells the result only when a rule is off:

| Result | What Akasha tells |
|:--|:--|
| All rules are on | Nothing |
| A rule is off, and the person administers the repository | Turn the rules on with the `akasha-setup` skill |
| A rule is off, and the person does not administer the repository | Ask an administrator. Work can start now; the handover waits |
| The default branch on the server has `akasha.toml`, but the checkout of the person does not | Pull the default branch. Do not set up Akasha again. The guard works already |

Akasha keeps the result for one hour in `.akasha/state/server.json`, so that a session start stays fast. Akasha examines GitHub again before the hour ends when one of these changed:

- the default branch on this computer, after a fetch. For example, an administrator merged the server files.
- the GitHub account of this computer.
- the files of Akasha, after an update. The version stays the same after an update, so Akasha compares the files.

Each `infra` command and each examination before the handover updates the result. The examination before the handover never uses the kept result.

The session start notice comes in 15 seconds, also when GitHub is slow. When the examination of the server rules does not end in that time, the notice comes without the result. The next session start examines GitHub again.

To find the default branch without the network, the hooks read this result, else `origin/HEAD`. `setup` asks the server. When the default branch already has `akasha.toml` and the checkout does not, `setup` writes nothing and tells the person to pull.

## When a person changes a setting

A person can change a setting on GitHub. Before each handover, Akasha examines the settings again. A task cannot go to the handover stage while a setting is not correct. The agent engine tells an administrator, and the administrator approves the correction.

A person without administrator rights cannot read all of branch protection. For that person, Akasha examines the required check and the settings that GitHub shows.

## Requirements

- The `gh` command line, logged in with an account that can write to the repository.
- To set branch protection and the repository settings, an account with administrator rights on the repository.
- GitHub Actions in the repository. On GitHub Free, private repositories get a monthly quota of Actions minutes.
- Recommended: the GitHub app of Akasha on the repository, with the variable `AKASHA_APP_CLIENT_ID` and the secret `AKASHA_APP_KEY`. Without it, the pull requests do not come up to date by themselves, and a merge of the helpers starts no other workflow.
