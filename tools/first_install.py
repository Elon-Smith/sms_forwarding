#!/usr/bin/env python3
"""Explicit first-install tool: identify, read twice, verify backup, write and verify.

Without --apply this only prints the plan and opens no serial port.
Requires the ESP-IDF Python environment (esptool 5.x).
"""
import argparse, datetime, hashlib, json, re, subprocess, sys
from pathlib import Path
from package_candidate import FLASH_SIZE, ROOT, image_identity, sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,default=ROOT/'dist/1.1.7-dual.1-candidate')
    p.add_argument('--port',required=True)
    p.add_argument('--expected-mac',required=True)
    p.add_argument('--backup-dir',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();package=a.package.resolve();backup_root=a.backup_dir.resolve()
    if ROOT==backup_root or ROOT in backup_root.parents: p.error('Backup directory must be outside the source workspace')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',a.expected_mac):p.error('Expected MAC must have six colon-separated bytes')
    manifest=json.loads((package/'manifest.json').read_text('utf-8'))
    for name,meta in manifest['files'].items():
        data=(package/name).read_bytes()
        if len(data)!=meta['bytes'] or sha(data)!=meta['sha256']:raise ValueError('Package hash mismatch: '+name)
    image_identity((package/'ota.bin').read_bytes())
    full=package/'first-install-4MB.bin'
    if full.stat().st_size!=FLASH_SIZE:raise ValueError('Expected a complete 4 MiB installation image')
    print(f'ESP32-C3 {a.expected_mac} on {a.port}: verify 4 MiB Flash, back up twice to {backup_root}, replace ESP Flash, verify. Modem SMS storage is not accessed.')
    if not a.apply:
        print('DRY RUN: no serial port opened. Add --apply only after wiring/power/model inspection.');return
    dest=backup_root/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+a.expected_mac.replace(':',''))
    dest.mkdir(parents=True,exist_ok=False)
    def run(*args):
        cmd=[sys.executable,'-m','esptool','--chip','esp32c3','--port',a.port,'--before','default-reset','--after','no-reset',*map(str,args)]
        result=subprocess.run(cmd,text=True,encoding='utf-8',errors='replace',capture_output=True)
        with (dest/'install.log').open('a',encoding='utf-8') as log:log.write(result.stdout+result.stderr+'\n')
        if result.returncode:raise RuntimeError('esptool failed; inspect '+str(dest/'install.log'))
        return result.stdout+result.stderr
    identity=run('read-mac')
    found=re.findall(r'MAC:\s*((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})',identity)
    if not found or found[-1].lower()!=a.expected_mac.lower():raise ValueError('Connected MAC differs; no Flash write performed')
    flash=run('flash-id')
    if not re.search(r'Detected flash size:\s*4MB',flash,re.I):raise ValueError('A 4 MiB Flash device is required')
    first,second=dest/'original-flash.bin',dest/'original-flash-second-read.bin'
    run('read-flash','0',str(FLASH_SIZE),first)
    run('read-flash','0',str(FLASH_SIZE),second)
    if first.stat().st_size!=FLASH_SIZE or sha(first.read_bytes())!=sha(second.read_bytes()):raise ValueError('Backup reads differ; no Flash write performed')
    (dest/'backup.json').write_text(json.dumps({'mac':a.expected_mac,'port':a.port,'bytes':FLASH_SIZE,'sha256':sha(first.read_bytes()),'package':manifest},indent=2)+'\n','utf-8')
    run('write-flash','--flash-mode','dio','--flash-freq','80m','--flash-size','4MB','0',full)
    run('verify-flash','0',full)
    print('Flash verified. Backup: '+str(dest)+'. Power-cycle, provision afresh, then perform hardware acceptance. This is not a stability pass.')

if __name__=='__main__':main()
