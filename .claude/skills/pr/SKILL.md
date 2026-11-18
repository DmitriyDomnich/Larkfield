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
  - unticked slices in the spec's Commit plan,
  - acceptance-criteria rows whose "Tested by" files don't exist,
  - a new setting missing from `.env.example`.
- Spec link: `git remote get-url origin` → `https://github.com/<owner>/<repo>/blob/<branch>/specs/<file>`.
- If neither the spec's Results nor the commits say what was verified by hand (manual end-to-end
  run, a review), ask the developer before writing the Result section.

## 2. Write
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
<what was verified by hand and how it went; review findings and where they were fixed>

### Setup
<new env vars, `make migrate`, `terraform apply`, npm install, anything a reviewer runs first;
"None" if nothing>

### Known edge cases
- <from the spec's Known gaps>
```

Title: `TNN — <spec title>`.

## 3. Hand over
- Save the body to `pr-body.md` in the scratchpad directory and give its full path.
- Print the title and the body in the reply, ready to paste.
- Give the command for the developer to run:
  `gh pr create --base dev --title "<title>" --body-file <path>`
