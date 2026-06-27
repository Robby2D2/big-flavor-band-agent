# Agent Guidelines — Big Flavor Band Agent

This project is an **AI-powered music discovery & production assistant** for the Big Flavor Band's
~1,300-song catalog. It is a Python **FastAPI** backend + **Next.js** frontend, backed by
**PostgreSQL/pgvector**, an **Ollama/Anthropic** LLM layer, and an **Icecast + Liquidsoap** radio
stack — all orchestrated with **Docker Compose**.

### GitHub CLI (`gh`)

> **Where the pipeline runs.** The `/fix-issue` agents (cpo, product-manager, developer, qa-reviewer,
> release-manager) run **locally on this Windows machine** through Claude Code, dispatched by the
> `/fix-issue` orchestrator — there is no GitHub Actions pipeline for them in this repo. They drive
> GitHub entirely through the `gh` CLI.

On this machine `gh` is on the **Bash tool's** PATH (`/c/Program Files/GitHub CLI/gh`) and is
pre-authenticated, so the agents call **bare `gh`** from the **Bash tool** with bash syntax. Post
multi-line comment/PR bodies with a **quoted bash heredoc** so apostrophes, `$`, and backticks pass
through literally:

```bash
gh issue comment "$ISSUE_NUMBER" --body "$(cat <<'EOF'
…your markdown body, apostrophes and all…
EOF
)"
```

Use an **unquoted** heredoc (`<<EOF`) only when you deliberately want shell variables in the body to
expand (e.g. `$PR_NUMBER`), and escape any literal `$`/backticks in that case.

> **Tool choice on Windows.** Run `gh`, `git`, `docker`, and `pytest` through the **Bash tool**
> (POSIX `sh`) when using heredocs and `||`/`2>/dev/null`. Run `.ps1` scripts, `npm`, and anything
> needing PowerShell semantics through the **PowerShell tool**. Don't mix the two syntaxes in one
> call.

---

### Agent Error Handling (halt + flag for a human)

Every pipeline agent (cpo, product-manager, developer, qa-reviewer, release-manager) follows this
when something goes genuinely wrong. The goal: **never fake success, never silently push through an
unexpected failure** — stop and leave a human a clear note.

**1. Halt on an unrecoverable failure.** If a command you expect to succeed fails in a way you
cannot safely recover from — `gh`/git auth or network failure, `git push` rejected, a Docker/build
error unrelated to your change, a missing tool, or any unexpected non-zero exit you did not plan
for — **stop immediately.** Do not retry blindly, do not fabricate a result, do not proceed to later
steps.

**2. Flag it on the issue/PR** with your role's `<!-- <role>-agent:error -->` marker:

```bash
gh issue comment "$ISSUE_NUMBER" --body "$(cat <<'EOF'
<!-- <role>-agent:error -->
**[<Role>]** ⚠️ Stopped — needs a human.

**Doing:** <the step you were on>
**Failed:** <the command or action>
**Error:** <the key error text, trimmed>

Stopping here so a human can take a look. No further automated action on this item until then.

— posted by <role> agent
EOF
)"
```

**3. Return a `BLOCKED:` line** to the orchestrator instead of a success line —
e.g. `BLOCKED: issue #18 — git push rejected (auth). Posted error comment.`

**Do NOT halt on expected, benign outcomes — these are normal control flow:**
- `gh label create` failing because the label already exists (`2>/dev/null || true` swallows it).
- `gh issue/pr list` returning empty when there's nothing to act on.
- "No PR found", "already past gate", "no new human input".
- `pytest` / `npm run lint` / `npm run build` failing because of **your own in-progress change** —
  that's normal iteration; fix it and continue. Only halt when the failure is environmental/infra,
  not your code.

When genuinely unsure whether an unexpected error is recoverable, **halt and flag** — a human glance
is cheap; a silently broken pipeline is not.

---

### Development

Always refer to `.agents/CODING.md` for coding standards and conventions.

### Testing

Always refer to `.agents/TESTING.md` for how to run and write tests.

### Architecture

Always refer to `.agents/ARCHITECTURE.md` for project structure, the request flow, and significant
decisions.

---

## Docker Development Setup

The app runs as a set of Docker Compose services. **Source is mounted as volumes**, so most changes
hot-reload — restart, don't rebuild.

| Container | Purpose |
|-----------|---------|
| `bigflavor-backend` | Python FastAPI API + agent + RAG |
| `bigflavor-frontend` | Next.js web app |
| `bigflavor-postgres` | PostgreSQL + pgvector |
| `bigflavor-ollama` | Local LLM (qwen2.5:14b, GPU) |
| `bigflavor-icecast` | Radio stream broadcast (`8001:8000`) |
| `bigflavor-liquidsoap` | Audio automation / playlist engine |
| `bigflavor-nginx` | Reverse proxy (80/443) |

### Viewing logs (backend logs live in the container, not on disk)

```bash
docker logs bigflavor-backend --tail 100
docker logs bigflavor-backend -f          # follow
docker logs bigflavor-liquidsoap --tail 100   # radio debugging
```

### Hot reloading — restart, don't rebuild

`./src`, `./database`, `./backend_api.py` (backend) and `./frontend/{app,components,lib,public}`
(frontend) are mounted read-only. After a code change:

```bash
docker restart bigflavor-backend
```

Only rebuild when you change dependencies (`requirements-api.txt`, `frontend/package.json`) or a
`Dockerfile`.

### Liquidsoap config changes need a forced no-cache rebuild

Docker BuildKit aggressively caches the `COPY` layer for `streaming/radio.liq`, so a plain
`docker restart`/`build` will **not** pick up changes:

```bash
# (PowerShell tool) bump the timestamp first
powershell -Command "(Get-Item 'streaming/radio.liq').LastWriteTime = Get-Date"

docker stop bigflavor-liquidsoap && docker rm bigflavor-liquidsoap
docker-compose build --no-cache liquidsoap
docker-compose up -d liquidsoap
```

### Common commands

```bash
docker-compose up -d                 # start all services
docker restart bigflavor-backend     # apply backend code changes
cd frontend && npm run dev           # frontend dev server (outside Docker)
```

---

## Radio Streaming Architecture (Icecast + Liquidsoap)

The radio uses Icecast + Liquidsoap for synchronized audio streaming:

- **Backend** (`backend_api.py`): manages radio queue state and writes the playlist file to
  `streaming/playlist/radio.m3u`.
- **Liquidsoap** (`streaming/radio.liq`): reads the playlist and streams to Icecast.
- **Icecast**: broadcasts at `/stream` (proxied by nginx).
- **Shared volume**: `./streaming/playlist` is mounted into both backend and liquidsoap.

**Two critical configuration facts (do not regress):**
1. Liquidsoap playlist sources **must** be wrapped in `mksafe()`, or the `fallback` operator picks
   `blank()` even with valid playlist files (sources look "not ready" during init):
   ```liquidsoap
   radio_queue = mksafe(radio_queue)
   fallback_music = mksafe(fallback_music)
   radio = fallback([radio_queue, fallback_music, blank()])
   ```
2. Playlist paths must match Liquidsoap's mount points: the backend writes `/app/audio_library/…`
   and **converts** it to `/audio_library/…` for the Liquidsoap container — see
   `write_playlist_file()` in `backend_api.py`.

---

## Deployment ("releasing")

There is **no app store and no fastlane** here — shipping means deploying the Docker stack to
production. The release-manager agent treats a release as "merged work on `main` is ready to deploy,"
tags it, and produces a deploy summary; a human runs the actual deploy.

- **Production deploy:** `deploy-production.sh` (Linux/CI) or `deploy-production.ps1` (Windows),
  driven by `docker-compose` with the production env. Full procedure in
  [`docs/DOCKER_DEPLOYMENT.md`](docs/DOCKER_DEPLOYMENT.md) and
  [`docs/PRODUCTION_QUICK_START.md`](docs/PRODUCTION_QUICK_START.md).
- **Environment:** copy `.env.production.example` → production env; secrets (Anthropic key, Google
  OAuth, Postgres password) are injected via env vars, never committed.
- **Local run:** `docker-compose up -d` (see [`docs/RUNNING_LOCALLY.md`](docs/RUNNING_LOCALLY.md) and
  [`docs/QUICK_START.md`](docs/QUICK_START.md)).

The repo does not yet use version tags. When the release-manager adopts them it uses a simple
`vX.Y.Z` scheme on `main`; until then "release" is purely the deploy summary + GitHub Release notes.

---

### Key Changes

At the end of every significant task or session, you MUST:
1. **Changes** — Identify key learnings (new patterns, fixed bugs, architectural decisions).
2. **Architecture** — Read `.agents/ARCHITECTURE.md` and update it with any structural changes.
3. **Memory** — Read `.agents/MEMORY.md` and add a concise, **dated** summary of the changes. This
   is the most-relevant rolling record of the project as a whole.
4. **Prune** — When `.agents/MEMORY.md` approaches ~200 lines, move older entries into topic-specific
   files under `.agents/memory/` (e.g. `.agents/memory/radio_streaming.md`, `.agents/memory/rag.md`)
   and link each from `.agents/LONGTERM_MEMORY.md`.
5. **Agent decision memory** — When a clear *pattern* emerges in how the CPO greenlights/declines
   issues or how the PM scopes specs, distill it into `.agents/memory/cpo_decisions.md` or
   `.agents/memory/pm_conventions.md`. These are the CPO/PM agents' curated long-term memory: they
   **read** them on every run but never edit them, so a human (or this upkeep pass) is the only
   writer. Keep entries short and high-signal — the GitHub `wont-fix`/`dev_ready` trail already
   records the raw decisions; these files hold the *generalized rationale*.
