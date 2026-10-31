---
name: akasha-join
description: Help a new teammate get ready to build with Akasha in a repository that an administrator set up. Use when the person is new, says "how do I start", or when the session start notice or akasha doctor shows a problem of this computer.
---

# Join a team that uses Akasha

The administrator set up the repository. The new teammate only needs this computer to be ready. Talk with the person
in their language and in simple words. The session start notice gives the Akasha command; this skill writes it as
`akasha`.

1. Run `akasha doctor`. For each FIX line, help the person in this order:
   - Python 3.11 or higher: install it and put it first on PATH. Then restart the agent app.
   - GitHub CLI: install it from https://cli.github.com.
   - GitHub login: the person runs `gh auth login` in a terminal and follows the browser.
   - Write access: an administrator adds the GitHub account of the person to the repository. Tell the person who
     the administrators are (`[team] admins` of `akasha.toml`).
   - A program of a check, for example npm: install it.
2. Run `akasha doctor` again until each line is OK.
3. Tell the person how to work, in three lines:
   - Say what you want to make or change, in your own words.
   - The AI shows a preview in the browser. Say "승인" (approve) when it is right, or tell what to change.
   - The AI does the rest and tells you when the change is live.
