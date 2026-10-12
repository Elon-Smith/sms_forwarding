#!/usr/bin/env python3
"""编译真实配网保存与请求处理函数，检查 mDNS 持久化、旧请求兼容和错误边界。"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(relative, name):
    source = (ROOT / relative).read_text(encoding="utf-8")
    match = re.search(rf"^(?:static )?(?:const )?[\w:<>]+[\s*&]+{re.escape(name)}\([^;]*?\)\s*\n\{{", source, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"未找到函数: {name}")
    end = source.index("\n}", match.end()) + 2
    return source[match.start():end]


config = "components/idf_config/idf_config.cpp"
web = "components/idf_web/idf_web.cpp"
functions = "\n\n".join(function(config, name) for name in ["trim_copy", "sanitize_mdns_host", "idf_config_save_wifi"])
functions += "\n\n" + "\n\n".join(function(web, name) for name in [
    "hex_value", "url_decode", "parse_urlencoded", "find_field", "has_field", "field_text",
    "handle_wifi_config", "handle_apstatus",
])
fixture = (ROOT / "tests/host/test_ap_provisioning.cpp").read_text(encoding="utf-8")
fixture = fixture.replace("// @配网函数@", functions)
(ROOT / "build").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="test-ap-provisioning-", dir=ROOT / "build") as temp:
    source = Path(temp) / "test.cpp"
    binary = Path(temp) / "test.exe"
    source.write_text(fixture, encoding="utf-8")
    subprocess.run([os.environ.get("CXX", "g++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
