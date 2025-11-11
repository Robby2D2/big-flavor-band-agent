# Terminal & Python rules for this repo

## ALWAYS ACTIVATE ENV FIRST
Before running any Python or pip commands, you MUST check if the virtual environment is already activated:

### Checking Activation Status
1. **Check the terminal prompt** - If the prompt starts with `(venv)`, the virtual environment is already active
2. **If NOT active** (no `(venv)` prefix), activate it first using:
   - **Windows PowerShell**: `venv\Scripts\Activate.ps1`
   - **macOS/Linux**: `source venv/bin/activate`
3. **If already active** (prompt shows `(venv)`), proceed directly with the Python command

### Workflow
- **Before each Python command**: Check if `(venv)` is in the prompt
- **If missing**: Run activation script first, then the intended command
- **If present**: Run the Python command directly without re-activating

## COMMAND STYLE
- Prefer `python -m pip install ...` (not `pip ...`).
- Prefer `python -m pytest` / `python -m build` / `python -m uvicorn ...`, etc.
- Always verify virtual environment is active before Python commands.
- Never install to system Python.

No need to update or create documents unless otherwise requested.


