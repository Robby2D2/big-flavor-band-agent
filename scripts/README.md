# scripts/

Helper and one-off scripts for the Big Flavor Band Agent. These were previously
scattered in the repo root; they're collected here to keep the root clean.

**All scripts are written to run from the repo root.** The PowerShell/shell
helpers `cd` themselves there automatically (via `$PSScriptRoot` / `$0`), and the
Python scripts add the repo root to `sys.path`, so you can invoke them from
anywhere, e.g.:

```powershell
.\scripts\dev-local.ps1
python scripts\run_agent.py
```

> ⚠️ **Legacy (Ollama / local-LLM) scripts.** Many scripts here date from when the
> agent ran against a local **Ollama** model with GPU acceleration. The project
> now defaults to the **Anthropic** API (no local LLM required — see
> [`docker-compose.override.yml.example`](../docker-compose.override.yml.example)).
> The Ollama/GPU scripts still work if you opt back into a local model, but they
> are **not** part of the normal workflow. They're marked **[legacy]** below.

---

## Local development

| Script | What it does |
|--------|--------------|
| [`dev-local.ps1`](dev-local.ps1) | **Recommended local dev entry point.** Brings up only the backing services in Docker (PostgreSQL + Icecast/Liquidsoap) so you can run the backend + frontend on the host against Anthropic. Creates `docker-compose.override.yml` from the example if missing, then prints the host commands to run. |
| [`start-backend.ps1`](start-backend.ps1) | Activates the Python venv, ensures API deps are installed (`requirements-api.txt`), and starts the FastAPI backend on `http://localhost:8000` (`python backend_api.py`). |
| [`start-frontend.ps1`](start-frontend.ps1) | Installs frontend deps if needed and runs the Next.js dev server (`npm run dev`) on `http://localhost:3000`. |
| [`start_full_stack.ps1`](start_full_stack.ps1) | **[legacy]** Brings up the **entire** stack in Docker including Ollama, and waits for health. Predates the Anthropic default; use `docker-compose up -d` (+ the override) instead. |
| [`activate.ps1`](activate.ps1) | Convenience wrapper to activate the Python virtual environment (`.\venv`). |

## Agent CLI runners

Interactive command-line ways to talk to the agent (handy for debugging without
the web frontend).

| Script | What it does |
|--------|--------------|
| [`run_agent.py`](run_agent.py) | Main agent entry point — Claude AI agent with RAG search + the production MCP tools. |
| [`run_full_agent.py`](run_full_agent.py) | **[legacy]** Full agent against a real PostgreSQL catalog + **Ollama** + RAG tools. |
| [`run_agent_local.py`](run_agent_local.py) | **[legacy]** Minimal local chat — no Docker/DB/web, talks straight to the LLM provider (Ollama). |
| [`run_agent_simple.py`](run_agent_simple.py) | **[legacy]** Demonstrates tool calling with simulated music tools (no DB). |
| [`run_full.ps1`](run_full.ps1) | **[legacy]** Starts Postgres + Ollama in Docker, then launches `run_full_agent.py`. |
| [`run_local.ps1`](run_local.ps1) | **[legacy]** Starts Ollama (pulling `qwen2.5:14b` if needed), then launches `run_agent_local.py`. |

## Database utilities

| Script | What it does |
|--------|--------------|
| [`run_migration.py`](run_migration.py) | Applies the `05-create-users-table.sql` migration against the database. |
| [`check_tempo.py`](check_tempo.py) | Quick diagnostic: counts songs with/without `tempo_bpm` populated. |

## Ollama & GPU setup  **[legacy]**

Only needed if you opt back into running a local LLM instead of Anthropic.

| Script | What it does |
|--------|--------------|
| [`setup-ollama.ps1`](setup-ollama.ps1) / [`setup-ollama.sh`](setup-ollama.sh) | Pulls and tests the Ollama model (default `qwen2.5:14b`) inside the `bigflavor-ollama` container. |
| [`setup_gpu_complete.ps1`](setup_gpu_complete.ps1) | End-to-end GPU enablement on Windows (Docker Desktop + WSL2 + NVIDIA Container Toolkit), then restarts Ollama with GPU. |
| [`setup_gpu_wsl2.sh`](setup_gpu_wsl2.sh) | Installs the NVIDIA Container Toolkit inside a WSL2 distro (run via the script above). |
| [`enable_gpu.ps1`](enable_gpu.ps1) | Restarts the Ollama container with GPU support and verifies `nvidia-smi` inside it. |
| [`check_gpu.py`](check_gpu.py) | Reports whether CUDA/GPU is visible to Python (used by the transcription tests). |
| [`debug_ollama_request.py`](debug_ollama_request.py) | Sends a raw tool-calling request to Ollama for debugging its responses. |

## Diagnostics & tests

These are standalone scripts (not part of the `pytest` suite under `tests/`).

| Script | What it does |
|--------|--------------|
| [`test_llm_integration.py`](test_llm_integration.py) | Exercises the LLM provider abstraction (Anthropic/Ollama) end to end. |
| [`test_ollama_simple.py`](test_ollama_simple.py) | **[legacy]** Smoke-tests the provider abstraction against Ollama without the full agent. |
| [`test_whisper_models.ps1`](test_whisper_models.ps1) | Benchmarks all Faster-Whisper models on `tests/wagonwheel.mp3` for lyric extraction. |

---

For deploying to production and the day-to-day Docker workflow, see the main
[`README.md`](../README.md).
