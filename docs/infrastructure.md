# Infrastructure

The infrastructure manager keeps the GitHub settings of the repository the same as the team config. These settings are the third enforcement layer. They operate also when a person does not use Akasha.

## What Akasha installs

| Item | Location | Function |
|:--|:--|:--|
| Required check `akasha` | `.github/workflows/akasha.yml` | Runs the required checks of the team on each pull request |
| CODEOWNERS block | The CODEOWNERS file of the repository | Gives the team rules to the administrators, and each gate to its people |
| Pull request template | `.github/pull_request_template.md` | Gives the sections of the briefing to people who open a pull request by hand. Akasha keeps a template that the team already has |
| Branch protection | The GitHub settings of the default branch | Stops a merge without the required check |
| Repository settings | The GitHub settings of the repository | Permit auto-merge and squash merges, and delete a merged branch |

## The required check

The check runs on each pull request and on each merge queue run:

1. It installs Akasha. The repository variable `AKASHA_SOURCE` can name another source, for example a mirror or a fork.
2. It takes `akasha.toml` from the default branch.
3. It runs the `setup` command of the team.
4. It runs the required checks on the files that the pull request changes.

The rules come from the default branch. Thus a pull request that makes the checks weaker cannot pass with its own rules.

## Branch protection and auto-merge

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
3. Run `infra --apply --by <administrator>`. Akasha writes the server files, sets branch protection, and changes the repository settings.
4. Make a new branch. Commit the server files on it and open a pull request.
5. Ask an administrator to merge the pull request.
6. Run `infra` again. Make sure that it shows no problem.

The `akasha-setup` skill does these steps for the first setup.

> **CAUTION:** Akasha changes the GitHub settings only with the approval of an administrator that `[roles]` names.

## When a person opens the repository

Each person installs Akasha. Nobody has to do a setup in a repository that is ready. At the start of each session, Akasha examines the server rules and tells the result only when a rule is off:

| Result | What Akasha tells |
|:--|:--|
| All rules are on | Nothing |
| A rule is off, and the person administers the repository | Turn the rules on with the `akasha-setup` skill |
| A rule is off, and the person does not administer the repository | Ask an administrator. Work can start now; the handover waits |
| The repository is private on GitHub Free | The owner must change the plan or make the repository public first |

Akasha keeps the result for 12 hours in `.akasha/state/server.json`, so that a session start stays fast. Each `infra` command and each examination before the handover updates it.

## When a person changes a setting

A person can change a setting on GitHub. Before each handover, Akasha examines the settings again. A task cannot go to the handover stage while a setting is not correct. The agent engine tells an administrator, and the administrator approves the correction.

A person without administrator rights cannot read all of branch protection. For that person, Akasha examines the required check and the settings that GitHub shows.

## Requirements

- The `gh` command line, logged in with an account that can write to the repository.
- To set branch protection and the repository settings, an account with administrator rights on the repository.
- For a private repository, GitHub Pro, Team, or Enterprise. GitHub Free has branch protection and auto-merge only in public repositories.
