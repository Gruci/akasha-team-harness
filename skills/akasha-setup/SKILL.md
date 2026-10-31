---
name: akasha-setup
description: Set up Akasha in a repository as its administrator: the team rules, the GitHub settings, and the files that bring Akasha to each teammate. Use when the person says "Set up Akasha" or "Akasha 설정해줘", or when the session start notice says that the repository does not use Akasha yet or that the server rules are off.
---

# Set up Akasha (administrator)

The administrator sets up the repository once. After the setup, each teammate only asks for changes and approves
previews. The session start notice gives the Akasha command; this skill writes it as `akasha`. Talk with the person in
their language and in simple words.

## Steps

1. Run `akasha doctor`. Repair each FIX line with the person before you continue.
2. Run `akasha setup`. It writes `akasha.toml` with the usual commands of the main language, and the other files.
3. Ask the person these questions, one at a time, and write each answer into `akasha.toml`:
   - Who are the administrators? (GitHub names) → `[team] admins`
   - Which folders are risky, for example the database, the data writes, the deployment? Who must review a change
     there? → `[risk] paths` and `[team] reviewers`. A change of these paths waits for a reviewer before the merge.
     Keep the list short: each risky path makes a person wait.
   - Does the repository have its own CI on GitHub? What are the names of its required checks? → `[ci] required`.
     Without a CI, Akasha adds its own check, which runs `[checks]` on GitHub.
   - Which commands check a change? → `[checks]`: one table `[checks.<name>]` for each command, with `cwd` and
     `only_when` for a part in its own folder, and the name in `required`.
   - Which team documents must the AI read before the preview (design, words on the screen), before the plan
     (architecture, rules), and for the review? → `[guides] preview`, `plan`, and `review`.
   - Does the repository already use the folder `.akasha/work` or branches that start with `akasha/`? → `[work]`.
4. Run `akasha setup` again. It writes CODEOWNERS and the workflow files from the answers.
5. If the person administers the repository on GitHub, ask them to approve the GitHub changes, then run
   `akasha setup --apply`. It turns on the branch protection, or records that GitHub cannot protect the branch on
   this plan. Tell the person the result in simple words. If the person does not administer the repository, tell them
   to ask an administrator to run it on their own computer.
6. If the team has its own CI, tell the person that each push of a draft pull request starts that CI. To save the
   time of the runners, the CI can skip drafts:

   ```yaml
   on:
     pull_request:
       types: [opened, synchronize, reopened, ready_for_review]
   jobs:
     checks:
       if: ${{ !github.event.pull_request.draft }}
   ```

7. Make a new branch, commit the files that `akasha setup` wrote, open a pull request, and ask the administrator to
   merge it. Before this merge, the main checkout is free to change. After it, each change is an Akasha task.
8. Tell the person how teammates join: install the plugin once (`/plugin install akasha@akasha`), log in with
   `gh auth login`, and open the repository. The akasha-join skill helps each of them.

## Later changes of the rules

After the setup merged, a change of the rules is a task (akasha-build): the preview is a short page that tells what
changes in the rules and why. In the work copy of the task, change `akasha.toml`, run `akasha setup` there, then check
and land. Run `akasha setup --apply` again after the merge when the change touches the GitHub settings, for example
`[ci] required` or the reviewers.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.
