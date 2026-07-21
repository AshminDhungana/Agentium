#!/usr/bin/env python3
"""Entry point to launch the Agentium Voice Bridge UI."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from ui.main import main

if __name__ == "__main__":
    main()
