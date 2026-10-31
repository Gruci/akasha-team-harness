# Akasha documents

| Document | Read it when |
|:--|:--|
| [How it works](how-it-works.md) | You want to know the steps of a task, what Akasha stops, and where it keeps its data |
| [Set up a team](admin.md) | You are the administrator and set up a repository, or change its rules |
| [Team config](team-config.md) | You write or change `akasha.toml` |
| [Commands](commands.md) | You want to know each command of Akasha. The agent engine runs them; people do not have to |

The procedures that the agent engine follows are in [`skills/`](../skills), and the reviewer of the plans is in
[`agents/`](../agents).

## Run the tests of Akasha

```
python -m unittest discover -s tests -t .
```
