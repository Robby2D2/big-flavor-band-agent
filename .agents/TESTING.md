# Testing Guide — Big Flavor Band Agent

> **State of testing (be honest about it).** This project does **not** yet have a formal automated
> test suite. The `tests/` directory is a large collection of **ad-hoc, print-based scripts**
> (manual demos and one-off verification runners using `asyncio`, e.g. `tests/test_search.py`,
> `tests/demo_rag_search.py`). They are useful for manual checking but are **not** assertion-based
> and are not wired into a test runner. The frontend gained a real runner in 2026-08 — **vitest**
> (`npm test`, jsdom + React Testing Library, specs under `frontend/__tests__/`) — but only the newest
> components are covered by it.
>
> The convention **going forward** is below. New backend behavior should ship with a real
> `pytest` test; new frontend behavior should ship with a `vitest` test where the logic is testable
> (pure functions and components), and must at least keep `npm run build` green.
>
> **Linting works again (2026-09-18).** `npm run lint` now runs the eslint CLI against a flat
> `frontend/eslint.config.mjs` (ESLint 9 + `eslint-config-next`'s `core-web-vitals` and `typescript`
> configs), replacing the `next lint` script Next 16 removed. The repo is clean and the script runs
> `--max-warnings=0`, so **zero errors and zero warnings** is enforced, not just documented — any
> output is something your change introduced. Where a rule is deliberately not
> followed (auth links that must be real navigations, small external avatars), the line carries an
> `eslint-disable-next-line` with the reason — write the reason, don't just silence it.

---

## What "verified" means today

Because there is no green/red suite, an agent or developer marks work verified by running the
checks that actually exist and pass them:

| Layer | Command | Use for |
|---|---|---|
| Backend imports/health | `docker restart bigflavor-backend && docker logs bigflavor-backend --tail 50` | The app boots, no import/startup errors, `/health` is reachable |
| Backend unit (new) | `python -m pytest tests/ -q` (after adding real pytest tests) | New backend logic |
| Backend manual script | `python tests/<script>.py` (venv active) | Reproducing a search/agent/radio scenario by hand |
| Frontend unit | `cd frontend && npm test` | vitest specs in `frontend/__tests__/` (hooks, pure logic, components) |
| Frontend build | `cd frontend && npm run build` | The app compiles for production (also typechecks) |
| Frontend lint | `cd frontend && npm run lint` | `eslint .` over the flat config; must stay at zero problems |

> **Backend suite caveat.** `python -m pytest tests/ -q` fails to *collect* four ad-hoc scraper scripts
> (`test_scraper.py`, `test_click_details.py`, `test_details_one_by_one.py`, `test_incremental_scrape.py`
> — they import a `web_scraper` module that no longer exists), and ~13 further demo scripts fail at run
> time without a live Postgres/Ollama. Neither is a regression signal. Run with those four `--ignore`d
> and read past the connection-refused failures; the assertion-based tests are the ones that matter.

### Writing new frontend tests (vitest)

`frontend/vitest.config.mts` (jsdom, globals, `@/` paths from tsconfig) + `vitest.setup.ts`
(jest-dom matchers, auto-cleanup). Put specs in `frontend/__tests__/*.test.{ts,tsx}`.

Prefer extracting logic into a pure module and testing that directly — `lib/lyricTimings.ts` is the
model: the active-line/word search lives there as plain functions, and `LyricsFollower.test.tsx` only
covers what genuinely needs a DOM (highlighting, click-to-seek, scroll). jsdom implements neither
`scrollIntoView` nor `matchMedia`, so components using them need those stubbed in the spec.

> **venv first.** Per `.github/copilot-instructions.md`, activate the venv before any Python command
> (`venv\Scripts\Activate.ps1` on Windows) and prefer `python -m …`. Most backend code, though, is
> exercised inside the `bigflavor-backend` container, but **`tests/` is not mounted into it** —
> only `src`, `database`, `backend_api.py`, `scripts` and `streaming` are. So
> `docker exec bigflavor-backend python -m pytest tests/…` fails with "file or directory not
> found"; **run backend tests from the host venv** instead. Use `docker exec` for driving the
> *running* app (calling a tool, hitting an endpoint), not for the test suite.

---

## Writing new backend tests (pytest — the target state)

Add `pytest` + `pytest-asyncio` to the dev deps and put real tests under `tests/` named
`test_*.py` with `assert`s (not prints). Keep them **narrow** — test one function/route at a time.

```python
import pytest

@pytest.mark.asyncio
async def test_text_search_returns_ranked_songs(rag_system):
    results = await rag_system.search_text("calm ambient sleep music", limit=5)
    assert results, "expected at least one match"
    assert results == sorted(results, key=lambda r: r["score"], reverse=True)
```

Guidance:
- **Don't hit production data or external APIs in a test.** For DB-backed tests, point
  `DatabaseManager` at a disposable test database (or a transaction rolled back in teardown), not
  the live `bigflavor` DB.
- **Don't call a real LLM in a test.** The `LLMProvider` abstraction is the seam — inject a fake
  provider so agent/tool-routing logic is tested without Anthropic/Ollama.
- Audio/Whisper/CLAP work is slow and heavy — test the orchestration around it with small fixtures
  or fakes, not by transcribing real files in CI.

## Writing new frontend tests

The harness is vitest — see "Writing new frontend tests (vitest)" above, which is the live section.
Every frontend change must also keep `npm run lint` and `npm run build` green.

---

## Guidelines

- **Every new feature or bug fix should add or update a test** where a runnable test layer exists.
  If the only thing that can be checked today is "backend boots + `/health` OK" or "frontend builds,"
  say so explicitly in the PR test plan rather than implying a suite ran.
- Prefer narrow unit tests over broad end-to-end scripts.
- Never let a "test" be a `print` you eyeball — if you add a backend test, make it assert.
- Preserve the radio invariants when touching streaming (`mksafe()`, playlist path rewrite) — verify
  by checking `docker logs bigflavor-liquidsoap` shows it streaming the playlist, not `blank()`.

---

## Before marking a task complete

Run what applies to your change and report results honestly:

```bash
# backend touched
docker restart bigflavor-backend && docker logs bigflavor-backend --tail 50
python -m pytest tests/ -q            # if/when real pytest tests exist

# frontend touched
cd frontend && npm run lint && npm run build
```

Fix every failure you introduced. Note any pre-existing failure in the PR body rather than silently
working around it.
