"""Shared test helpers: make the in-repo core importable without installing it."""
import os
import sys

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
