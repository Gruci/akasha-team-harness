# Architecture

The standard of this repository for where code goes and what it may depend on. An administrator keeps it: a task of
a teammate does not change this file (`[risk] paths`). The AI reads it before each plan, and the reviewer judges each
plan against it (R7). A task makes new folders and files freely inside these rules. Only a change of a
responsibility, of an allowed dependency, or of a public contract is a task of an administrator.

Each line marked TODO waits for the answer of an administrator. Write no line about a framework without its source
(the place in its official documents).

## The rules

{card}

## The areas

- The folder of one area: {areas}
- The entry of an area, the only file of it that other areas import: {entries}
- What each area keeps: its sheet, the file `area.toml` in its folder, tells it in one line, with the areas that it
  uses and the tables that it writes. `akasha map` shows each sheet with what the code shows. A task that makes a
  new area writes its sheet, and an administrator approves it (the first line of its entry file says the same)

## Inside an area

- Where a request comes in, where the rules of the business are, and where data is read and written: TODO (folders
  or files. A small product needs no layers)

## Shared input and output

- The connection to the database, the login, the calls to outside systems, and the function with which a screen
  calls the server: TODO

## Errors and the check of input

- Where input is checked, where an error is made, and what happens when a step fails: TODO

## Tests

- Where the tests are, the shape of a contract test, and how a test stands in for an outside system: TODO

## New libraries

- The plan of a task names each new library and why the task needs it.

## Examples of the team

- None yet. Follow this document, not the code that is there. An administrator names an example here after a check
  of its real code: the file, and what to take from it.

## Known exceptions

- TODO, or none (a path that new code does not use, and the entry to use in its place)
