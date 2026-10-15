#!/usr/bin/env python3
"""Exercise real modem command dispatch and URC extraction with deterministic RTOS shims."""
from pathlib import Path
import os, re, shlex, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'components/idf_modem/idf_modem.cpp').read_text('utf-8')
a=s.index('    TaskHandle_t owner_');b=s.index('    void idf_log_line',a)
owner=s[a:b]
def fun(name):
    m=re.search(r'^(?:void|bool) '+name+r'\(',s,re.M)
    return s[m.start():s.index('\n}',m.end())+2]
urc='\n'.join(fun(n) for n in ['looks_like_pdu_line','preserve_uart_urc_line','preserve_uart_urcs'])
fixture=(root/'tests/host/test_dual_owner.cpp').read_text('utf-8').replace('// @owner@',owner).replace('// @urc@',urc)
with tempfile.TemporaryDirectory(prefix='dual-owner-') as tmp:
    cpp,binary=Path(tmp)/'test.cpp',Path(tmp)/'test.exe';cpp.write_text(fixture,'utf-8')
    subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++17','-Wall','-Wextra','-Werror',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
