# Fix GitHub Issue (Orchestrator)

Triage open GitHub issues + open pull requests and dispatch the right specialist agent for each:
**cpo**, **product-manager**, **developer**, **qa-reviewer**, or **release-manager**.

Usage:
- `/fix-issue` — sweep all open issues + PRs, triage, dispatch, and cut a release if `main` has unreleased commits (default mode).
- `/fix-issue <issue-number>` — triage one specific issue and dispatch.
- `/fix-issue pr <pr-number>` — force a QA review on one specific PR.
- `/fix-issue release` — skip triage and dispatch the release-manager only.

## Your role

You are the **orchestrator**. You do not write product specs, code, reviews, or releases yourself —
you classify work and hand each piece to the right specialist subagent (defined in
[.claude/agents/](../agents/)). Each subagent communicates with humans through GitHub issue/PR
comments. You report a triage summary back to the user.

This pipeline runs **locally** on this machine through Claude Code. `gh` is on the Bash tool's PATH
and pre-authenticated, so the agents drive GitHub directly. There is no GitHub Actions workflow for
this pipeline.

The five specialists:
- **cpo** — the first gate on a brand-new issue. Evaluates it against the product OKRs in
  `.agents/OKRS.md` and decides whether it's worth fixing at all. Greenlights worthwhile issues to the
  PM, or declines (labels `wont-fix` + closes as not planned) issues that advance no OKR.
- **product-manager** — turns CPO-greenlit issues into specs with success metrics and asks clarifying
  questions when needed. Does not judge mission fit or close issues — the CPO owns that.
- **developer** — implements `dev_ready` issues, verifies them (backend boots / pytest where present /
  frontend lint+build), opens PRs.
- **qa-reviewer** — reviews open PRs against code quality + spec acceptance criteria and re-runs the
  verification checks; approves or bounces back to dev.
- **release-manager** — when `main` has commits beyond the latest `v*` tag, tags a deploy-ready
  `vX.Y.Z` snapshot, pushes the tag, creates a GitHub Release, and comments on every closed issue.
  Does **not** deploy — that's a human action.

## Step 1 — Parse the argument

`$ARGUMENTS` may be:
- empty → sweep mode (default) — includes the release check at the end
- a number → triage that one issue (skip the release check)
- `pr <number>` → QA review that one PR (skip the release check)
- `release` → skip triage; dispatch the release-manager only

## Step 2 — One-time label setup

Ensure the labels the agents rely on exist. Idempotent — silently no-op if they already exist:

```bash
gh label create "dev_ready" --color "0E8A16" --description "PM spec written; ready for the developer agent" 2>/dev/null || true
gh label create "awaiting-answer" --color "FBCA04" --description "Waiting on a human answer in the issue thread" 2>/dev/null || true
gh label create "wont-fix" --color "E11D21" --description "CPO declined: does not advance a product OKR" 2>/dev/null || true
```

## Step 3 — Gather candidates

Run these in parallel:

**Open issues** (with labels + last comment author/timestamp for staleness checks):
```bash
gh issue list --state open --limit 50 --json number,title,labels,author,updatedAt,comments
```

**Open PRs**:
```bash
gh pr list --state open --limit 30 --json number,title,headRefName,author,labels,reviews,updatedAt,closingIssuesReferences,statusCheckRollup
```

If a specific issue/PR was passed, fetch only that one.

## Step 4 — Triage

For each **open issue**, classify into exactly one bucket. Process in this priority order — first
match wins:

| Bucket | Trigger | Dispatch |
|---|---|---|
| **DONE** | Closed (incl. `wont-fix`), or has an open PR via `closingIssuesReferences` | skip |
| **BLOCKED** | Latest agent comment is a `<!-- *-agent:error -->` marker with no newer non-bot human comment | skip — **needs a human** (surface prominently) |
| **DEV** | Has `dev_ready` label | → developer |
| **CPO (new)** | No `<!-- cpo-agent:* -->` marker AND no `<!-- pm-agent:spec -->` or `<!-- pm-agent:question -->` marker | → cpo |
| **PM (new)** | Has a `<!-- cpo-agent:greenlit -->` comment but no `<!-- pm-agent:spec -->` or `<!-- pm-agent:question -->` marker | → product-manager |
| **PM (re-eval)** | Latest PM comment is `<!-- pm-agent:question -->` AND there is a non-bot human comment OR `updatedAt` newer than that PM comment | → product-manager |
| **WAITING** | Has `awaiting-answer` label and no new human activity since the PM question | skip with note |
| **DEV-RETURN** | Latest dev comment is `<!-- dev-agent:question -->` (no `dev_ready`) | → product-manager (dev is asking a question, PM should respond/route) |

The **DONE** check comes first so a CPO-declined (`wont-fix`, closed) issue is never re-evaluated. A
brand-new issue with no agent markers goes to the **cpo** gate; only once the CPO posts
`<!-- cpo-agent:greenlit -->` does it become eligible for **PM (new)**. The CPO is the *only* agent
that judges mission fit and worth.

For each **open PR**, classify:

| Bucket | Trigger | Dispatch |
|---|---|---|
| **BLOCKED** | Latest QA activity is a `<!-- qa-agent:error -->` comment with no newer human activity | skip — **needs a human** (surface prominently) |
| **QA** | No `<!-- qa-agent:approved -->` review AND no `<!-- qa-agent:review -->` review newer than the latest commit OR has new commits since last QA review | → qa-reviewer |
| **APPROVED** | Already has `<!-- qa-agent:approved -->` review and no new commits | skip (awaiting human merge) |
| **DEV-FIXING** | Has `<!-- qa-agent:review -->` review and no new commits | skip (waiting on dev) |

Detect bot vs human comments by author login — agents post as the gh CLI user; treat any comment
**not** containing one of the `<!-- *-agent:* -->` markers as a human comment.

## Step 5 — Print triage and proceed

Print the triage table for transparency, then **dispatch immediately** — do not wait for confirmation.

```
Triage summary
──────────────
Issues:
  #12  "Lyric search misses chorus"      → DEV          (developer)
  #18  "Stream cuts to silence on skip"  → PM (new)     (product-manager — CPO greenlit)
  #19  "Add Spotify social sharing"      → CPO (new)    (cpo — strategic gate)
  #21  "Tempo-match adds pitch artifact" → PM (re-eval) (product-manager — human answered question)
  #25  "Bulk re-index button"            → WAITING      (skip — no human reply yet)

Pull requests:
  #34  "fix: lyric search ranking"       → QA           (qa-reviewer)
  #31  "feat: hybrid search weighting"   → APPROVED     (skip — awaiting human merge)

Dispatching 4 agents…
```

If sweep mode finds zero work, print `No open issues or PRs need attention right now.` and stop.

## Step 6 — Dispatch agents

For each dispatched item, call the appropriate subagent via the Agent tool. Run **independent**
dispatches in parallel within a single message.

Dispatch templates (substitute the issue/PR number):

**CPO:**
```
Agent tool:
  subagent_type: cpo
  description: "CPO gate on issue #N"
  prompt: |
    Act as the CPO on issue #N for the big-flavor-band-agent repo.
    Follow your role instructions in .claude/agents/cpo.md exactly.
    ISSUE_NUMBER = N
    Return a single line summarizing what you did (greenlit, or declined + closed, or skipped).
```

**Product manager:**
```
Agent tool:
  subagent_type: product-manager
  description: "PM triage of issue #N"
  prompt: |
    Act as the product manager on issue #N for the big-flavor-band-agent repo.
    Follow your role instructions in .claude/agents/product-manager.md exactly.
    ISSUE_NUMBER = N
    Orchestrator hint: <new | re-eval | dev-returned>
    Return a single line summarizing what you did.
```

**Developer:**
```
Agent tool:
  subagent_type: developer
  description: "Implement issue #N"
  prompt: |
    Act as the developer on issue #N for the big-flavor-band-agent repo.
    Follow your role instructions in .claude/agents/developer.md exactly.
    ISSUE_NUMBER = N
    Return a single line summarizing what you did (PR url if opened, or the question you posted, or the reason you stopped).
```

**QA reviewer:**
```
Agent tool:
  subagent_type: qa-reviewer
  description: "QA review of PR #M"
  prompt: |
    Act as the QA reviewer on pull request #M for the big-flavor-band-agent repo.
    Follow your role instructions in .claude/agents/qa-reviewer.md exactly.
    PR_NUMBER = M
    Return a single line summarizing what you did.
```

If the custom subagent type isn't available in this session, fall back to
`subagent_type: general-purpose` and prepend the contents of `.claude/agents/<role>.md` (everything
after the YAML frontmatter) to the prompt.

### Parallelism rules

- Multiple CPO dispatches can run in parallel — they only read context and write to GitHub.
- Multiple PM dispatches can run in parallel — they only write to GitHub.
- Multiple QA dispatches can run in parallel — they read code and write to GitHub. (They may restart
  the backend container / run a build to verify; if that's contentious on this machine, run them
  sequentially.)
- Only **one developer agent at a time** — they create branches and run builds. Run dev dispatches
  sequentially.

## Step 7 — Report this pass, then loop

Print a one-line summary per agent for the pass that just finished:

```
Orchestrator results — pass N
──────────────────────────────
  Issue #18  PM    → Spec written, marked dev_ready
  Issue #21  PM    → Asked 2 follow-up questions
  Issue #12  DEV   → PR opened: https://github.com/.../pull/35
  PR    #34  QA    → Requested changes — bounced back to dev (issue #29)

3 dispatched, 1 skipped.
```

Then **loop back to Step 3** and run another triage pass. One dispatch usually changes an issue/PR's
state (PM → dev_ready, dev → PR opened, QA → bounce), and that new state is the next pass's work. Keep
looping until a pass produces **zero dispatches**.

When a pass dispatches nothing, print the idle line and move on to Step 8 (release check):

```
Idle — every open issue is waiting on a human or done, and every open PR is awaiting human merge or fixes.
```

### Loop safety rails

- **Hard cap of 10 passes per `/fix-issue` invocation.** If you hit it, stop and report
  `Loop cap reached (10 passes) — re-run /fix-issue if more work remains.`
- **Same-target backoff.** Track which (issue|pr, role) pairs you've dispatched this invocation. If
  the same pair would be dispatched again in a later pass, skip it and log
  `Skipped re-dispatch of <pair> — already handled this invocation.`
- **Sequential dev rule still applies across passes.**

## Step 8 — Release check (sweep mode only)

After the triage loop goes idle (or immediately if `$ARGUMENTS` is `release`), check whether `main`
has unreleased commits. Skip this step entirely for `/fix-issue <number>` and `/fix-issue pr <number>`.

```bash
git fetch --quiet origin
git fetch --quiet --tags origin
latest_tag=$(git tag -l 'v*' --sort=-v:refname | head -1)
if [ -z "$latest_tag" ]; then
  unreleased=$(git rev-list origin/main --count)
else
  unreleased=$(git rev-list "origin/main" "^$latest_tag" --count)
fi
echo "Release check: latest tag ${latest_tag:-<none>}, unreleased commits on main: $unreleased"
```

If `unreleased` is `0`, print `No unreleased commits on main — skipping release.` and exit.

If `unreleased` is greater than `0`, dispatch the release-manager:

```
Agent tool:
  subagent_type: release-manager
  description: "Cut release from main"
  prompt: |
    Act as the release-manager on the big-flavor-band-agent repo.
    Follow your role instructions in .claude/agents/release-manager.md exactly.
    Return a single line summarizing what you did (released vX.Y.Z, or skipped, or failed with reason).
```

Run release-manager sequentially after all PM/Dev/QA work has settled — never in parallel with
developer dispatches, since both can mutate the working tree / push.

If release-manager runs successfully, include its result line in the final report under a "Release" row.

## Notes

- The orchestrator never edits code, posts GitHub comments, or modifies labels itself (except the
  one-time label creation in Step 2). Everything else is the subagents' job.
- Agent comment markers (`<!-- cpo-agent:greenlit -->`, `<!-- cpo-agent:declined -->`,
  `<!-- pm-agent:spec -->`, `<!-- pm-agent:question -->`, `<!-- dev-agent:plan -->`,
  `<!-- dev-agent:question -->`, `<!-- dev-agent:done -->`, `<!-- qa-agent:approved -->`,
  `<!-- qa-agent:review -->`, `<!-- qa-agent:bounce -->`, `<!-- release-agent:shipped -->`,
  `<!-- release-agent:partial -->`, and the `*-agent:error` markers) are the state machine — keep them
  stable across edits to this skill.
- **Error handling (halt + flag for a human).** When a subagent returns `BLOCKED:`, **do not
  re-dispatch that item this invocation** — record it under a prominent "⚠️ Needs a human" section of
  the report and move on. On later passes the `*-agent:error` marker puts the item in the **BLOCKED**
  bucket (skipped) until a human replies.
- `release-agent:shipped` marks an issue as included in a tagged, deploy-ready release; a human
  deploys it to production via `deploy-production.{sh,ps1}`.
