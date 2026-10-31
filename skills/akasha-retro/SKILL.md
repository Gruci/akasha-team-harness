---
name: akasha-retro
description: Find what stops the work of the team again and again, and turn it into a check of the team. Use when an administrator asks for a retro, or says that the same failure keeps coming back.
---

# Retro: grow the checks from the problems

A team starts with few checks: the commands that it already has. A rule grows when the same problem comes back. Talk
with the administrator in their language.

1. Run `akasha retro`. It shows the checks that failed most, the checks that passed on a computer and failed on
   GitHub, the actions that Akasha stopped, and the review rounds of the plans.
2. For each repeated problem, find the cause in the records of the tasks (`.akasha/tasks/<task>/`) and in the code.
3. Tell the administrator, in simple words, which problem repeats and what one check would stop it before the merge.
   A check is a command that fails on the problem, for example a test or a small script.
4. When the administrator agrees, add the check as an Akasha task (akasha-build): the preview is a short page that
   shows the problem and what the new check reports. The check goes into `[checks]` of `akasha.toml`.
5. When a new check finds problems in the existing code, keep a list of the existing problems that the check accepts,
   and let the list only get shorter. Else the first day of the check stops each task.
