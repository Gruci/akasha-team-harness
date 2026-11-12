# Set up a team

The administrator sets up a repository once, and then maintains it: the rules of Akasha, the database, and the
deployment. The administrator reviews no task, except a change of existing lines of the core: the administrator
approves it on GitHub (below). The AI does each step with the akasha-setup skill: say "Set up Akasha",
in any language. This page tells what happens, for the person who must understand it.

## What the administrator decides

| Question | Where it goes |
|:--|:--|
| Who are the administrators? Each other person with write access is a teammate | `[team] admins` |
| Does a program run an agent that changes the code for people? Its GitHub account | `[team] agents` |
| Which parts are risky, for example the database and the deployment? Only an administrator changes them | `[risk] paths` |
| Which folders hold one feature each? The AI proposes them from the folders of the repository. A file that two or more other areas import is core | `[core] areas`, `[core] used_by` |
| Which files must an administrator approve before a change of their existing lines, for example the definitions of the database? | `[core] paths` |
| Which commands check a change? Does the team have its own CI? | `[checks]`, `[ci] required` |
| What must each computer install to run the checks? | `[checks] setup`, `ready` of each check, `[guides] join` |
| Which documents must the AI read before the preview, the plan, and the review? | `[guides]` |
| How does a teammate read the data, so that the preview shows each value now (a copy of the database, a read-only account, an API)? | a file of `[guides] preview` and `[guides] join` |
| Which files make data that people see, for example queries and calculations? Their previews define each value | `[preview] data` |
| Which folder do the checkers of the team skip, for the records of the tasks? | `[work] records` |
| Which workflow deploys each merge? | `[deploy] workflow` |
| Which command shows that the live service works after a deployment? | `[deploy] verify` |

Start with the checks that the team already has. Add a check when the same problem comes back (see the retro below):
a long list of rules on the first day stops each task.

## The steps

1. `akasha doctor` shows what this computer needs.
2. `akasha setup` writes the files:

   | File | Function |
   |:--|:--|
   | `akasha.toml` | The rules of the team, with the usual commands of the main language |
   | `.gitignore` | Ignores `.docs/state/`, the work folder, the own agent settings of each person (`.claude/settings.local.json`, `CLAUDE.local.md`), and the files that tests and builds make |
   | `.github/workflows/akasha.yml` | The check of Akasha, when the team has no CI of its own |
   | `.github/workflows/akasha-watch.yml` | The watch, where GitHub does not protect the default branch |
   | `.claude/settings.json` | Registers the marketplace of Akasha and turns the plugin on for each teammate. Allows the git and gh commands that only read, and lets edits pass without a prompt (`acceptEdits`) when the team set no mode: Akasha still stops each edit that a task must not make. The other keys stay |
   | `CLAUDE.md` | The Akasha block for Claude Code: use the akasha-build skill, and this procedure comes first. The other text stays |
   | `AGENTS.md`, `.codex/hooks.json` | The rules and the hooks of Akasha for Codex. The other text and hooks stay |
   | `pre-commit`, `pre-push` in the hooks folder of git | The two rules that hold for each agent engine and for a person in a terminal: no commit on the default branch, and no push to it. Each session start writes them on its computer. A hook of the team stays, and `akasha doctor` tells which line to add to it |

   Where GitHub does not protect the default branch now, `akasha setup` records `rules = "akasha"` and writes the
   watch, so that nothing merges before the checks even before `--apply`.
3. Draw the map of the product: name the folder of one area (`[core] areas`) and its entry (`[boundaries]`), run
   `akasha map --draft`, and correct the sheet of each area with the AI: its purpose in one line, the areas that it
   uses, and the tables that it writes. Each later task reads the map to find where its code goes, so the map comes
   before the other rules. `akasha map` shows it.
4. The AI reads the own agent rules of the repository (below), asks the questions above, and writes the answers into
   `akasha.toml`. Then `akasha setup` again.
5. `akasha setup --apply` on the computer of an administrator of the GitHub repository. It turns on the branch
   protection, the squash merge, the deletion of merged branches, and the labels, and the auto-merge where GitHub
   protects the branch. Where GitHub refuses the protection because of the plan, it records `rules = "akasha"`.
6. Commit the files on a branch, open a pull request, wait for the required checks of the team, and merge it. Before
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
| A personal settings file in git, for example `.claude/settings.local.json` with wide permissions | remove it from git. Each person tunes their own harness there, and the edits never need a task |
| Hooks that start each session with maintenance or audits | do what is due before teammates join; Akasha tells the sessions of teammates to skip them |
| Shared files that many features change (routes, menus, generated indexes) | a short document in `[guides] build` that tells how to merge each |
| The programs that the hooks of the repository run, for example `python` | `ready` of the checks with the same name; `akasha doctor` also runs them |

The own save-time hooks of the repository see the work copy of a task when the session moves into it (Claude Code:
`EnterWorktree` with its path). The akasha-build skill does it when the build starts. Exact Akasha commands run without
a permission prompt: the hook of Akasha allows them, so a teammate does not need wide permissions.

## Server rules

| Repository | What stops a bad merge |
|:--|:--|
| Public, or private on GitHub Pro, Team, or Enterprise | GitHub: the required checks on an up-to-date branch, no force push |
| Private on GitHub Free | Akasha on each computer merges only after its examination: the required checks passed on the current head, and the branch is up to date. The watch examines each push to the default branch and opens an issue for the administrators when a change went around the rules: no Akasha task, no approved preview, no passed plan review, no passed checks, a teammate's change of a part that only an administrator changes, or a teammate's change of existing lines of the core without an approval of an administrator. It changes no code |

Akasha asks for no review of a pull request, except the approval of a core change (below). Where a rule of the
repository on GitHub asks for one, the landing stops and names it, so that an administrator can remove the rule.

On GitHub Free, a person with write access can still merge by hand on GitHub. The watch tells it after the push. For
protection before each merge, move to GitHub Pro or Team, or make the repository public, then run
`akasha setup --apply` again.

## Approve a core change

A teammate's task adds code freely. When it changes or deletes existing lines of a core file (`[core]`), its landing
waits, and Akasha asks the administrators on the pull request. The comment names the files and why each one is core.

1. Open the pull request on GitHub.
2. Examine the change of the named files: do the other areas that use them still work?
3. Click Review changes → Approve. The next landing of the task merges it.

The approval holds for the core files as they are in the approved commit. A later change of those files needs a new
approval. A later Request changes of the same administrator takes the approval back. Only an approval of an
administrator counts. The changes of the administrators and of the people of `[team] own_procedure` need no approval.

## A team that has its own CI

Write the names of its required checks in `[ci] required`, as GitHub shows the jobs (for example `checks`, not the name
of the workflow). Akasha waits for these checks on GitHub, together with its own check (`akasha`), which it
installs in each case. The CI of the team need not run a command of Akasha: when it ran
`python -m akasha check --ci`, remove that step. Let the CI run on draft pull requests, and do not start it again
when a draft gets ready:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
```

Akasha pushes a draft only after `akasha check` passed on the computer, and the landing counts a run that passed on
the same commit while the pull request was a draft. A second run on `ready_for_review` makes the merge wait again.
See `[ci]` in [team-config.md](team-config.md#ci).

## Teammates

Each teammate installs the plugin once (`/plugin marketplace add Gruci/akasha-team-harness#v<version of the team>`,
then `/plugin install akasha@akasha`), logs in with `gh auth login`, and opens the repository. The committed
`.claude/settings.json` registers the marketplace at the version of the team when they trust the folder. The akasha-join skill reads
`[guides] join` and checks the rest with `akasha doctor`: Python 3.11 or higher for the hooks (they try `py -3`,
`python3`, and `python`), the name of git, the GitHub CLI and its login for git, write access, and each check of the
team (its `ready` command, else its program).

Codex needs Akasha as a package in the Python of its hooks: on Windows
`py -3 -m pip install "git+https://github.com/Gruci/akasha-team-harness@v2.0.0"`, elsewhere `python3 -m pip install …`.
Codex runs Akasha as `py -3 -X utf8 -m akasha` on Windows and `python3 -m akasha` elsewhere.

## Agent accounts

An agent account is a GitHub account that a program, the relay, runs: for example an operations agent that diagnoses
a failed job and fixes it when a person asks. Its tasks have no preview, and the person approves the result before the
merge (see "An agent task" in [how it works](how-it-works.md)).

1. Make a GitHub account for the agent, invite it to this repository only, and give the relay its key. A change of the
   agent then shows under its own name, and a removal from the collaborators stops it.
2. Add its name to `[team] agents` with a task of an administrator.
3. The relay runs the agent engine with the plugin of Akasha, and keeps these duties:
   - Each prompt carries the words of a person, as they wrote them: first the request, later their answer to the
     result. It can name the person on the first line: `[akasha-from: <name>]`.
   - After `akasha land` says ASK (exit code 4), the session ends its turn with the text of `akasha result`. The relay
     sends that text to the person, and gives their answer as the next prompt.
   - The relay keeps the last word on the merge. The hooks keep a cooperative agent engine on the procedure; they are
     not a sandbox. A relay that holds the GitHub key outside the session and examines each merge stops an agent
     engine that does not cooperate.

## The retro: grow the rules from the problems

`akasha retro` shows the checks that failed most, the checks that passed on a computer and failed on GitHub, and the
review rounds of the plans of the last merged tasks of the team, and the actions that Akasha stopped on the computer
that runs it. The akasha-retro skill turns a
repeated problem into a new check of the team, as an Akasha task. When a new check finds problems in the existing
code, keep a list of the existing problems that it accepts, and let the list only get shorter.

## Change the rules, or update Akasha

After the first setup, a change of the rules is a task of an administrator like each other change: `akasha start
"<title>"`, change `akasha.toml` in the work copy of the task, run `akasha setup` there (it writes the workflows into
the work copy), then check and land it. The same holds for the database and the deployment: when a teammate's task
needs a change there, the AI asks with `akasha help`, and an administrator makes it in a task of their own.

Each release of Akasha has its own tag. `[team] version` in `akasha.toml` holds the version of the team, and an
administrator chooses it. The CI and the watch run that version itself: the server is the judge of each change. A
computer runs it or another patch of the same minor version (2.0.x), because a patch changes no rule. An Akasha of
another minor version, older or newer, also of an administrator, starts no task, takes over no task, and hands no
task over to the merge. `akasha setup` pins it in three places: the marketplace of
Claude Code in `.claude/settings.json` (`"ref": "v<version>"`), the pip line of Codex in `AGENTS.md`, and the
workflows. It writes this Akasha into `[team] version` only when the setting is empty. To raise the version:

1. On a computer that runs the version of the team now, start a task.
2. In its work copy, change `[team] version` in `akasha.toml` to the new version, and run `akasha setup` there. It
   refuses a version without a release tag in the public repository. The pins name the new version; the workflows and
   the agent instructions still come from the Akasha that ran, and the setup says so.
3. Check and land it. Its own server check runs the new version.
4. After the merge, each computer pulls the default branch and restarts the agent app: Claude Code loads the pinned
   version. The session start notice names a difference with the commands that fix it, and `akasha doctor` fails until
   the computer runs the version of the team. Codex: `pip install "git+https://github.com/Gruci/akasha-team-harness@v<version>"`.
5. When `akasha doctor` of the new version names old server rules, run `akasha setup` again in a task.

When the server check or the watch fails with "The server runs Akasha …", the Akasha on the server differs from
`[team] version`: run `akasha setup` again in a task, and remove the repository variable `AKASHA_SOURCE` or set it to
the same version.

### From 1.x to 2.0

A new major version can give a setting another meaning, so the task that raises it does more than change a number.
End or cancel each open task first: a task of 1.x has no steps in its plan and no review of its result.

1. `[work] records` and `[work] archive`. In 1.x the records of the merged tasks stayed in the records folder. In 2.0
   the records folder holds only the task in work, on its own branch, and the landing moves the records into the
   archive, which no work copy holds. The task that raises the major version sets both folders once more: Akasha
   refuses a change of them in any other task. Move the old records into the archive in the same task, as
   `<archive>/YYYY/MM/YYYY-MM-DD-<task>/`, and correct each document, hook, and ignore rule of the repository that
   names the old folder. How the old records lie is the history of the repository, so Akasha has no command for it.
2. A CI of the team that ran `python -m akasha check --ci` removes that step, and the Akasha that its image
   installed. Akasha installs its own check (`.github/workflows/akasha.yml`), and the landing waits for it by the
   name `akasha`. `[ci] runs-on` names its machine, also a runner of the team.
3. Each other place of the repository that names the version of Akasha: a document for new teammates, an image of
   an agent. `git grep -n <old version>` lists them.
4. Draw the map of the product (step 3 of "The steps"), in this task or in the next one.
