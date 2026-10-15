#!/usr/bin/env python3
"""Package fixed-layout C3 candidates. Does not connect to or write a device."""
import argparse, hashlib, json, shutil, struct, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLASH_SIZE, SLOT_SIZE = 0x400000, 0x1a0000
UPSTREAM = 'd4271d46f40bca215d2fba966b83051a1a4460be'

def sha(data): return hashlib.sha256(data).hexdigest()

def image_identity(data):
    if len(data) < 288 or data[0] != 0xe9 or struct.unpack_from('<H',data,12)[0] != 5:
        raise ValueError('Expected an ESP32-C3 application image')
    if struct.unpack_from('<I',data,32)[0] != 0xabcd5432:
        raise ValueError('Missing ESP-IDF application descriptor')
    def string(offset): return data[32+offset:32+offset+32].split(b'\0',1)[0].decode('ascii')
    result = dict(version=string(16),project=string(48),idf=string(112),elf_sha256=data[176:208].hex())
    if result['project'] != 'sms_forwarding_dual' or '-dual.' not in result['version']:
        raise ValueError('Single-modem or unrelated firmware rejected')
    if not result['idf'].startswith('v6.0.2') or len(data) > SLOT_SIZE:
        raise ValueError('SDK version or OTA slot size mismatch')
    return result

def package(build, output):
    app = (build/'sms_forwarding_dual.bin').read_bytes()
    identity = image_identity(app)
    output.mkdir(parents=True,exist_ok=True)
    files = {'ota.bin':app, 'bootloader.bin':(build/'bootloader/bootloader.bin').read_bytes(),
             'partition-table.bin':(build/'partition_table/partition-table.bin').read_bytes()}
    # FF intentionally replaces previous NVS, OTA metadata, app slots and inbox/config partition.
    # It never accesses the modem's own SMS storage. Installation always requires a verified backup.
    full = bytearray(b'\xff'*FLASH_SIZE)
    for offset,limit,name in [(0,0x8000,'bootloader.bin'),(0x8000,0x1000,'partition-table.bin'),(0x10000,SLOT_SIZE,'ota.bin')]:
        payload = files[name]
        if len(payload)>limit: raise ValueError(f'{name} does not fit')
        full[offset:offset+len(payload)] = payload
    files['first-install-4MB.bin'] = bytes(full)
    for name,data in files.items(): (output/name).write_bytes(data)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).split(b'\0')
    source_hashes = {p.decode('utf-8'):sha((ROOT/p.decode('utf-8')).read_bytes()) for p in tracked if p and (ROOT/p.decode('utf-8')).is_file()}
    (output/'source-manifest.json').write_text(json.dumps(source_hashes,ensure_ascii=False,indent=2)+'\n','utf-8')
    manifest = {'status':'CANDIDATE_HARDWARE_PENDING','upstream_commit':UPSTREAM,'git_head':head,**identity,
                'chip':'esp32c3','flash_bytes':FLASH_SIZE,'ota_slot_bytes':SLOT_SIZE,
                'first_install_resets_business_configuration':True,'hardware_acceptance':False,
                'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in files.items()},
                'source_manifest_sha256':sha((output/'source-manifest.json').read_bytes())}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(f'{sha(data)}  {name}\n' for name,data in files.items()),'ascii')
    shutil.copy2(ROOT/'dev_doc/upstream_dual_modem.md',output/'README.md')
    print(json.dumps({'output':str(output),'version':identity['version'],'app_bytes':len(app),'slot_free':SLOT_SIZE-len(app),'status':manifest['status']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'build/idf6')
    p.add_argument('--output',type=Path,default=ROOT/'dist/1.1.7-dual.1-candidate')
    args=p.parse_args();package(args.build.resolve(),args.output.resolve())
