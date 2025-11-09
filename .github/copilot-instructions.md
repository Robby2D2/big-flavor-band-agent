# Terminal & Python rules for this repo

## ALWAYS ACTIVATE ENV FIRST
When you propose or run terminal commands that use Python or pip, do the following before any Python command:

**macOS/Linux (venv)**  
`source venv/bin/activate`

**Windows PowerShell (venv)**  
`venv\Scripts\Activate.ps1`

## COMMAND STYLE
- Prefer `python -m pip install ...` (not `pip ...`).
- Prefer `python -m pytest` / `python -m build` / `python -m uvicorn ...`, etc.
- If a terminal is newly created, re-run the activation line before Python commands.
- Never install to system Python.

No need to update or create documents unless otherwise requested.


