# Akasha documents

| Document | Read it when |
|:--|:--|
| [Architecture](architecture.md) | You want to know how the parts connect and where Akasha keeps its data |
| [Workflows](workflows.md) | You want to change the stages or the exit conditions |
| [Team config](team-config.md) | You write or change `akasha.toml` |
| [Roles](roles.md) | You want to know who decides what, and how Akasha counts a decision comment |
| [Coordination](coordination.md) | Many requesters work in one repository, or a task goes to another person or another computer |
| [Validators](validators.md) | You want to know what Akasha examines and stops |
| [Infrastructure](infrastructure.md) | You set up or examine the GitHub settings |

The procedures that the agent engine follows are in [`skills/`](../skills).

## Run the tests of Akasha

```
python -m unittest discover -s tests -t .
```
