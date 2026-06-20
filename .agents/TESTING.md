# Testing Guide — Big Flavor Band Agent

> **State of testing (be honest about it).** This project does **not** yet have a formal automated
> test suite. The `tests/` directory is a large collection of **ad-hoc, print-based scripts**
> (manual demos and one-off verification runners using `asyncio`, e.g. `tests/test_search.py`,
> `tests/demo_rag_search.py`). They are useful for manual checking but are **not** assertion-based
> and are not wired into a test runner. The frontend has **no** test script (only `lint`/`build`).
>
> The convention **going forward** is below. New backend behavior should ship with a real
> `pytest` test; new frontend behavior must at least keep `npm run lint` and `npm run build` green.

---

## What "verified" means today

Because there is no green/red suite, an agent or developer marks work verified by running the
checks that actually exist and pass them:

| Layer | Command | Use for |
|---|---|---|
| Backend imports/health | `docker restart bigflavor-backend && docker logs bigflavor-backend --tail 50` | The app boots, no import/startup errors, `/health` is reachable |
| Backend unit (new) | `python -m pytest tests/ -q` (after adding real pytest tests) | New backend logic |
| Backend manual script | `python tests/<script>.py` (venv active) | Reproducing a search/agent/radio scenario by hand |
| Frontend lint | `cd frontend && npm run lint` | TypeScript/React correctness |
| Frontend build | `cd frontend && npm run build` | The app compiles for production |

> **venv first.** Per `.github/copilot-instructions.md`, activate the venv before any Python command
> (`venv\Scripts\Activate.ps1` on Windows) and prefer `python -m …`. Most backend code, though, is
> exercised inside the `bigflavor-backend` container — `docker exec bigflavor-backend python -m pytest …`.

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

There is no test harness wired up yet. At minimum every frontend change must pass `npm run lint`
and `npm run build`. If a component grows real logic worth testing, introduce a lightweight runner
(e.g. Vitest + React Testing Library) in its own PR and document it here.

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
