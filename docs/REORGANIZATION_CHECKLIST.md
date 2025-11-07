# Project Reorganization Checklist

## Status: In Progress 🔄

This checklist tracks the reorganization of the Big Flavor Band Agent project into a clean, maintainable structure.

---

## Phase 1: Directory Structure ✅ COMPLETE

- [x] Create `src/` directory
- [x] Create `src/agent/` directory
- [x] Create `src/rag/` directory  
- [x] Create `src/mcp/` directory
- [x] Create `database/` directory (already exists)
- [x] Create `setup/` directory (already exists)

---

## Phase 2: File Migration ✅ COMPLETE

### Agent Files
- [x] Copy `claude_dual_mcp_agent.py` → `src/agent/big_flavor_agent.py`
- [x] Update imports in `src/agent/big_flavor_agent.py`

### RAG Files
- [x] Copy `rag_system.py` → `src/rag/big_flavor_rag.py`
- [x] Keep class name as `SongRAGSystem`

### MCP Files
- [x] Copy `mcp_server_new.py` → `src/mcp/big_flavor_mcp.py`
- [x] Keep class name as `BigFlavorMCPServer`

### Database Files
- [x] Move `database.py` → `database/database.py`
- [x] Move `apply_schema.py` → `database/apply_schema.py`
- [x] Move `load_from_backup.py` → `database/load_from_backup.py`
- [x] `setup-database.ps1` already in `database/`

### Setup Files
- [x] Move `requirements.txt` → `setup/requirements.txt`
- [x] Move `setup*.ps1` scripts → `setup/` (already there)
- [x] Move `config.json` → `setup/config.json` (if exists)

### Package Files
- [x] Create `src/__init__.py`
- [x] Create `src/agent/__init__.py`
- [x] Create `src/rag/__init__.py`
- [x] Create `src/mcp/__init__.py`
- [x] Create `database/__init__.py`

---

## Phase 3: Import Updates 🔄 IN PROGRESS

### Core Files (High Priority)
- [x] Update imports in `src/agent/big_flavor_agent.py`
- [ ] Update imports in `src/rag/big_flavor_rag.py`
- [ ] Update imports in `src/mcp/big_flavor_mcp.py`

### Supporting Files (Need Verification)
- [ ] `audio_analysis_cache.py` - import DatabaseManager from database/
- [ ] `audio_embedding_extractor.py` - verify imports
- [ ] `audio_analyzer.py` - verify imports
- [ ] `recommendation_engine.py` - update if uses database

### Entry Points
- [x] Create `run_agent.py` with proper path setup
- [ ] Verify `cli.py` (if still needed)
- [ ] Update `agent.py` (if still needed)

### Test Files
- [ ] `tests/test_agent.py`
- [ ] `tests/test_rag.py`
- [ ] `tests/test_mcp.py`
- [ ] `tests/demo_rag_search.py`
- [ ] `tests/quick_test_rag.py`
- [ ] Other test files as needed

### Scraper Files
- [ ] Check if `scraper/*.py` files need database import updates

---

## Phase 4: Testing & Validation ⏳ PENDING

### Compilation Tests
- [ ] Test `python -m py_compile src/agent/big_flavor_agent.py`
- [ ] Test `python -m py_compile src/rag/big_flavor_rag.py`
- [ ] Test `python -m py_compile src/mcp/big_flavor_mcp.py`
- [ ] Test `python -m py_compile database/database.py`
- [ ] Test `python -m py_compile run_agent.py`

### Import Tests
- [ ] Test `from src.agent.big_flavor_agent import ClaudeRAGMCPAgent`
- [ ] Test `from src.rag.big_flavor_rag import SongRAGSystem`
- [ ] Test `from src.mcp.big_flavor_mcp import BigFlavorMCPServer`
- [ ] Test `from database.database import DatabaseManager`

### Unit Tests
- [ ] Run `python tests/test_agent.py`
- [ ] Run `python tests/test_rag.py`
- [ ] Run `python tests/test_mcp.py`
- [ ] Run `python tests/test_database.py`

### Integration Tests
- [ ] Run `python run_agent.py` and verify basic functionality
- [ ] Test RAG search commands
- [ ] Test MCP production commands
- [ ] Test database connections

---

## Phase 5: Documentation Updates ⏳ PENDING

### Core Documentation
- [x] Create `README_NEW.md` with new structure
- [x] Create `docs/NEW_PROJECT_STRUCTURE.md`
- [ ] Update `docs/PROJECT_OVERVIEW.md`
- [ ] Update `docs/GETTING_STARTED.md`
- [ ] Update `docs/SIMPLIFIED_ARCHITECTURE.md`

### Technical Documentation
- [ ] Update `docs/RAG_SYSTEM_GUIDE.md` with new imports
- [ ] Update `docs/TOOL_ROUTING_GUIDE.md` with new file paths
- [ ] Update `docs/DATABASE_SETUP.md` with new locations
- [ ] Create migration guide for existing users

### Code Documentation
- [ ] Add docstrings to `src/agent/big_flavor_agent.py`
- [ ] Add docstrings to `src/rag/big_flavor_rag.py`
- [ ] Add docstrings to `src/mcp/big_flavor_mcp.py`

---

## Phase 6: Cleanup ⏳ PENDING

### Remove Old Files (WAIT UNTIL CONFIRMED WORKING)
- [ ] Delete `claude_dual_mcp_agent.py`
- [ ] Delete `claude_mcp_agent.py`
- [ ] Delete `rag_system.py`
- [ ] Delete `rag_mcp_server.py`
- [ ] Delete `mcp_server_new.py`
- [ ] Delete `mcp_server.py`

### Root Directory Cleanup
- [ ] Move/delete old database files from root (if duplicates)
- [ ] Move/delete old setup files from root (if duplicates)
- [ ] Consider archiving old scripts in `archive/` folder

### Git Operations
- [ ] Stage all new files
- [ ] Commit reorganization
- [ ] Push to branch 'add_llm'

---

## Known Issues & Notes

### Import Warnings
- ✅ Expected: Import lint warnings until all files updated
- ✅ Normal: False positives from IDEs scanning before testing

### Path Setup
- ✅ Solved: `run_agent.py` uses sys.path manipulation
- ⚠️ Watch: Relative imports may need adjustment in some files

### Database Package
- ✅ Created: `database/__init__.py` 
- ⏳ TODO: Export DatabaseManager for easier imports

### Requirements.txt
- ⏳ TODO: Verify all dependencies still listed
- ⏳ TODO: Check for any new dependencies needed

---

## Next Immediate Actions

1. **Update Supporting File Imports** (HIGH PRIORITY)
   - Focus on `audio_analysis_cache.py`
   - Focus on `audio_embedding_extractor.py`
   - These are imported by core files

2. **Create Database Package Exports** (MEDIUM PRIORITY)
   - Edit `database/__init__.py` to export `DatabaseManager`
   - Makes imports cleaner: `from database import DatabaseManager`

3. **Test Compilation** (HIGH PRIORITY)
   - Run py_compile on all new files
   - Verify no syntax errors
   - Check import resolution

4. **Update Test Files** (MEDIUM PRIORITY)
   - At least one test file to verify system works
   - Prefer `tests/quick_test_rag.py` for fast validation

5. **Integration Test** (HIGH PRIORITY)
   - Run `python run_agent.py`
   - Try basic search command
   - Verify RAG system responds

---

## Success Criteria

### Minimum Viable
- [ ] All core files compile without errors
- [ ] `run_agent.py` starts without import errors
- [ ] RAG search returns results
- [ ] Database connections work

### Complete
- [ ] All files compile
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Old files removed
- [ ] Git committed and pushed

---

## Time Estimate

- Remaining import updates: ~30 minutes
- Testing & debugging: ~1-2 hours  
- Documentation updates: ~1 hour
- Total remaining: ~2-4 hours

---

**Current Status**: Files migrated, core imports updated. Need to finish supporting file imports and test.

**Blocker**: None - ready to proceed with testing after final import updates.

**Last Updated**: Initial checklist creation
