#!/usr/bin/env python3
"""Run the production notification queue/retry code with a failing network boundary."""
from pathlib import Path
import os, re, shlex, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
source = (root/'components/idf_push/idf_push.cpp').read_text('utf-8')
def function(name):
    m = re.search(r'^static bool '+name+r'\(', source, re.M)
    return source[m.start():source.index('\n}', m.end())+2]
a = source.index('struct PushJob {')
struct = source[a:source.index('\n};',a)+3]
code = (root/'tests/host/test_dual_push.cpp').read_text('utf-8')
code = code.replace('// @struct@',struct).replace('// @functions@','\n'.join(function(n) for n in ['enqueue_push_job_locked','process_push_one']))
with tempfile.TemporaryDirectory(prefix='dual-push-') as tmp:
    cpp, binary = Path(tmp)/'test.cpp', Path(tmp)/'test.exe'
    cpp.write_text(code,'utf-8')
    subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++17','-Wall','-Wextra','-Werror',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
