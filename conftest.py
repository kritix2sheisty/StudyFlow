"""
conftest.py
Ensures the project root (where models.py/storage.py/main.py live)
is importable from inside tests/, regardless of where pytest is run from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
