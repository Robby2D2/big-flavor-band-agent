# Publish Release

Determine release info automatically and walk through tagging and deploying the Big Flavor Band Agent
to production (Docker) with minimal user input.

## Your role

You are a release manager for this Dockerized FastAPI + Next.js app. Gather information
automatically, present a single confirmation summary, then execute the steps in order. Use the
TodoWrite tool to track progress.

> There is **no app store and no fastlane** here. A release is: a `vX.Y.Z` git tag on `main`, a
> GitHub Release with notes, and a production deploy of the Docker stack. Versioning lives entirely in
> git tags — this repo has no version file to bump.

## Step 1 — Gather release info automatically

Run these in parallel (Bash tool):

**Last release tag:**
```bash
git tag -l 'v*' --sort=-v:refname | head -5
```

**Commits since last tag (what changed):**
```bash
git log $(git tag -l 'v*' --sort=-v:refname | head -1)..HEAD --oneline --no-merges
```
If there are no tags yet, use `git log --oneline --no-merges -20` (this is the first release).

## Step 2 — Propose the release

From the information gathered, determine:
- **New version**: bump the patch from the latest tag (e.g. `0.2.1` → `0.2.2`). If commits include a
  feature (not just fixes/chores), suggest bumping the **minor** instead. If there is no tag yet,
  propose `v0.1.0`. Show your reasoning.
- **Release notes**: synthesize the git commits into 1–3 plain-English sentences for the GitHub
  Release "What's Changed". Omit chore/CI/bump commits; focus on user-facing changes (search, agent/
  DJ, radio, production tools).

Show a confirmation summary like:

```
Ready to publish:
  Version:       v0.2.2 (was v0.2.1)
  Release notes: [your drafted notes]

Changes included:
  abc1234 fix: lyric search ranking
  def5678 feat: hybrid search weighting

Proceed? (or say what to change)
```

Wait for the user to confirm or request adjustments before continuing.

## Step 3 — Pre-flight sanity check

Confirm `main` is healthy before tagging (best-effort — if Docker isn't up, say so and ask whether to
proceed):

```bash
git checkout main && git pull --ff-only
docker restart bigflavor-backend && sleep 5 && docker logs bigflavor-backend --tail 30
cd frontend && npm run build
```

If the backend doesn't boot or the frontend doesn't build, stop and report — don't tag a broken `main`.

## Step 4 — Tag and push

```bash
git tag -a "vVERSION" -m "Release vVERSION"
git push origin "vVERSION"
```
Confirm the tag reached origin:
```bash
git ls-remote --tags origin "vVERSION"
```
Do not proceed if the tag didn't push.

## Step 5 — Create the GitHub Release

```bash
# With a previous tag:
gh release create "vVERSION" --title "vVERSION" --notes "CONFIRMED_RELEASE_NOTES" --notes-start-tag "PREV_TAG"
# First release (no previous tag): drop --notes-start-tag.
```

## Step 6 — Deploy to production

Deploy the Docker stack. On the production host (or via the deploy script for this machine):

```bash
# Linux / production host:
./deploy-production.sh
```
```powershell
# Windows (PowerShell tool):
.\deploy-production.ps1
```

Follow `DOCKER_DEPLOYMENT.md` / `PRODUCTION_QUICK_START.md` for the exact host steps and required
production env (`.env.production` from `.env.production.example` — Anthropic key, Google OAuth,
Postgres password). Confirm the stack came up:

```bash
docker-compose ps
docker logs bigflavor-backend --tail 50
```

## Step 7 — Verify the live deploy

- `GET /health` on the production backend returns OK.
- The radio `/stream` endpoint is serving audio (not silence) — `docker logs bigflavor-liquidsoap`.
- A sample search and an agent/DJ request return results.

## Step 8 — Wrap up

Print a final summary:

```
Release vVERSION published:
  ✅ Tagged v VERSION and pushed
  ✅ GitHub Release created
  ✅ Docker stack deployed to production
  ✅ /health OK, stream live, search responding

Next steps:
  • Monitor docker logs bigflavor-backend for errors.
  • Roll back by deploying the previous tag if needed.
```

## Notes

- Run `git`/`gh`/`docker` via the **Bash tool**; run `.ps1` scripts and `npm` via the **PowerShell tool**.
- Never commit secrets or `.env*` files. Production secrets are injected via env vars on the host.
- Do not deploy a tag whose `main` failed the Step 3 sanity check.
- If `deploy-production` fails partway, report exactly what came up and what didn't — don't claim a
  clean deploy.
