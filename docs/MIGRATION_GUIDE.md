# Migration Guide: Old Structure → New Structure

This guide helps you migrate from the old flat structure to the new organized structure.

---

## Quick Reference

### Running the Agent

**Old Way:**
```powershell
python claude_dual_mcp_agent.py
```

**New Way:**
```powershell
python run_agent.py
```

### Import Changes

**Old Imports:**
```python
from rag_system import SongRAGSystem
from mcp_server_new import BigFlavorMCPServer
from database import DatabaseManager
```

**New Imports:**
```python
from src.rag.big_flavor_rag import SongRAGSystem
from src.mcp.big_flavor_mcp import BigFlavorMCPServer
from database import DatabaseManager  # This one stayed the same!
```

---

## Detailed Migration Steps

### For End Users

No changes needed! Just use the new entry point:
```powershell
python run_agent.py
```

Everything else works the same.

### For Developers

#### 1. Update Your Imports

**If you import the RAG system:**
```python
# OLD
from rag_system import SongRAGSystem

# NEW
from src.rag.big_flavor_rag import SongRAGSystem
```

**If you import the MCP server:**
```python
# OLD
from mcp_server_new import BigFlavorMCPServer

# NEW
from src.mcp.big_flavor_mcp import BigFlavorMCPServer
```

**If you import the agent:**
```python
# OLD
from claude_dual_mcp_agent import ClaudeRAGMCPAgent

# NEW
from src.agent.big_flavor_agent import ClaudeRAGMCPAgent
```

**Database imports (unchanged):**
```python
# Both old and new use this:
from database import DatabaseManager
```

#### 2. Update Your Scripts

**Old script structure:**
```python
from rag_system import SongRAGSystem
from database import DatabaseManager

db = DatabaseManager()
rag = SongRAGSystem(db)
```

**New script structure:**
```python
from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager

db = DatabaseManager()
rag = SongRAGSystem(db)
```

#### 3. Update Your Test Files

**Example test file update:**

**Before:**
```python
# tests/test_rag.py
import sys
sys.path.append('..')
from rag_system import SongRAGSystem
```

**After:**
```python
# tests/test_rag.py
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
from src.rag.big_flavor_rag import SongRAGSystem
```

---

## File Location Changes

### Agent Files
- `claude_dual_mcp_agent.py` → `src/agent/big_flavor_agent.py`
- `claude_mcp_agent.py` → (removed, use new agent)

### RAG Files
- `rag_system.py` → `src/rag/big_flavor_rag.py`
- `rag_mcp_server.py` → (removed, RAG is now a library)

### MCP Files
- `mcp_server_new.py` → `src/mcp/big_flavor_mcp.py`
- `mcp_server.py` → (removed, use new server)

### Database Files
- `database.py` → `database/database.py`
- `apply_schema.py` → `database/apply_schema.py`
- `load_from_backup.py` → `database/load_from_backup.py`
- `setup-database.ps1` → `database/setup-database.ps1`

### Setup Files
- `requirements.txt` → `setup/requirements.txt`
- `setup*.ps1` → `setup/*.ps1`
- `config.json` → `setup/config.json`

---

## Common Migration Issues

### Issue 1: Import Errors

**Error:**
```
ModuleNotFoundError: No module named 'rag_system'
```

**Solution:**
Update your import:
```python
from src.rag.big_flavor_rag import SongRAGSystem
```

### Issue 2: Path Issues

**Error:**
```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
Add project root to sys.path:
```python
import sys
from pathlib import Path
project_root = Path(__file__).parent  # Adjust based on your location
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
```

### Issue 3: Database Import

**Error:**
```
ModuleNotFoundError: No module named 'database'
```

**Solution:**
Add database directory to sys.path:
```python
sys.path.insert(0, str(project_root / "database"))
```

Or use the cleaner import (if database package exports it):
```python
from database import DatabaseManager
```

---

## Testing Your Migration

### Step 1: Test Compilation
```powershell
python -m py_compile src\agent\big_flavor_agent.py
python -m py_compile src\rag\big_flavor_rag.py
python -m py_compile src\mcp\big_flavor_mcp.py
```

### Step 2: Test Imports
```powershell
python -c "from src.agent.big_flavor_agent import ClaudeRAGMCPAgent; print('Agent import OK')"
python -c "from src.rag.big_flavor_rag import SongRAGSystem; print('RAG import OK')"
python -c "from src.mcp.big_flavor_mcp import BigFlavorMCPServer; print('MCP import OK')"
python -c "from database import DatabaseManager; print('Database import OK')"
```

### Step 3: Run Your Code
```powershell
python run_agent.py
```

---

## Backwards Compatibility

### Old Files Still Present

The old files are still in the root directory for now:
- `claude_dual_mcp_agent.py`
- `rag_system.py`
- `mcp_server_new.py`
- etc.

You can still use them if needed for transition period.

### Gradual Migration

You don't have to migrate everything at once:
1. Start using `run_agent.py` instead of old entry point
2. Gradually update imports in your custom scripts
3. Test each change
4. Once everything works, old files can be deleted

---

## Benefits of New Structure

### Before (Flat)
```
❌ 50+ files in root directory
❌ Hard to find what you need
❌ No clear boundaries
❌ Difficult to test components
```

### After (Organized)
```
✅ Clean package structure
✅ Easy navigation
✅ Clear separation of concerns
✅ Simple imports
✅ Testable components
```

---

## Support

### If You Get Stuck

1. **Check this guide** for common issues
2. **Look at REORGANIZATION_COMPLETE.md** for details
3. **Check docs/NEW_PROJECT_STRUCTURE.md** for architecture
4. **Read the new README_NEW.md** for overview

### Rollback If Needed

Old files are still there! You can always:
```powershell
# Use old entry point
python claude_dual_mcp_agent.py

# Use old imports
from rag_system import SongRAGSystem
```

---

## Timeline Suggestion

### Week 1: Testing
- Use new `run_agent.py` entry point
- Test core functionality
- Keep old files as backup

### Week 2: Migration
- Update your custom scripts
- Update test files
- Verify everything works

### Week 3: Cleanup
- Delete old files
- Update documentation
- Commit changes

---

## FAQ

**Q: Do I have to migrate right away?**
A: No, old files still work. Migrate when convenient.

**Q: Will my data be affected?**
A: No, only code organization changed. Database is untouched.

**Q: Can I mix old and new imports?**
A: Not recommended, but technically possible during transition.

**Q: What if something breaks?**
A: Use old files as backup. They're still in root directory.

**Q: Should I update my git remote?**
A: Wait until fully tested. Then commit all changes together.

---

## Final Checklist

Migration complete when:
- [ ] You can run `python run_agent.py` successfully
- [ ] Your custom scripts use new imports
- [ ] Your test files work with new structure
- [ ] No errors in compilation tests
- [ ] Documentation updated (if you have custom docs)
- [ ] Old files can be safely deleted (optional)

---

**Good luck with your migration!** The new structure is much cleaner and easier to maintain.
