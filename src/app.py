#!/usr/bin/env python3
"""
Legacy entry point for Dataiku Agent.

This file is maintained for backwards compatibility.
The main application logic has been moved to src/main.py.
"""
import warnings
import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).parent))

# Import from the new main module
from main import main

if __name__ == "__main__":
    warnings.warn(
        "Using src/app.py is deprecated. Please use 'python -m src.main' instead.",
        DeprecationWarning,
        stacklevel=2
    )
    main() 