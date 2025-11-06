# Virtual Environment Setup

This project uses a Python virtual environment to manage dependencies and ensure consistency across different systems.

## ✅ Already Set Up!

The virtual environment has been created and all dependencies are installed. You're ready to go!

## Environment Details

- **Location**: `.\venv`
- **Python Version**: 3.12.10
- **Type**: Virtual Environment
- **Status**: ✓ Active and ready

## Installed Packages

### Core Dependencies
- **mcp** (1.20.0) - Model Context Protocol for AI agent server
- **httpx** (0.28.1) - HTTP client for web requests

### Audio Analysis
- **librosa** (0.11.0) - Audio analysis (BPM, genre detection)
- **numpy** (2.3.4) - Numerical operations
- **soundfile** (0.13.1) - Audio file I/O

### Additional Dependencies
- Over 50 supporting packages automatically installed

## Quick Start

### Activate the Virtual Environment

**Option 1 - Use the helper script:**
```powershell
.\activate.ps1
```

**Option 2 - Manual activation:**
```powershell
.\venv\Scripts\Activate.ps1
```

You'll see `(venv)` appear in your terminal prompt when activated.

### Deactivate

When you're done working:
```powershell
deactivate
```

## Usage

Once activated, run commands normally:

```powershell
# Run the MCP server
python mcp_server.py

# Run tests
python test_audio_analysis.py

# Pre-analyze audio files
python pre_analyze_audio.py --max-files 5

# Run the main agent
python agent.py
```

## Why Use a Virtual Environment?

✅ **Isolation**: Dependencies don't conflict with other Python projects  
✅ **Reproducibility**: Everyone uses the same package versions  
✅ **Cleanliness**: Easy to delete and recreate if needed  
✅ **Best Practice**: Industry standard for Python development

## Troubleshooting

### Virtual environment not found
```powershell
# Recreate it
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Package import errors
```powershell
# Verify environment is activated (you should see (venv) in prompt)
# Reinstall packages
pip install -r requirements.txt
```

### Activation script won't run
```powershell
# You may need to allow script execution (one time only)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try again
.\activate.ps1
```

### Wrong Python version
```powershell
# Make sure you're using Python 3.10 or higher
python --version

# If needed, specify Python version when creating venv
python3.12 -m venv venv
```

## Maintenance

### Update Packages
```powershell
# Activate the environment first
.\activate.ps1

# Update all packages
pip install --upgrade -r requirements.txt
```

### Add New Packages
```powershell
# Install the package
pip install package-name

# Update requirements.txt
pip freeze > requirements.txt
```

### Recreate Environment
```powershell
# Deactivate if active
deactivate

# Delete the old environment
Remove-Item -Recurse -Force .\venv

# Create new environment
python -m venv venv

# Activate it
.\activate.ps1

# Install dependencies
pip install -r requirements.txt
```

## Testing

Verify everything is working:

```powershell
# Activate environment
.\activate.ps1

# Run the test suite
python test_audio_analysis.py
```

You should see:
```
✓ All tests passed!
✓ Librosa is installed and available
```

## IDE Integration

### VS Code
VS Code should automatically detect the virtual environment. You can select it:
1. Press `Ctrl+Shift+P`
2. Type "Python: Select Interpreter"
3. Choose the one with `.\venv` in the path

### PyCharm
1. Go to Settings → Project → Python Interpreter
2. Click the gear icon → Add
3. Select "Existing environment"
4. Browse to `.\venv\Scripts\python.exe`

## Files

- **`venv/`** - Virtual environment directory (not in git)
- **`activate.ps1`** - Helper script to activate the environment
- **`requirements.txt`** - List of all dependencies
- **`.gitignore`** - Excludes venv/ from version control

## Notes

- The `venv/` directory is **excluded from git** (in `.gitignore`)
- Each developer creates their own local virtual environment
- The environment is **already activated** in your current terminal
- All packages including **librosa** are installed and tested

---

**Ready to start developing!** 🎸🐍
