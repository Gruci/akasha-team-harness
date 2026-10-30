---
name: akasha-setup
description: Set up Akasha in a repository, or turn on its server rules. Use when the user says "Set up Akasha" or "Akasha 설정해줘", or when the session start notice says that the repository does not use Akasha yet or that its server rules are off.
---

# Set up Akasha

The session start notice gives the Akasha command. This skill writes it as `akasha`.

Akasha examines the repository first. Do only the part that the repository needs.

## Procedure

1. Run `akasha setup`.
2. If Akasha says that the repository is ready, tell the user that Akasha is ready. Stop here.
   If Akasha says that the default branch on the server already has `akasha.toml`, the setup is done, and this checkout is old. Tell the user to pull the default branch with the command that Akasha shows. Then run `akasha setup` again.
3. If Akasha wrote `akasha.toml`, the repository did not use Akasha yet. Ask the user these questions. Ask one question at a time.
   - Which GitHub names are the administrators?
   - Which folders contain high-risk code, for example data changes, permissions, or payments?
   - Must a person approve a change in these folders before the merge? If yes, which GitHub names?
   - Which command starts a preview of the product?
   - Which command installs the dependencies of the project in a new copy?
   - Which command runs the tests?
4. Write each answer into `akasha.toml`. For a person gate, write the names in `[roles] developers` and remove the `#` in `[approval]`.
5. Read the last lines of the output of `akasha setup`:
   - If the owner must change the plan or make the repository public, tell the user. The server rules cannot go on before that.
   - If the user is not an administrator, tell the user to ask an administrator. The work can start now. The handover waits for the server rules.
   - If Akasha shows a GitHub warning, tell the user. A warning does not stop the work or the handover.
   - If the user is an administrator, ask the user to approve the GitHub changes. Then run `akasha setup --approve-infra <GitHub name>`. The name must be the GitHub account of this computer: Akasha asks GitHub, and only an administrator of the repository can change the settings.
6. Make a new branch. Commit the new and changed files on it and open a pull request.
   The files are `akasha.toml`, `.akasha/context/map/README.md`, `AGENTS.md`, `.codex/hooks.json`, `.gitignore`, and the files in `.github/`.
7. Ask an administrator to merge the pull request. Then run `akasha infra`. Make sure that it shows no problem.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.

> **NOTE:** Codex needs Akasha installed with pip: `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.
