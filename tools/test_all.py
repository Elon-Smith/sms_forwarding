#!/usr/bin/env python3
"""Portable host/JavaScript regression entry point; no device or external messages."""
import json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    output=Path(os.environ.get('TEST_OUTPUT',str(ROOT/'build/regression')));output.mkdir(parents=True,exist_ok=True)
    tests=[(n,[sys.executable,'-X','utf8',f'tools/test_{n}.py']) for n in (
        'dual_dispatch','dual_config','dual_owner','dual_sms','dual_push','ap_provisioning','cellular_http',
        'daily_heartbeat','modem_refresh','modem_uart','scheduled_sms_health','sms_timestamp','web_performance')]
    tests += [(Path(f).stem,['node',f]) for f in ('tests/ap_provisioning_ui_test.js','tests/keepalive_ui_test.js',
        'tests/modem_refresh_ui_test.js','tests/dual_target_ui_test.js','tools/tests/test_scheduled_sms_ui.js')]
    tests += [('javascript_syntax',['node','--check','code/web_src/app.js']),
              ('web_resources',[sys.executable,'-X','utf8','tools/build_web_assets.py','--check']),
              ('sdk_and_delivery',[sys.executable,'-X','utf8','-m','unittest','discover','-s','tools/tests','-v'])]
    results=[]
    for name,cmd in tests:
        start=time.monotonic()
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            run=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUTF8':'1'})
        results.append({'name':name,'passed':run.returncode==0,'seconds':round(time.monotonic()-start,2)})
        print(name+(': PASS' if run.returncode==0 else ': FAIL'),flush=True)
    (output/'results.json').write_text(json.dumps(results,indent=2)+'\n','utf-8')
    return 0 if all(r['passed'] for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
