# Validators

The validators change each rule that a machine can examine into a check. They operate at two places: in the hooks of the agent engine during the work, and in the required checks.

The hooks operate in a repository when its checkout has `akasha.toml`. They also operate when only the default branch on the server has it, for example after the setup pull request merged and before the person pulls it. For this test, the hooks use no network: they read the default branch as git fetched it last.

## The guard

The guard examines each shell command and each edit before it runs. It stops these commands:

| Command | Reason |
|:--|:--|
| `git push --force`, `-f`, `--force-with-lease`, a bundled flag such as `-fu`, or a `+` refspec | A force push replaces history on the server |
| `git push --delete main`, `git push -d main`, or `git push origin :main` | It deletes the default branch on the server |
| `git branch -d main`, `-D`, or `--delete` | It deletes the default branch |
| `git push origin main` or `git push origin HEAD:main` | It pushes straight to the default branch. Akasha merges each change through a pull request |
| `rm -r`, `Remove-Item -Recurse`, `rd /s`, or `del /s` on the whole project, on a folder outside the project, or on `*` | It deletes data that Akasha cannot restore |
| A recursive delete of a path with a variable, for example `$HOME` or `%USERPROFILE%` | Akasha cannot see the target |
| A recursive delete after `cd` or `Set-Location` in the same command | Akasha cannot see the target |
| `git push` to a task branch `akasha/<task>` or `akasha-wip/<task>`, or to a branch with a prefix of `[work]` in `akasha.toml`, or to the branch of a task on this computer, also to delete it; `git push --all` or `--mirror`; and `git push` without a branch, or to `HEAD`, in a work copy | Akasha pushes the task branches itself, also the branch of the task of the agent engine. The task branch on the server always passed the checks |
| `gh pr merge`, a merge through `gh api` (`pulls/<number>/merge`, or the GraphQL `mergePullRequest`), or the GraphQL `enablePullRequestAutoMerge` | GitHub, or the merge workflow of Akasha, merges each pull request when the server check passes |
| `gh pr create`, `gh pr edit`, `gh issue create`, or `gh issue edit` that gives the label `akasha-merge`, `gh api` on `issues/<number>/labels` with that label, or the GraphQL `addLabelsToLabelable` | Akasha gives the label at the handover. Where GitHub has no auto-merge, the merge workflow of Akasha merges each pull request with the label |
| `gh issue comment`, `gh pr comment`, or `gh api` on comments, with a line that starts with `/approve`, `/accept`, `/reject`, `/resume`, or `/cancel` | A decision counts only from the GitHub account of the person who decides. The guard also reads the file of `--body-file`, `--input`, or `@<file>` |
| `gh issue comment --edit-last` or `--delete-last`, `gh api` with `PATCH` or `DELETE` on `issues/comments/<id>`, or the GraphQL `updateIssueComment`, `deleteIssueComment`, or `minimizeComment` | When a comment changes or goes away, a later decision can stop counting, and an earlier decision counts again |
| `gh issue edit` with `--body` or `--body-file`, `gh api` with `PATCH` on `issues/<number>`, or the GraphQL `updateIssue` | The issue of an Akasha task holds the state of the task, and Akasha writes it itself |

The default branch is `main` or `master`. The guard reads the git command after the flags of git, so `git stash push` is not a push. The guard reads a command that goes on in the next line as one command. It reads `;`, `&`, `&&`, `|`, and `||` as separators. It also reads a command after variables, for example `GH_REPO=team/app gh pr merge 5` or `env X=1 git push`, and a `gh` command after `-R <repository>`. For `git push` without a branch, the folder is the folder of the command, the folder after `cd` or `Set-Location` in the same command, or the folder of `git -C <folder>`. A work copy is in `.akasha/work/` or in the work folder of `[work]`. For the prefixes and the work folder, the guard reads the team config on the default branch as git fetched it last, else in the checkout.

A push to another branch, for example `git push origin feature-x`, and a comment that only names a decision in a sentence are permitted. When the person who decides is the GitHub account of this computer, the agent engine runs the Akasha command `approve`, `accept`, `resume`, or `cancel`. Akasha writes the decision comment in Python, so the guard does not stop it.

The guard also stops an edit in the main checkout while a task is at the build stage or at the checks stage and its work copy is on this computer. The agent engine must make the change in the work copy of the task. After a handoff, the task has no work copy on this computer, and the guard does not stop the edit. Edits of the task state in `.akasha/state/` are permitted.

## The secret check

The secret check finds secret keys in files. It finds these kinds:

- OpenAI and Anthropic keys
- GitHub tokens
- AWS access keys
- Slack tokens
- Google API keys
- Private keys

It runs at two times:

1. After each edit of the agent engine. When it finds a key, the hook sends the edit back to the agent engine with exit code 2, and tells it to remove the key and read it from the environment.
2. As the required check `secrets`, on each changed file of the task. File names with Korean or other non-ASCII letters are included.

## The overlap notice after an edit

The same hook after each edit also compares the file with the scopes of the other open tasks. When the file is in the work copy of a task and in the scope of another task, the hook tells the agent engine. The notice does not stop the work: the hook gives it as additional context with exit code 0. Claude Code and Codex give that context to the agent engine. When the hook also finds a secret key, the notice goes into the same message. Each pair of tasks gets the notice once. [Coordination](coordination.md#during-the-work) tells which files and tasks count.

## The briefing check

The `brief` command examines the briefing before the handover:

| Rule | Limit |
|:--|:--|
| Headings | `## Why`, `## What changed`, `## Scope`, `## Tradeoffs`, and `## Blast Radius`, in this order. Only Tradeoffs is optional |
| Verification | Not permitted. Akasha writes it from the real results |
| Text before the first heading | Not permitted |
| Bold lead-ins | Not permitted. Use headings |
| Length of each section | Why: 1 to 3 sentences. What changed, Scope, and Tradeoffs: 1 to 3 items. Blast Radius: 1 or 2 sentences |
| Sentence length | 25 words or fewer |
| Commit hashes and branch history | Not permitted |
| Total | 34 lines or fewer, so that the commit body with Verification stays under 40 lines |

## The check runner

The check runner runs the required checks in the work copy of the task. The server check uses the same runner on the files that the pull request changes. Each check gets one result.

| Result | Meaning |
|:--|:--|
| PASS | The check passed |
| FAIL | The check failed. A FAIL counts as one failed repair. A check whose `cwd` folder does not exist also fails |
| SKIP | The team config has no command for the check. SKIP is not a pass |
| NOT_NEEDED | The check has `only_when`, and the change touches no file that matches it or `run_all_when`. The check did not run. NOT_NEEDED is a pass |

The exit condition `checks_pass`, `check`, `handover`, and the server check use one rule: the result has one or more checks, and each check is PASS or NOT_NEEDED.

Each check runs in its `cwd` folder, else at the top of the work copy. The command runs in the shell of the operating system: `cmd.exe` on Windows, and `/bin/sh` on macOS and Linux. On Windows, `command_windows` replaces `command` when the check has it. [Team config](team-config.md) tells the keys of a check.

A check command that does not stop in 30 minutes gets the result FAIL. Akasha then stops the command and all the processes that it started. The runner keeps the last 3000 characters of the output for the agent engine.

When each check passes or is NOT_NEEDED, Akasha saves the work as a commit and pushes the task branch. It saves nothing while the work copy has a file outside the scope, for example a file that a test made. The handover stops for the same reason and names the files.

## Language packs

A language pack gives the default commands for one language. `setup` writes them into `akasha.toml` as the one-line checks `tests` and `lint` when git tracks files of that language. When the repository has files of more than one language, `setup` uses the first pack in alphabetical order.

| Pack | File extensions | Setup | Tests | Lint |
|:--|:--|:--|:--|:--|
| Go | `.go` | `go mod download` | `go test ./...` | `go vet ./...` |
| Java | `.java`, `.kt` | — | `./gradlew test` | `./gradlew check` |
| Python | `.py` | `python -m pip install -r requirements.txt` | `python -m pytest -q` | `python -m ruff check .` |
| TypeScript | `.ts`, `.tsx`, `.js`, `.jsx` | `npm ci` | `npm test --silent` | `npx eslint .` |

`setup` writes the setup command as a comment. When the command is correct for your project, remove the `#`. On Windows, Akasha runs a command that starts with `./` as `.\`.

Each pack also names the files that its tests and builds make, for example `__pycache__/` for Python and `node_modules/` for TypeScript. `setup` adds them to `.gitignore` when git does not ignore them yet, so that they never go into a commit.

For a language without a pack, write the commands in `[checks]` of `akasha.toml`. To add a pack to Akasha, add one TOML file to `akasha/validators/packs/`:

```toml
name = "rust"
extensions = [".rs"]
setup = "cargo fetch"
tests = "cargo test"
lint = "cargo clippy -- -D warnings"
ignore = ["target/"]
```

> **CAUTION:** The guard and the hooks keep a cooperative agent engine on the rules. They are not a sandbox. A merge cannot go around the required check on the server.
