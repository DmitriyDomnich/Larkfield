---
name: pr
description: Write the pull request title and description for the current feature branch from its spec and commits
argument-hint: "[TNN]"
disable-model-invocation: true
---

Write the PR description for: $ARGUMENTS

The developer creates the PR; you write its text. Never push, create the PR or run `gh pr create`.

## 1. Gather
- Ticket: from the arguments, else from the branch name (`feature/T13-frontend` → `T13`). Read
  `specs/TNN-*.md`.
- Base branch is `dev`. Commits: `git log --oneline dev..HEAD`. Changes: `git diff --stat dev...HEAD`,
  and the diff itself where a commit message doesn't say enough.
- Check, and list any problem at the top of your reply:
  - uncommitted changes (`git status`),
  - unticked slices in the spec's Commit plan (before step 2 deletes it),
  - acceptance-criteria rows whose "Tested by" files don't exist,
  - a new setting missing from `.env.example`,
  - E2E scenarios with no `## E2E` run, or a FAIL or BLOCKED in the newest run (run `/e2e TNN`),
  - commits after the newest E2E run that touch the frontend (the run may be stale).
- Spec link: `git remote get-url origin` → `https://github.com/<owner>/<repo>/blob/<branch>/specs/<file>`.
- If neither the spec's Results nor the commits say what was verified by hand (manual end-to-end
  run, a review), ask the developer before writing the Result section.

## 2. Condense the spec
Once the ticket is built, the spec is the record of what was decided and why; how it was built
lives in the code and the commits. Rewrite `specs/TNN-*.md` to about 100 lines (the earlier specs'
size) before writing the PR:
- Keep every acceptance criterion, decision, rejected alternative, answered question, setting,
  known gap and the manual Results. Shorten the wording, never the meaning.
- **Acceptance criteria:** "How" is the mechanism in one or two sentences (endpoint, rule,
  component), not the steps. "Tested by" lists the test files only.
- **Design decisions:** `**Choice:** why in one sentence. *Rejected:* alternative (why not).`
  Drop what the code already shows: file trees, folder layouts, prop and hook names, exact styling.
- **Questions:** the answer's facts and links; cut the reasoning around them.
- **Flow:** a Mermaid diagram in a ```` ```mermaid ```` block (GitHub renders it), about 15 lines:
  `sequenceDiagram` for requests between browser, API, AWS and workers; `flowchart` for statuses
  and branches. Keep the happy path and the main failures; drop it if there is no flow worth
  drawing.
- **Configuration:** what changed, not instructions to the developer,
  which are done by now.
- **Testing:** one line each for Unit and Integration; keep Manual.
- **E2E scenarios:** one line each (behaviour, starting data, what is seen); keep the numbers the
  "Browser" column refers to.
- **E2E:** keep only the newest dated run, its table and findings.
- **Results:** their own `## Results` section at the end: the manual run and the reviews.
- **Commit plan:** delete it (the commits and the PR record the slices).

Show the developer the new line count and anything removed that isn't plain rewording, and wait
for their OK. They commit the condensed spec before creating the PR.

## 3. Write
Match the earlier PRs (`gh pr list --base dev --state merged --limit 2 --json body`): terse, facts,
no filler, no restating the spec at length.

```
## TNN — <spec title>

Spec: [specs/<file>](<link>)

<1-2 sentences: what the ticket makes possible>

### Changes
- **<Area>:** <what changed, user-visible behaviour and rules first> (grouped by area: API, DB,
  frontend, infra/Terraform, tests; nest bullets for several items)

### Result
<E2E run (date, scenarios passed, risks found and their new tests); what was verified by hand and
how it went; review findings and where they were fixed>

### Setup
<new env vars, `make migrate`, `terraform apply`, npm install, anything a reviewer runs first;
"None" if nothing>

### Known edge cases
- <from the spec's Known gaps>
```

Title: `TNN — <spec title>`.

## 4. Hand over
- Save the body to `pr-body.md` in the scratchpad directory and give its full path.
- Print the title and the body in the reply, ready to paste.
- Give the command for the developer to run:
  `gh pr create --base dev --title "<title>" --body-file <path>`
