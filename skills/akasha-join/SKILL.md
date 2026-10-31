---
name: akasha-join
description: Help a new teammate get ready to build with Akasha in a repository that an administrator set up. Use when the person is new, says "how do I start", or when the session start notice or akasha doctor shows a problem of this computer.
---

# Join a team that uses Akasha

The administrator set up the repository. The new teammate only needs this computer to be ready. Talk with the person
in their language and in simple words. The session start notice gives the Akasha command; this skill writes it as
`akasha`.

1. If `[guides] join` of `akasha.toml` names files, read them first and help the person through them: the programs,
   the packages, the settings of the network, and the local files that the checks need.
2. Run `akasha doctor`. For each FIX line, help the person in this order:
   - Python 3.11 or higher: install it from python.org (it brings the launcher `py`). Then restart the agent app.
   - The name and the e-mail of git: `git config --global user.name "<name>"` and `user.email`.
   - GitHub CLI: install it from https://cli.github.com.
   - GitHub login: the person runs `gh auth login` in a terminal and follows the browser.
   - git cannot read origin: the person runs `gh auth setup-git`, so that git uses the GitHub login of gh.
   - Write access: an administrator adds the GitHub account of the person to the repository. Tell the person who
     the administrators are (`[team] admins` of `akasha.toml`).
   - A check cannot run here: install what `[guides] join` names for it, for example npm or a Python package.
3. Run `akasha doctor` again until each line is OK.
4. Tell the person how to work, in three lines:
   - Say what you want to make or change, in your own words.
   - The AI shows a preview in the browser. Type "승인" (approve) when it is right, or tell what to change.
   - The AI does the rest. It tells you when the change is merged, and when the deployment of the team put it live.
