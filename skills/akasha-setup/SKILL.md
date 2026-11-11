---
name: akasha-setup
description: Set up Akasha in a repository as its administrator: the team rules, the GitHub settings, and the files that bring Akasha to each teammate. Use when the person asks to set up Akasha, in any language, or when the session start notice says that the repository does not use Akasha yet or that the server rules are off.
---

# Set up Akasha (administrator)

The administrator sets up the repository once. After the setup, each teammate only asks for changes and approves
previews. The session start notice gives the Akasha command; this skill writes it as `akasha`. Talk with the person in
their language and in simple words.

## Steps

1. Run `akasha doctor`. Repair each FIX line with the person before you continue, except the `akasha.toml` line,
   which step 3 writes.
2. If the own rules or hooks of the repository forbid changes in the main checkout, make a git worktree on a new
   branch first, and do steps 3 to 9 there.
3. Ask first whether the repository starts now (it has no product code yet). If it does, ask which languages it
   uses, which folder holds one feature (an area, for example `domains/*`), and which file of an area is its
   entry for the other areas (for example `api.py`), then run `akasha setup --new --stack <languages> --areas
   <folder> --entries <files>`: see "A repository that starts now" below. Else:
   Run `akasha setup`. It writes `akasha.toml` with the usual commands of each language, and the other files.
   Where GitHub does not protect the default branch now, it records `[server] rules = "akasha"` and adds the watch.
   If a checker of the repository allows only listed files at the top, move `akasha.toml` to `.github/akasha.toml`
   and run `akasha setup` again: Akasha reads it there too.
4. Read the own agent rules of the repository: `CLAUDE.md`, `AGENTS.md`, `.claude/skills/*/SKILL.md`, the hooks in
   `.claude/settings.json`, the gates or scripts that they run, and the documents they point to. Decide with the
   person who keeps that own procedure (often the administrator who built it) → `[team] own_procedure`: Akasha does
   not stop their work outside its tasks, and the watch accepts their pull requests when the checks passed. For each
   other teammate, list each rule about scope interviews, a plan approval by a person, where plans, research, and
   mockups go, worktrees, task boards, and pushes, pull requests, and merges, and tell the person that Akasha's
   procedure comes first for teammates: Akasha wrote its block into `CLAUDE.md` and `AGENTS.md` with that sentence.
   Keep the design and architecture documents: they go into `[guides]` in step 5. Look also for these:
   - the hooks of the repository that start a session with maintenance or audits: Akasha tells the sessions of
     teammates to skip them, but the administrator does what is due before teammates join;
   - files that tools write in each work copy, for example caches of hooks: add them to `.gitignore` (with `**/` in
     front, so that they match in each folder), else each task commits them and tasks conflict on them;
   - a personal settings file in git, for example `.claude/settings.local.json`: remove it from git
     (`git rm --cached`), else each teammate gets the permissions of one person;
   - a folder that the repository already ignores for work copies, for example `worktrees`: `akasha setup` proposes it
     as `[work] folder`.
5. Ask the person these questions, one at a time, and write each answer into `akasha.toml`:
   - Who are the administrators? (GitHub names) → `[team] admins`. A team has only two roles: the administrators,
     who set up and maintain Akasha, and the teammates (each other person with write access), who approve the
     previews of their own requests. Nobody reviews a task, except a change of existing lines of the core: an
     administrator approves it on GitHub. Only the administrators change `akasha.toml`, `.github/`, CODEOWNERS, and
     the risky parts.
   - Which parts are risky, for example the database and the deployment? → `[risk] paths`. Only an administrator
     changes them: a teammate's task stops there, and its AI asks an administrator with `akasha help`. Keep screens,
     features, and the own agent settings of each person out of the list, so that teammates rarely wait.
   - Which folders hold one feature each? Look at the folders of the repository and propose them, for example
     `domains/*` or `src/features/*` → `[core] areas`. A file that two or more other areas import is core: a change
     of its existing lines waits for the approval of an administrator. New code is always free.
   - Which files must an administrator approve before a change of their existing lines, though a teammate can edit
     them, for example the definitions of the database? → `[core] paths`. Use it also for code that Akasha cannot
     follow: Akasha sees the imports of Python, JavaScript, and TypeScript only.
   - Does the repository have its own CI on GitHub? What are the names of its required checks, as GitHub shows the
     jobs (for example `checks`, not the name of the workflow)? → `[ci] required`. Akasha adds its own check in each
     case, also beside that CI: it runs `[checks]` and the checks of Akasha on GitHub.
   - Which commands check a change? → `[checks]`: one table `[checks.<name>]` for each command, with `cwd` and
     `only_when` for a part in its own folder, and the name in `required`.
   - What must each computer install to run these checks (packages, versions, settings of the network, local files
     such as `.env`)? → `ready` in each check for a quick test that the computer can run it (with the same program
     names as the hooks of the repository, for example `python`), and a short document for `[guides] join`. Keep
     `[checks] setup` empty when it installs much: put that into the join document instead. Leave a check that a
     teammate's computer cannot run to the CI (`[ci] required`).
   - Which team documents must the AI read before the preview (design, words on the screen), before the plan
     (architecture, rules), and for the AI that checks the plan? → `[guides] preview`, `plan`, and `review`. The
     preview shows the value now of each number that comes from data, so a teammate must read the data: how (a copy
     of the database, a read-only account, an API)? Write it into a document of `[guides] preview` and `[guides] join`.
   - Which files make data that people see, for example queries and calculations? → `[preview] data`. A task that
     changes them defines each value of its preview (source, formula, value, check), and is never a quick task.
   - Which files do many new features change, for example the list of routes, the menu, or a generated index? →
     a short document for `[guides] build` that names them and tells how to merge each one when two tasks change it.
   - Does a checker of the repository examine Markdown or other files that it finds by their folder? The records of
     each task (preview, research, plan, summary) go into git. → `[work] records`: a folder that those checkers skip,
     for example `docs/tasks/akasha`.
   - Does a workflow deploy each merge to the default branch? → `[deploy] workflow`: its name or its file name.
     Then Akasha tells the person when the change is live, not only merged.
   - Which command shows that the live service works after a deployment, for example a script that opens the main
     pages? → `[deploy] verify`. When it fails, Akasha tells the person and an administrator.
   - Does the repository already use the folder of `[work] folder` or branches that start with `akasha/`? →
     `[work]`.
6. Run `akasha setup` again. It writes the workflow files from the answers.
7. If the person administers the repository on GitHub, ask them to approve the GitHub changes, then run
   `akasha setup --apply`. It turns on the branch protection, or records that GitHub cannot protect the branch on
   this plan. Tell the person the result in simple words. If the person does not administer the repository, tell them
   to ask an administrator to run it on their own computer.
8. If the team has its own CI, tell the person that each push of a draft pull request starts that CI. To save the
   time of the runners, the CI can skip drafts:

   ```yaml
   on:
     pull_request:
       types: [opened, synchronize, reopened, ready_for_review]
   jobs:
     checks:
       if: ${{ !github.event.pull_request.draft }}
   ```

9. Commit the files on a new branch, open a pull request, and wait until the required checks of the team pass on it.
   Repair what fails, for example a checker that examines the new files. Then ask the administrator to merge it. Until
   this merge, the main checkout is free to change as the own rules of the repository allow. After it, each change is
   an Akasha task.
10. Tell the person how teammates join: install the plugin once (`/plugin install akasha@akasha`), log in with
    `gh auth login`, and open the repository. The akasha-join skill helps each of them.

## A repository that starts now

The first code of a repository becomes what each later task reads and copies. So the standard comes before the
first code, from fixed text and the answers of the administrator, never from the first AI.

1. `akasha setup --new` writes `docs/architecture.md`. Its six rules are fixed text: do not change them and do
   not add a rule of your own. Ask the administrator each line marked TODO, one at a time, with a proposal that
   they answer with yes or no, and write the answers there: what each area keeps, where a request comes in and
   where the rules and the data are, the shared input and output, errors, tests, and known exceptions. A line
   about a framework names its source in the official documents, or it stays out.
2. A direction of dependency that the guide names goes into `[boundaries]` too, so that the check sees the real
   change and not only the plan. Ask whether the areas may import each other in a circle; if not, add
   `[boundaries.no-cycles]` with `acyclic = ["<the folder of an area>"]`.
3. `akasha.definitions.toml` starts empty, with a correct first example in its head. Tell the administrator in
   simple words what a definition is: one meaning for a number or a feature that more than one screen uses.
4. The lint: tell which rule files only an administrator changes now (`[risk] paths`). For TypeScript, propose
   the rules that the setup names for the config of ESLint. Ask whether the team wants a rule of complexity;
   its limit is of the team.
5. The first task that adds a library adds the lock of its package tool. Propose `[pins] policy = "all"` then.
6. The first area that a task makes is not an example of the team. After a check of its real code, an
   administrator names it in the structure guide, in a task without a screen whose plan names the file, the
   line of the guide that it shows, and the checks that ran.

## The versions of the libraries

When `akasha setup` prints lines that start with `versions —`, some versions float. Before you ask, tell the
person in simple words: what floats, what can happen (the same commit builds differently on another day; a
deployment that goes back installs other versions than before), and what changes when they are fixed (a raise of
a version becomes a task). Then ask which answer fits, and write it into `akasha.toml`: `[pins] policy =
"observe"`, `"new"`, or `"all"`. Propose `"new"` for a repository that has code, and `"observe"` for a library
that others install. Do not choose versions for the team, and do not make a lock from what runs now.

## A repository that has code

The definitions and the boundaries stay off. `akasha map --report` shows what Akasha observes: read it with the
administrator, who decides what becomes a rule. Do not turn an observation into a rule yourself: the direction
of the imports of today is not the right structure for that reason. Each decision is a task of an administrator
without a screen, whose plan the person approves.

## Later changes of the rules

After the setup merged, a change of the rules is a task of an administrator (akasha-build): the preview is a short
page that tells what changes in the rules and why. In the work copy of the task, change `akasha.toml`, run
`akasha setup` there, then check and land. Run `akasha setup --apply` again after the merge when the change touches
the GitHub settings, for example `[ci] required`.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.
