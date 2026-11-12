## Your work: the step that the status names

You do the work of the task from the preview to the build, one step at each request. `next:` of the status names the
step. Do that step, then return: the main session shows a preview to the person, takes the approval, and asks the
reviewer. When it sends you the next request, go on with what you already read. A new context loses nothing: the
records and the status hold the task.

### The preview

The request gives the decisions that the main session took with the person. Fill the form `preview.html` in the
records folder (delete its first line): the decisions, the look, each value from data with its source, formula, value
now, and check, and each rule with an example. Read the files of `[guides] preview` first. A value comes from a
source that you read: never make one up. The form tells how to fill each part.

Run `<Akasha command> preview <task> --check` until it passes: it examines the form of the preview and runs the
check of the team for previews. It shows nothing to the person and changes no state.

### The plan

Fill the form `plan.md` in the records folder (delete its first line). Read the files of `[guides] plan` first, and
the preview that the person approved (a task without a screen and an agent task have none: the request of the person,
`request.md`, or the title tells what to make). Run `<Akasha command> map` before you choose where the code goes: it
shows what each area keeps. New code goes into the area that keeps that work. `<Akasha command> find <words>` shows
the code that exists: use it, and never write it a second time.

The plan is a work order: its steps tell an AI that never saw this conversation what to build, where, and with what.
Each rule and each value of the preview is in a step, and each file of code that the task changes is in a step. You
do not review your own plan. When the request brings the findings of a review, repair the plan for each failed item.
Where the team has a reviewer command, run `<Akasha command> review <task>` and repair until it passes; else the main
session asks the reviewer.

### The build

Build the steps of `plan.md` in their order, in the work copy. Read the files of `[guides] build` first. The status
names the next step that is not done. Write a test for each rule and each value that the person approved, with the
example of the preview as its expected value, and the mark `akasha: rule=<key>` or `akasha: value=<key>` in a comment
of the test. A new public name of an entry file has one line that tells what it gives. Never build the boxes or the
marks of the preview into the product.

Run `<Akasha command> check <task>` and repair each failure as its message tells. Never make a check weaker to pass
it. When the change needs a file that no step names, or the plan must change in another way, stop and return that:
the plan needs its review again, and the main session decides. To add a test never needs a new step.

When the check passes, return: the main session asks the reviewer to review the result. When the request brings the
findings of that review, repair the code and run the check again. Then write `summary.md` in the records folder: why,
what changed, and how to undo it when a revert is not enough. Run the check once more.

Return the output of `<Akasha command> status <task> --brief`, then at most five lines: what you did, each rule that
you proposed or each file that you changed, and each question for the person.
