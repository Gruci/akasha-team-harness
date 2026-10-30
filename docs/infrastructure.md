# Infrastructure

The infrastructure manager keeps the GitHub settings of the repository the same as the team config. These settings are the third enforcement layer. They operate also when a person does not use Akasha.

## What Akasha installs

| Item | Location | Function |
|:--|:--|:--|
| Required check `akasha` | `.github/workflows/akasha.yml` | Runs the required checks of the team on each pull request |
| CODEOWNERS | `.github/CODEOWNERS` | Sets who must approve the changes in each area |
| Pull request template | `.github/pull_request_template.md` | Gives the sections of the handover document |
| Branch protection | The GitHub settings of the default branch | Stops a merge without the required check and the approvals |

## The required check

The check runs on each pull request:

1. It installs Akasha.
2. It takes `akasha.toml` from the default branch.
3. It runs the `setup` command of the team.
4. It runs the required checks on the files that the pull request changes.

The rules come from the default branch. Thus a pull request that makes the checks weaker cannot pass with its own rules.

## CODEOWNERS

Akasha writes CODEOWNERS from `[risk]`, `[approval]`, and `[roles]`:

- Each `high` and `medium` risk pattern gets the people who have the roles that `[approval]` names for that level.
- `akasha.toml`, `.akasha/`, and `.github/` belong to the administrators.

A plain GitHub name gets the prefix `@`.

## Branch protection

| Setting | Value |
|:--|:--|
| Required status check | `akasha` |
| The branch must be up to date before a merge | Yes |
| Approvals | One or more |
| Code owner review | Required |
| Force push | Not permitted |
| Deletion of the default branch | Not permitted |
| Administrators can go around the rules | Yes |

## Procedure: examine and correct the settings

1. Run `infra`. Akasha shows each setting that is different from the team config. It reads the server files from the default branch.
2. Ask an administrator to approve the correction.
3. Run `infra --apply --by <administrator>`. Akasha writes the server files and sets branch protection.
4. Make a new branch. Commit the server files on it and open a pull request.
5. Ask an administrator to merge the pull request.
6. Run `infra` again. Make sure that it shows no problem.

The `akasha-setup` skill does these steps for the first setup.

> **CAUTION:** Akasha changes the GitHub settings only with the approval of an administrator that `[roles]` names.

## When a person changes a setting

A person can change a setting on GitHub. Each handover examines the settings again. A task cannot complete the handover stage while a setting is not correct. The agent engine tells an administrator, and the administrator approves the correction.

## Requirements

- The `gh` command line, logged in with an account that can read the repository.
- To set branch protection, an account with administrator rights on the repository.
- For a private repository, a GitHub plan that supports branch protection.
