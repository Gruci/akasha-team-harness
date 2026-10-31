---
name: akasha-setup
description: Set up Akasha in a repository as its administrator: the team rules, the GitHub settings, and the files that bring Akasha to each teammate. Use when the person says "Set up Akasha" or "Akasha 설정해줘", or when the session start notice says that the repository does not use Akasha yet or that the server rules are off.
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
3. Run `akasha setup`. It writes `akasha.toml` with the usual commands of the main language, and the other files.
   Where GitHub does not protect the default branch now, it records `[server] rules = "akasha"` and adds the watch.
4. Read the own agent rules of the repository: `CLAUDE.md`, `AGENTS.md`, `.claude/skills/*/SKILL.md`, the hooks in
   `.claude/settings.json`, and the documents they point to. List each rule about scope interviews, a plan approval by
   a person, where plans, research, and mockups go, worktrees, task boards, and pushes, pull requests, and merges.
   With the person, replace each one in this change with a pointer to Akasha. Akasha already wrote its own block into
   `CLAUDE.md` and `AGENTS.md`, with a sentence that its procedure comes first; the old rules must not say otherwise.
   Keep the design and architecture documents: they go into `[guides]` in step 5.
5. Ask the person these questions, one at a time, and write each answer into `akasha.toml`:
   - Who are the administrators? (GitHub names) → `[team] admins`. They review each change of `akasha.toml` and
     `.github/`.
   - Which folders are risky, for example the database, the data writes, the deployment? Who must review a change
     there? → `[risk] paths` and `[team] reviewers`. A change of these paths waits for a reviewer before the merge.
     Keep the list short: each risky path makes a person wait. Name two or more reviewers, so that a reviewer who
     makes a change can get a review from another one.
   - Does the repository have its own CI on GitHub? What are the names of its required checks, as GitHub shows the
     jobs (for example `checks`, not the name of the workflow)? → `[ci] required`. Without a CI, Akasha adds its own
     check, which runs `[checks]` on GitHub.
   - Which commands check a change? → `[checks]`: one table `[checks.<name>]` for each command, with `cwd` and
     `only_when` for a part in its own folder, and the name in `required`.
   - What must each computer install to run these checks (packages, versions, settings of the network, local files
     such as `.env`)? → `[checks] setup` for the commands, `ready` in each check for a quick test that the computer can
     run it, and a short document for `[guides] join`.
   - Which team documents must the AI read before the preview (design, words on the screen), before the plan
     (architecture, rules), and for the review? → `[guides] preview`, `plan`, and `review`.
   - Does a checker of the repository examine Markdown or other files that it finds by their folder? The records of
     each task (preview, research, plan, summary) go into git. → `[work] records`: a folder that those checkers skip,
     for example `docs/tasks/akasha`.
   - Does a workflow deploy each merge to the default branch? → `[deploy] workflow`: its name, as GitHub shows it.
     Then Akasha tells the person when the change is live, not only merged.
   - Does the repository already use the folder `.akasha/work` or branches that start with `akasha/`? → `[work]`.
6. Run `akasha setup` again. It writes CODEOWNERS and the workflow files from the answers.
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

## Later changes of the rules

After the setup merged, a change of the rules is a task (akasha-build): the preview is a short page that tells what
changes in the rules and why. In the work copy of the task, change `akasha.toml`, run `akasha setup` there, then check
and land. An administrator reviews it before the merge. Run `akasha setup --apply` again after the merge when the
change touches the GitHub settings, for example `[ci] required` or the reviewers.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.
