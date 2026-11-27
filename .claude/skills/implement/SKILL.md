---
name: implement
description: Implement a ticket from its spec in slices, pausing after each passing slice for the developer to commit
argument-hint: TNN
disable-model-invocation: true
---

Implement the ticket: $ARGUMENTS

The spec `specs/TNN-*.md` is the contract. Build what it says, test every acceptance criterion, and
keep the spec true when reality forces a change. The developer does every git operation: you
never stage, commit, push or create branches.

## 1. Start
- This should run in a fresh session, with only the spec as context. If this conversation already
  holds other work, tell the developer to start a new session and stop.
- Read `CLAUDE.md` and the spec. If the spec has an unanswered question, an empty "How", "Tested
  by" or "Browser", an `E2E n` with no scenario n under `## E2E scenarios`, or contradicts the
  code, stop and say what is missing (`/spec TNN` fixes it).
- `git status` and `git branch --show-current`: the branch should be `feature/TNN-<slug>` and the
  tree clean. If not, tell the developer and stop; don't create the branch.

## 2. Plan
- If the spec has a Commit plan, continue from its first unticked slice.
- Otherwise, if the ticket fits in one or two commits, skip the plan and treat the ticket as one slice.
- Otherwise write a `## Commit plan` at the end of the spec, 3-8 slices:
  - Each slice works on its own: the build, lint, typecheck and tests pass after it.
  - Each names the acceptance criteria it covers. Together they cover every row of the table.
  - Order: foundations first (models + migration, config, generated types), then the features, the
    things a demo needs last.
  - Format: `- [ ] N. <what> — <criteria> — \`<commit message>\``. The commit message follows the
    repo's style (`git log --oneline -15`): lowercase, starts with a verb, lists what was added.
- Show the plan and wait for the developer's OK before writing code.

## 3. Each slice
1. Write the code and its tests together. Every acceptance criterion the slice covers gets at
   least one test, in the file named in "Tested by".
2. Follow `CLAUDE.md`: layout by feature, typed, thin routers, async, settings via `Settings`,
   migrations from `make revision`, no AWS or DB in unit tests. Fix whatever the edit hook reports.
3. Run the checks: `make test-unit`, plus `make check` when the slice touches the DB, plus the
   lint / typecheck / test / build commands of any other part of the repo the slice touches (e.g.
   the frontend's). All green before going on; fix failures, don't skip or weaken tests.
4. Tick the slice in the spec (`- [x]`) and update the commit message if the slice changed.
5. Stop and report: what changed (files grouped by area), the checks run with their results, and
   the commit message to use. Ask the developer to commit and say "continue".
6. On "continue": `git status` and `git log -1` to confirm the slice is committed. If its files
   are still uncommitted, say so and wait. Then start the next slice.

## 4. When the spec changes
If the developer edits the spec, or you find something the spec gets wrong (an API that doesn't
behave as assumed, a criterion that can't be tested as written):
- Stop and explain the problem with the evidence. Propose the spec change; don't decide it alone.
- Once agreed, update the spec (decisions, criteria table, Known gaps), then re-plan the unticked
  slices. Ticked slices stay as they are; fixes to them go in a new slice.
- If the build turns up a risk the E2E scenarios miss (a state the UI could mishandle, a request
  that shouldn't happen), add its scenario to `## E2E scenarios` and its `E2E n` to the criterion's
  "Browser" cell, and tell the developer.

## 5. Finish
- Every slice ticked, every acceptance-criteria row has passing tests, `make check` green.
- Fill the spec's Testing → Manual line with the end-to-end check the developer should run, and
  ask them for the result if it belongs in the spec's Results.
- Tell the developer the next steps: `/e2e TNN` if the spec has E2E scenarios (its FAILs are fixed
  in a new slice here, each with the test that catches it, then `/e2e TNN` again), `/code-review`
  on the branch, fix its findings in a final slice (re-run `/e2e TNN` if the fixes touch a page),
  then `/pr`.

Never stage, commit or push.
