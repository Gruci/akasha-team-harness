# Workflows

A workflow is a list of stages. Each stage has exit conditions. A task goes to the next stage only when it meets all the exit conditions of its stage.

## Built-in workflows

| Workflow | Use it for | Stages and exit conditions |
|:--|:--|:--|
| `feature` | A new feature or a changed feature | request (`conditions_clear`) → specification (`requester_approved`, `impact_assessed`, `risk_approvals`) → build (`scope_respected`) → checks (`checks_pass`) → inspection (`accepted`, `map_current`, `infra_ready`) → handover (`merged`) |
| `fix` | A defect | request (`conditions_clear`) → build (`impact_assessed`, `scope_respected`) → checks (`checks_pass`) → inspection (`accepted`, `map_current`, `infra_ready`) → handover (`merged`) |
| `small` | A small change with clear completion conditions | build (`impact_assessed`, `scope_respected`) → checks (`checks_pass`, `map_current`, `infra_ready`) → handover (`merged`) |

## Exit conditions

| Exit condition | What Akasha measures |
|:--|:--|
| `conditions_clear` | The task has one or more completion conditions and no open question |
| `requester_approved` | The requester approved the specification |
| `impact_assessed` | The impact analysis has all five parts: features, data, contracts, tasks, and rollback |
| `risk_approvals` | Each gate role that `[approval]` names for the risk level of the task approved |
| `scope_respected` | Each changed file in the work copy matches the scope. The team context, for example the product map, is outside each scope. A task without a scope permits all files |
| `checks_pass` | Each required check passed, and no check failed |
| `accepted` | The requester accepted each completion condition |
| `map_current` | The change updates the product map, or the task records why the map does not change |
| `infra_ready` | The required check, branch protection, auto-merge, and the server files on the default branch agree with the team config |
| `pull_request_open` | The pull request of the task is open. The built-in workflows do not use it |
| `merged` | GitHub merged the pull request of the task |

## How the risk level changes

Akasha sets the risk level from the scope when the task starts. Each time the task tries to advance, Akasha examines the real changed files again. The risk level can go up. It never goes down.

When `[approval]` names a gate for a risk level, Akasha examines the gate at each advance after the build starts. Thus a risk that the real changes raise still needs the approval of the gate.

## Failed repairs

Each failed check counts as one failed repair. After three failed repairs, Akasha stops the task.

1. The agent engine stops the work and tells the requester in simple words.
2. A developer examines the problem.
3. The developer tells the agent engine to continue. The agent engine runs `resume`, and the count starts again at zero.

## Change a workflow

1. Make the folder `.akasha/workflows/` in your repository.
2. Write one TOML file for each workflow. For example:

   ```toml
   name = "feature"

   [[stages]]
   id = "request"
   exit = ["conditions_clear"]

   [[stages]]
   id = "build"
   exit = ["impact_assessed", "scope_respected"]

   [[stages]]
   id = "checks"
   exit = ["checks_pass", "map_current", "infra_ready"]

   [[stages]]
   id = "handover"
   exit = ["merged"]
   ```

3. Commit the file. A team workflow with the name of a built-in workflow replaces the built-in workflow.
4. To permit only some workflows, write them in `akasha.toml`:

   ```toml
   [workflows]
   enabled = ["feature", "fix"]
   ```

Akasha refuses a workflow with an unknown exit condition, a workflow without stages, and a workflow with two stages that have the same id.

> **CAUTION:** Keep the stage ids `build` and `handover`. Akasha makes the work copy when a task enters `build`. The handover command operates only at `handover`. Put `infra_ready` before `handover`, because auto-merge needs the server rules.
