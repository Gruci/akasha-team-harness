## Your step: the build and the checks

Build what `plan.md` says, in the work copy. Read the files of `[guides] build` first. Write a test for each example
of the rules and each value that the person approved, with the expected values that they approved. Never build the
boxes or the marks of the preview into the product. Run `<Akasha command> check <task>` and repair each failure. When
the check asks for a row in "Public changes" of the plan, or the plan must change in another way, stop and return
that: the plan needs its review again, and the main session decides.

When the check passes, write `summary.md` in the records folder: why, what changed, and how to undo it when a revert
is not enough. Run the check again.

Return the output of `<Akasha command> status <task> --brief`, then the files that you changed.
