#!/usr/bin/env python3
"""Inject every NVS write failure into the production dual-card configuration code."""
import os, shlex, subprocess, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="dual-config-") as tmp:
    binary = Path(tmp) / "test.exe"
    includes = ["tests/host/stubs", "components/idf_config/include", "components/idf_board/include"]
    subprocess.run([*shlex.split(os.environ.get("CXX", "c++")), "-std=c++17", "-Wall", "-Wextra", "-Werror",
        *["-I"+str(root/p) for p in includes], str(root/"tests/host/test_dual_config.cpp"),
        str(root/"components/idf_config/idf_config.cpp"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
