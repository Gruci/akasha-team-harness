# Set up a team

The administrator sets up a repository once. The AI does each step with the akasha-setup skill: say "Set up Akasha", in
any language. This page tells what happens, for the person who must understand it.

## What the administrator decides

| Question | Where it goes |
|:--|:--|
| Who are the administrators? | `[team] admins` |
| Which paths are risky, and who reviews a change there? | `[risk] paths`, `[team] reviewers` |
| Which commands check a change? Does the team have its own CI? | `[checks]`, `[ci] required` |
| What must each computer install to run the checks? | `[checks] setup`, `ready` of each check, `[guides] join` |
| Which documents must the AI read before the preview, the plan, and the review? | `[guides]` |
| Which folder do the checkers of the team skip, for the records of the tasks? | `[work] records` |
| Which workflow deploys each merge? | `[deploy] workflow` |

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
   | `.github/workflows/akasha-watch.yml` | The watch, where GitHub does not protect the default branch |
   | `.claude/settings.json` | Registers the marketplace of Akasha and turns the plugin on for each teammate |
   | `CLAUDE.md` | The Akasha block for Claude Code: use the akasha-build skill, and this procedure comes first. The other text stays |
   | `AGENTS.md`, `.codex/hooks.json` | The rules and the hooks of Akasha for Codex. The other text and hooks stay |

   Where GitHub does not protect the default branch now, `akasha setup` records `rules = "akasha"` and writes the
   watch, so that nothing merges before the checks even before `--apply`.
3. The AI reads the own agent rules of the repository (below), asks the questions above, and writes the answers into
   `akasha.toml`. Then `akasha setup` again.
4. `akasha setup --apply` on the computer of an administrator of the GitHub repository. It turns on the branch
   protection, the squash merge, the deletion of merged branches, and the labels, and the auto-merge where GitHub
   protects the branch. Where GitHub refuses the protection because of the plan, it records `rules = "akasha"`.
5. Commit the files on a branch, open a pull request, wait for the required checks of the team, and merge it. Before
   this merge, the main checkout is free to change. After it, each change is a task.

## A repository with its own harness

A repository that an AI already works in often has its own procedure in `CLAUDE.md`, `AGENTS.md`, skills, hooks, and
gates: a scope interview, a plan that a person approves, plan files in a folder, worktrees in a folder, a task board, a
merge by the AI. Akasha works next to it; the hooks and gates of the repository stay.

| Decision | Where |
|:--|:--|
| Who keeps the own procedure (often the administrator who built it). Akasha does not stop their work outside its tasks, and the watch accepts their pull requests when the checks passed | `[team] own_procedure` |
| Everyone else follows Akasha. Its block in `CLAUDE.md` and `AGENTS.md` says that its procedure comes first, and keeps the records where Akasha puts them | written by `akasha setup` |
| A checker that allows only listed files at the top | put the rules at `.github/akasha.toml` |
| A checker that examines files by their folder, for example Markdown files: the records of each task go into git | `[work] records`: a folder that the checker skips |
| A folder that the repository already ignores for work copies, and that its gates know | `[work] folder`, for example `worktrees` |
| Files that the hooks or tools of the repository write in each work copy, for example caches | `.gitignore` lines with `**/` in front |
| A personal settings file in git, for example `.claude/settings.local.json` with wide permissions | remove it from git |
| Hooks that start each session with maintenance or audits | do what is due before teammates join; Akasha tells the sessions of teammates to skip them |
| Shared files that many features change (routes, menus, generated indexes) | a short document in `[guides] build` that tells how to merge each |
| The programs that the hooks of the repository run, for example `python` | `ready` of the checks with the same name; `akasha doctor` also runs them |

The own save-time hooks of the repository see the work copy of a task when the session moves into it (Claude Code:
`EnterWorktree` with its path). The akasha-build skill does it when the build starts. Exact Akasha commands run without
a permission prompt: the hook of Akasha allows them, so a teammate does not need wide permissions.

## Server rules

| Repository | What stops a bad merge |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | GitHub: the required checks on an up-to-date branch, the code owners, no force push |
| Private on GitHub Free | Akasha on each computer merges only after its examination: the required checks passed on the current head, the branch is up to date, and a reviewer (risky paths) or an administrator (`akasha.toml`, `.github/`, CODEOWNERS) other than the author approved. GitHub does not enforce CODEOWNERS there, so Akasha reads the reviews itself. The watch examines each push to the default branch and opens an issue for the administrators when a change went around the rules: no Akasha task, no approved preview, no passed plan review, no passed checks, or no review of its owners. It changes no code |

On GitHub Free, a person with write access can still merge by hand on GitHub. The watch tells it after the push. For
protection before each merge, move to GitHub Pro or Team, or make the repository public, then run
`akasha setup --apply` again.

## A team that has its own CI

Write the names of its required checks in `[ci] required`, as GitHub shows the jobs (for example `checks`, not the name
of the workflow). Akasha keeps its own check away, and waits for these checks on GitHub. Each push of a draft pull
request starts the CI too. To save the runners, the CI can skip drafts:

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
`.claude/settings.json` registers the marketplace when they trust the folder. The akasha-join skill reads
`[guides] join` and checks the rest with `akasha doctor`: Python 3.11 or higher for the hooks (they try `py -3`,
`python3`, and `python`), the name of git, the GitHub CLI and its login for git, write access, and each check of the
team (its `ready` command, else its program).

Codex needs Akasha as a package in the Python of its hooks: on Windows
`py -3 -m pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.1"`, elsewhere `python3 -m pip install …`.
Codex runs Akasha as `py -3 -X utf8 -m akasha` on Windows and `python3 -m akasha` elsewhere.

## The retro: grow the rules from the problems

`akasha retro` shows the checks that failed most, the checks that passed on a computer and failed on GitHub, and the
review rounds of the plans of the last merged tasks of the team, and the actions that Akasha stopped on the computer
that runs it. The akasha-retro skill turns a
repeated problem into a new check of the team, as an Akasha task. When a new check finds problems in the existing
code, keep a list of the existing problems that it accepts, and let the list only get shorter.

## Change the rules, or update Akasha

After the first setup, a change of the rules is a task like each other change: `akasha start "<title>"`, change
`akasha.toml` in the work copy of the task, run `akasha setup` there (it writes CODEOWNERS and the workflows into the
work copy), then check and land it. The landing waits for the review of an administrator other than the author.

Each release of Akasha has its own tag. To update, each teammate updates the plugin, and one task runs `akasha setup`
with the new Akasha: it writes the new version into the workflows.
