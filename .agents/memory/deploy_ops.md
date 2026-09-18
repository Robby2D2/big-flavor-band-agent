# Deployment & Ops — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) on 2026-09-18 to keep the rolling file under ~200 lines.
Entries about actually shipping this stack: what the production deploy really does, and what bites
at deploy time. Newest first.

See also [`docs/DOCKER_DEPLOYMENT.md`](../../docs/DOCKER_DEPLOYMENT.md) for the procedure itself —
this file is the record of what went wrong and why, not the runbook.

---

### 2026-09-15 — First prod deploy in a while: the image build had been broken for weeks
`docker-compose --env-file .env.production build` failed immediately: `npm ci` refuses a
`package-lock.json` out of sync with `package.json` (missing `@emnapi/*`). Broken since `0fe6e4e`
and invisible locally, because `npm install` is lenient and only `npm ci` — what the Dockerfile
runs — is strict. **Nobody had deployed since.**

Regenerating the lock exposed a second latent break: the vitest suite imported `screen` from
`@testing-library/react`, which only re-exports it from `@testing-library/dom` — a **peer**
dependency that was never declared and that `--legacy-peer-deps` does not install. It had merely
been sitting in a stale `node_modules`. A clean install failed all nine test files. Now declared
explicitly, so a from-scratch install (CI, Docker) reproduces a working suite.

**Prod is this machine.** `deploy-production.sh` runs the same `docker-compose.yml` with a
different env file — same container names, same Postgres volume. So "deploying" does not migrate
anything: the prod database *is* the dev database, which is why migration 13 and the metadata
embeddings were already live. Checked `POSTGRES_PASSWORD` matches between `.env` and
`.env.production` before recreating containers — a mismatch would have locked the backend out of
its own data volume, since Postgres only applies that variable on first init.

Deploy-time differences that actually bite:
- `SESSION_SECRET` differs per environment by design, so **every deploy that flips env logs
  everyone out**.
- `OLLAMA_MODEL` is `mistral-nemo` in dev, `qwen2.5:14b` in prod. Explanations work on both;
  qwen's first call after a restart takes ~13s while the 9 GB model loads, then it is fast.
- The frontend runs `NODE_ENV=development` even in prod: `docker-compose.yml` hardcodes it rather
  than reading `${NODE_ENV}`, so the value in `.env.production` is dead. Pre-existing.
- `deploy-production.sh` prints "3. Set up the database with migrations" but runs no migrations.

Post-deploy verification that matters: liquidsoap logs `Switch to safe_blank` **at startup** and
then recovers once sources are ready — check the *tail*, not the boot lines, or it reads as the
blank-source regression. It was queuing real `/audio_library/…` files a minute later, path rewrite
intact.
