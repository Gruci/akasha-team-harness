## Your step: the landing

Run `<Akasha command> land <task> --wait 540` with a shell timeout of 10 minutes. While it says WAITING or DEPLOYING,
run it again. Stop at each other result, and return it: MERGED, DEPLOYED, CLOSED, ASK (the person approves the result
of an agent task: the main session asks), FAILED, CONFLICT, BLOCKED, DEPLOY_FAILED, or VERIFY_FAILED, with the lines
that the command printed. Do not repair the code here: a failed check or a conflict goes back to the build step.

Return one line: the result, and what the main session does next.
