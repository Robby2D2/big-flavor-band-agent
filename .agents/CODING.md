# Coding Standards — Big Flavor Band Agent

## Principles

- **KISS** — Keep solutions simple. Prefer the straightforward path; avoid clever code that needs
  explaining.
- **DRY** — Don't duplicate logic, queries, or UI patterns. Extract shared behavior only when it's
  used in more than one place.
- No speculative features, no future-proofing abstractions, no extra configurability beyond what is
  asked.
- Match the existing code style. Read the surrounding code before writing new code.

---

## Python (backend / agent / RAG / MCP)

- Target **Python 3.12** (the backend image). Use type hints everywhere; avoid bare `dynamic`/`Any`
  when a real type fits.
- The app is **async** (FastAPI + asyncpg). Use `async`/`await` consistently; never block the event
  loop with sync I/O or heavy CPU work in a request handler — push audio/ML work to the MCP server
  or a thread.
- **All LLM calls go through `src/llm/llm_provider.py`** (`get_llm_provider()` /
  `LLMProvider`). Do **not** `import anthropic` directly in agent logic — that breaks the
  Ollama/Anthropic switch.
- **All DB access goes through `DatabaseManager`** (`database/database.py`). No ad-hoc connections,
  no SQL string-building with f-strings on user input — use parameterised asyncpg queries.
- **Never hardcode secrets or DB creds.** Read from env (`DB_*`, `DATABASE_URL`, `ANTHROPIC_API_KEY`,
  `OLLAMA_*`, `GOOGLE_CLIENT_*`). See `.env.example` / `.env.production.example`.
- Search/read code belongs in the **RAG system** (`src/rag/`); production/write code belongs in the
  **MCP server** (`src/production/`). Don't blur the two (see [ARCHITECTURE.md](ARCHITECTURE.md)).
- Use the module loggers (`logging.getLogger(...)`) already established — don't `print()` in
  backend code.
- Run Python with the venv active and prefer `python -m …` (see `.github/copilot-instructions.md`).

## SQL / database

- Schema changes are **migrations**, not edits to existing `init/*.sql`. Add a new numbered file
  under `database/sql/migrations/` and wire it through `run_migration.py`.
- pgvector columns and search functions are performance-sensitive — keep vector dimensions and
  index choices consistent with what's already in `database/sql/`.

## TypeScript / Next.js (frontend)

- App-router project under `frontend/app/`. Browser-protected actions go through the `app/api/*`
  route handlers (the BFF layer), not directly to the backend.
- Follow the existing component conventions in `frontend/components/`. Styling is Tailwind — use
  utility classes, not ad-hoc CSS, unless a component already does otherwise.
- Pass `npm run lint`. Don't introduce `any` where a real type fits.

## Docker / streaming

- After backend/frontend code changes, **restart** the container — don't rebuild (source is
  volume-mounted). Rebuild only for dependency/Dockerfile changes.
- Changes to `streaming/radio.liq` require a **no-cache** Liquidsoap rebuild (see `AGENTS.md`).
- Preserve the two radio invariants: `mksafe()`-wrapped sources, and the
  `/app/audio_library` → `/audio_library` playlist path rewrite.

---

## Documentation

- **Architecture & significant decisions** → [.agents/ARCHITECTURE.md](ARCHITECTURE.md).
- **Testing patterns** → [.agents/TESTING.md](TESTING.md).
- **Feature-level & long-term notes** → a topic file in `.agents/memory/`, linked from
  [.agents/LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).
- Don't scatter docs into ad-hoc comments when a dedicated doc file fits. Comment only where the
  *why* is non-obvious — never narrate what the code plainly does.

---

## Commit / PR hygiene

- Commits should be small and focused. Describe *why*, not just *what*.
- Never commit secrets, `.env` files, audio binaries, `venv/`, `node_modules/`, or `__pycache__`.
- Stage only the files you changed (no `git add -A`).
