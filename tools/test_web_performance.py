#!/usr/bin/env python3
"""编译真实页面模板处理器与日志增量函数，检查缓存边界、环回与空轮询内存。"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def extract(relative: str, name: str) -> str:
    source = (ROOT / relative).read_text(encoding="utf-8")
    start = source.rfind("\n", 0, source.index(name)) + 1
    return source[start:source.index("\n}", start) + 2]


fixture = (ROOT / "tests/host/test_web_performance.cpp").read_text(encoding="utf-8")
fixture = fixture.replace("// @日志增量函数@", extract("components/idf_logbuf/idf_log.cpp", "idf_log_json_since("))
fixture = fixture.replace("// @模板请求处理器@", extract("components/idf_web/idf_web.cpp", "handle_ui_panel("))
(ROOT / "build").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="test-web-perf-", dir=ROOT / "build") as temp:
    source = Path(temp) / "test.cpp"
    binary = Path(temp) / "test.exe"
    source.write_text(fixture, encoding="utf-8")
    subprocess.run([*shlex.split(os.environ.get("CXX", "c++")), "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
