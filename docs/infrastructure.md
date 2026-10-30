# Infrastructure

The infrastructure manager keeps the GitHub settings of the repository the same as the team config. These settings are the third enforcement layer. They operate also when a person does not use Akasha.

## Server rules: GitHub first, Akasha's helpers second

GitHub's own branch protection and auto-merge come first. Akasha's helpers fill the gap only where the GitHub plan has none.

| Repository | `[server] rules` | Who enforces the rules |
|:--|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | `github` | GitHub: branch protection, the required check, code owners, and auto-merge |
| Private on GitHub Free | `akasha` | Akasha's helpers: `akasha-merge` and `akasha-watch` |

The setup tries GitHub's branch protection first. When GitHub refuses it because of the plan, the setup records `rules = "akasha"` in `akasha.toml`. When the plan changes, run the setup again. Then GitHub's rules take over.

The helpers are always installed. Before each action, they examine the default branch on GitHub. While GitHub protects it, they do nothing.

## What Akasha installs

| Item | Location | Function |
|:--|:--|:--|
| Required check `akasha` | `.github/workflows/akasha.yml` | Runs the required checks of the team on each pull request |
| Merge helper | `.github/workflows/akasha-merge.yml` | Merges a pull request with the label `akasha-merge` after the check passes, where GitHub has no auto-merge |
| Watch helper | `.github/workflows/akasha-watch.yml` | Undoes a change on the default branch that went around the check, where GitHub has no branch protection |
| CODEOWNERS block | The CODEOWNERS file of the repository | Gives the team rules to the administrators, and each gate to its people |
| Pull request template | `.github/pull_request_template.md` | Gives the sections of the briefing to people who open a pull request by hand. Akasha keeps a template that the team already has |
| Branch protection | The GitHub settings of the default branch | Stops a merge without the required check, when the plan has it |
| Repository settings | The GitHub settings of the repository | Permit auto-merge and squash merges, and delete a merged branch |

## The required check

The check runs on each pull request and on each merge queue run:

1. It installs Akasha. The repository variable `AKASHA_SOURCE` can name another source, for example a mirror or a fork.
2. It takes `akasha.toml` from the default branch.
3. It runs the `setup` command of the team.
4. It runs the required checks on the files that the pull request changes.

The rules come from the default branch. Thus a pull request that makes the checks weaker cannot pass with its own rules.

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

## Akasha's helpers

| Helper | When it runs | What it does |
|:--|:--|:--|
| `akasha-merge` | After each run of the check `akasha` on a pull request | Merges the pull request when it has the label `akasha-merge`, the check passed on its latest commit, and the branch is up to date. Then it closes the linked board issue |
| `akasha-watch` | After each push to the default branch | Examines each new commit, and opens an issue for each problem. It undoes a commit without a pull request and a passed check. It also undoes a commit that changed an owned file without the approval of an owner |

The watch reports a force push and a push of an administrator, and it does not undo them. This agrees with GitHub protection, where administrators can go around the rules.

> **CAUTION:** GitHub protection stops a bad change before it merges. The watch undoes it right after it arrives. For a change of data, the undo of the code does not undo the data.

> **NOTE:** A merge with the workflow token starts no other workflow, for example a deployment on the default branch. To start them, store a token with write access as the repository secret `AKASHA_TOKEN`.

## CODEOWNERS

Akasha writes its lines between `# akasha:start` and `# akasha:end`, at the end of the CODEOWNERS file. It keeps the other lines of the team.

- `akasha.toml`, `.akasha/workflows/`, `.github/`, and the CODEOWNERS file belong to the administrators.
- Each gate in `[approval]` gives the risk patterns of its level to the people with the gate roles.
- `.akasha/context/` has no owner, so that an update of the product map does not stop a merge.

A plain GitHub name gets the prefix `@`.

> **NOTE:** In CODEOWNERS, the last matching line wins. A line of the team for all files, for example `* @team-leads`, makes each pull request wait for that review.

## Procedure: examine and correct the settings

1. Run `infra`. Akasha shows each setting that is different from the team config. It reads the server files and the team config from the default branch.
2. Ask an administrator to approve the correction.
3. On the computer of the administrator, run `infra --apply`. Akasha writes the server files, sets branch protection or records the helpers, and changes the repository settings. Akasha does not trust a typed name: the GitHub account of the computer must be in `[roles] administrators`, when the list names people, and must administer the repository on GitHub. `--by` is optional, and it must be that account. Without GitHub, `--by <administrator>` names the administrator.
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

To find the default branch without the network, the hooks read this result, else `origin/HEAD`. `setup` asks the server. When the default branch already has `akasha.toml` and the checkout does not, `setup` writes nothing and tells the person to pull.

## When a person changes a setting

A person can change a setting on GitHub. Before each handover, Akasha examines the settings again. A task cannot go to the handover stage while a setting is not correct. The agent engine tells an administrator, and the administrator approves the correction.

A person without administrator rights cannot read all of branch protection. For that person, Akasha examines the required check and the settings that GitHub shows.

## Requirements

- The `gh` command line, logged in with an account that can write to the repository.
- To set branch protection and the repository settings, an account with administrator rights on the repository.
- GitHub Actions in the repository. On GitHub Free, private repositories get a monthly quota of Actions minutes.
