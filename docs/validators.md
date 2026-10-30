# Validators

The validators change each rule that a machine can examine into a check. They operate at two places: in the hooks of the agent engine during the work, and in the required checks.

## The guard

The guard examines each shell command and each edit before it runs. It stops these commands:

| Command | Reason |
|:--|:--|
| `git push --force`, `-f`, `--force-with-lease`, a bundled flag such as `-fu`, or a `+` refspec | A force push replaces history on the server |
| `git push --delete main`, `git push -d main`, or `git push origin :main` | It deletes the default branch on the server |
| `git branch -d main`, `-D`, or `--delete` | It deletes the default branch |
| `rm -r`, `Remove-Item -Recurse`, `rd /s`, or `del /s` on the whole project, on a folder outside the project, or on `*` | It deletes data that Akasha cannot restore |
| A recursive delete of a path with a variable, for example `$HOME` or `%USERPROFILE%` | Akasha cannot see the target |
| A recursive delete after `cd` or `Set-Location` in the same command | Akasha cannot see the target |

The default branch is `main` or `master`. The guard reads a command that goes on in the next line as one command. It reads `;`, `&`, `&&`, `|`, and `||` as separators.

The guard also stops an edit in the main checkout while a task is at the build stage or at the checks stage. The agent engine must make the change in the work copy of the task. Edits of the task state in `.akasha/state/` are permitted.

## The secret check

The secret check finds secret keys in files. It finds these kinds:

- OpenAI and Anthropic keys
- GitHub tokens
- AWS access keys
- Slack tokens
- Google API keys
- Private keys

It runs at two times:

1. After each edit of the agent engine. When it finds a key, it tells the agent engine to remove the key and read it from the environment.
2. As the required check `secrets`, on each changed file of the task. File names with Korean or other non-ASCII letters are included.

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

The check runner runs the required checks in the work copy of the task. Each check gets one result.

| Result | Meaning |
|:--|:--|
| PASS | The check passed |
| FAIL | The check failed. A FAIL counts as one failed repair |
| SKIP | The team config has no command for the check. SKIP is not a pass |

A check command that does not stop in 30 minutes gets the result FAIL. Akasha then stops the command and all the processes that it started. The runner keeps the last 3000 characters of the output for the agent engine.

## Language packs

A language pack gives the default commands for one language. `setup` writes them into `akasha.toml` when git tracks files of that language. When the repository has files of more than one language, `setup` uses the first pack in alphabetical order.

| Pack | File extensions | Setup | Tests | Lint |
|:--|:--|:--|:--|:--|
| Go | `.go` | `go mod download` | `go test ./...` | `go vet ./...` |
| Java | `.java`, `.kt` | — | `./gradlew test` | `./gradlew check` |
| Python | `.py` | `python -m pip install -r requirements.txt` | `python -m pytest -q` | `python -m ruff check .` |
| TypeScript | `.ts`, `.tsx`, `.js`, `.jsx` | `npm ci` | `npm test --silent` | `npx eslint .` |

`setup` writes the setup command as a comment. When the command is correct for your project, remove the `#`. On Windows, Akasha runs a command that starts with `./` as `.\`.

For a language without a pack, write the commands in `[checks]` of `akasha.toml`. To add a pack to Akasha, add one TOML file to `akasha/validators/packs/`:

```toml
name = "rust"
extensions = [".rs"]
setup = "cargo fetch"
tests = "cargo test"
lint = "cargo clippy -- -D warnings"
```

> **CAUTION:** The guard and the hooks keep a cooperative agent engine on the rules. They are not a sandbox. A merge cannot go around the required check on the server.
