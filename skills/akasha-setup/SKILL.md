---
name: akasha-setup
description: Set up Akasha in a repository. Use when the user says "Set up Akasha" or "Akasha 설정해줘", or when the session start notice says that the repository has no akasha.toml.
---

# Set up Akasha

The session start notice gives the Akasha command. This skill writes it as `akasha`.

## Procedure

1. Run `akasha setup`. Akasha writes `akasha.toml`, the product map, and the files that Codex reads.
2. Read `akasha.toml`.
3. Ask the user these questions. Ask one question at a time.
   - Which GitHub names are the administrators?
   - Which folders contain high-risk code, for example data changes, permissions, or payments?
   - Must a person approve a change in these folders before the merge? If yes, which GitHub names?
   - Which command starts a preview of the product?
   - Which command installs the dependencies of the project in a new copy?
   - Which command runs the tests?
4. Write each answer into `akasha.toml`. For a person gate, write the names in `[roles] developers` and remove the `#` in `[approval]`.
5. Run `akasha infra`. Tell the user each setting that is not correct.
6. Ask an administrator to approve the GitHub changes.
7. After the approval, run `akasha setup --approve-infra <administrator>`.
   Akasha writes the server files, sets branch protection, and turns on auto-merge.
8. Make a new branch. Commit the new files on it and open a pull request.
   The new files are `akasha.toml`, `.akasha/context/product-map.md`, `AGENTS.md`, `.codex/hooks.json`, `.gitignore`, and the files in `.github/`.
9. Ask an administrator to merge the pull request. Then run `akasha infra` again. Make sure that it shows no problem.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.

> **NOTE:** Codex needs Akasha installed with pip: `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.
