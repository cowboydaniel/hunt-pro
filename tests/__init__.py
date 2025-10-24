"""Test package initialisation for Hunt Pro."""

import sys
from pathlib import Path

# Ensure the repository root is importable when tests run from an isolated
# working directory. Pytest can change the current directory during collection
# which makes top-level modules like ``collaboration`` inaccessible unless the
# project root is explicitly added to ``sys.path``.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

