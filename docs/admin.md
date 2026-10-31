# Set up a team

The administrator sets up a repository once. The AI does each step with the akasha-setup skill: say "Set up Akasha" or
"Akasha 설정해줘". This page tells what happens, for the person who must understand it.

## What the administrator decides

| Question | Where it goes |
|:--|:--|
| Who are the administrators? | `[team] admins` |
| Which paths are risky, and who reviews a change there? | `[risk] paths`, `[team] reviewers` |
| Which commands check a change? Does the team have its own CI? | `[checks]`, `[ci] required` |
| Which documents must the AI read before the preview, the plan, and the review? | `[guides]` |

Start with the checks that the team already has. Add a check when the same problem comes back (see the retro below):
a long list of rules on the first day stops each task.

## The steps

1. `akasha doctor` shows what this computer needs.
2. `akasha setup` writes the files:

   | File | Function |
   |:--|:--|
   | `akasha.toml` | The rules of the team, with the usual commands of the main language |
   | `.gitignore` | Ignores `.akasha/state/`, the work folder, and the files that tests and builds make |
   | `.github/CODEOWNERS` | The Akasha block: the reviewers own the risky paths, the administrators own the rules |
   | `.github/workflows/akasha.yml` | The check of Akasha, when the team has no CI of its own |
   | `.github/workflows/akasha-watch.yml` | The watch, where GitHub cannot protect the default branch |
   | `.github/pull_request_template.md` | For a pull request that a person opens by hand |
   | `.claude/settings.json` | Registers the marketplace of Akasha and turns the plugin on for each teammate |
   | `AGENTS.md`, `.codex/hooks.json` | The rules and the hooks of Akasha for Codex. The other text and hooks stay |

3. The AI asks the questions above and writes the answers into `akasha.toml`. Then `akasha setup` again.
4. `akasha setup --apply` on the computer of an administrator of the GitHub repository. It turns on the branch
   protection, the squash merge, the auto-merge, the deletion of merged branches, and the labels. Where GitHub refuses
   the protection because of the plan, it records `rules = "akasha"`.
5. Commit the files on a branch, open a pull request, and merge it. Before this merge, the main checkout is free to
   change. After it, each change is a task.

## Server rules

| Repository | What stops a bad merge |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | GitHub: the required checks on an up-to-date branch, the code owners, no force push |
| Private on GitHub Free | Akasha on each computer merges only after the same examination. The watch examines each push to the default branch and opens an issue for the administrators when a change went around the rules. It changes no code |

On GitHub Free, a person with write access can still merge by hand on GitHub. The watch tells it after the push. For
protection before each merge, move to GitHub Pro or Team, or make the repository public, then run
`akasha setup --apply` again.

## A team that has its own CI

Write the names of its required checks in `[ci] required`. Akasha keeps its own check away, and waits for these
checks on GitHub. Each push of a draft pull request starts the CI too. To save the runners, the CI can skip drafts:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  checks:
    if: ${{ !github.event.pull_request.draft }}
```

## Teammates

Each teammate installs the plugin once (`/plugin marketplace add Gruci/akasha-team-harness`, then
`/plugin install akasha@akasha`), logs in with `gh auth login`, and opens the repository. The committed
`.claude/settings.json` registers the marketplace when they trust the folder. The akasha-join skill checks the rest
with `akasha doctor`: Python 3.11 or higher, the GitHub CLI, write access, and the programs of the checks.

Codex needs Akasha as a package: `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.

## The retro: grow the rules from the problems

`akasha retro` shows the checks that failed most, the checks that passed on a computer and failed on GitHub, the actions
that Akasha stopped, and the review rounds of the plans of the last merged tasks. The akasha-retro skill turns a
repeated problem into a new check of the team, as an Akasha task. When a new check finds problems in the existing
code, keep a list of the existing problems that it accepts, and let the list only get shorter.

## Update Akasha

Each release of Akasha has its own tag. To update, change the version in the plugin and in the `AKASHA_SOURCE` of the
workflows (`akasha setup` writes them), merge, and ask each teammate to update the plugin.
