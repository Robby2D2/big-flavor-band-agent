"""Make the repo root importable so tests can `import backend_api`."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
