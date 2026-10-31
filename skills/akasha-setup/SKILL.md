---
name: akasha-setup
description: Set up Akasha in a repository, or turn on its server rules. Use when the user says "Set up Akasha" or "Akasha 설정해줘", or when the session start notice says that the repository does not use Akasha yet or that its server rules are off, or when Akasha says that the GitHub app of Akasha is not set up.
---

# Set up Akasha

The session start notice gives the Akasha command. This skill writes it as `akasha`.

Akasha examines the repository first. Do only the part that the repository needs.

## Procedure

1. Run `akasha setup`.
2. If Akasha says that the repository is ready, tell the user that Akasha is ready. If Akasha also says that it updated `AGENTS.md` or `.codex/hooks.json`, an update of Akasha changed the files that Codex reads, or Akasha removed a byte order mark from `.codex/hooks.json`: a JSON reader can refuse it. If Akasha says that it added a folder to `.gitignore`, the team changed `[work]`. Then make a new branch, commit these files on it, and open a pull request. Stop here.
   Akasha keeps the other text of `AGENTS.md` and the other hooks in `.codex/hooks.json`. If Akasha says that `.codex/hooks.json` is not JSON, tell the user: Akasha did not change it. The user repairs the file or removes it. Then run `akasha setup` again.
   If Akasha says that this checkout is old, tell the user to pull the default branch with the command that Akasha shows. If Akasha says that a newer Akasha wrote the files, tell the user to update Akasha, then run `akasha setup` again. Do not change these files yourself.
   If Akasha says that git tracks files in the work folder of `[work]`, tell the user: an administrator sets `[work] folder` in `akasha.toml` to a folder that git does not track. Then run `akasha setup` again.
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
   - If the warning says that a CODEOWNERS line of the team has no effect on some files, tell the administrator which line. The Akasha block decides the owners of these files.
   - If the warning says that the GitHub app of Akasha is not set up, tell the administrator to make it. Do the steps in [Make the GitHub app of Akasha](#make-the-github-app-of-akasha).
   - If the user is an administrator, ask the user to approve the GitHub changes. Then run `akasha setup --approve-infra <GitHub name>`. The name must be the GitHub account of this computer: Akasha asks GitHub, and only an administrator of the repository can change the settings. If this output shows a GitHub warning, tell the user before the pull request.
6. Make a new branch. Commit the new and changed files on it and open a pull request.
   The files are `akasha.toml`, `.akasha/context/map/README.md`, `AGENTS.md`, `.codex/hooks.json`, `.gitignore`, and the files in `.github/`.
7. Ask an administrator to merge the pull request. Then run `akasha infra`. Make sure that it shows no problem.

> **CAUTION:** Do not change the GitHub settings without the approval of an administrator.

> **NOTE:** Codex needs Akasha installed with pip: `pip install "git+https://github.com/Gruci/akasha-team-harness@v1.0.0"`.

## Make the GitHub app of Akasha

The helper workflows of Akasha use the token of this app. With the app, the pull requests of the tasks come up to date when the default branch moves, and a merge of the helpers starts the other workflows, for example a deployment. Make the app in each repository, also when GitHub merges.

An administrator of the repository does these steps on GitHub. Tell the steps to the administrator one at a time.

1. On GitHub, open **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**. For a repository of an organization, open the settings of the organization.
2. Give the app a name, for example `akasha-<repository>`, and a homepage URL, for example the address of the repository. Clear **Webhook** → **Active**.
3. Give the app these repository permissions. Then select **Only on this account**, and **Create GitHub App**.

   | Permission | Access |
   |:--|:--|
   | Contents | Read and write |
   | Pull requests | Read and write |
   | Issues | Read and write |
   | Workflows | Read and write |
   | Checks | Read-only |

4. On the page of the app, select **Generate a private key**. GitHub downloads a `.pem` file.
5. Select **Install App**, then the account of the repository. Select **Only select repositories**, and the repository.
6. Ask the administrator for the Client ID on the page of the app. Run `gh variable set AKASHA_APP_CLIENT_ID --body <Client ID>`.
7. Tell the administrator to run this command in a terminal: `gh secret set AKASHA_APP_KEY < <path of the .pem file>`. Then the administrator deletes the `.pem` file, or keeps it in a safe place.
8. Run `akasha infra`. Make sure that it does not show the notice about the GitHub app.

> **CAUTION:** Do not open or read the private key. Only the administrator stores it.

> **NOTE:** Without the Workflows permission, the helpers cannot merge or undo a change in `.github/workflows/`. Without the app, the secret `AKASHA_TOKEN` with a token of a person also starts other workflows, but the token belongs to that person.
