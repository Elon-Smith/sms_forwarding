#!/usr/bin/env python3
"""Run complete production config regressions, including both SIMs and interrupted commits."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name("test_dual_config.py")), run_name="__main__")
