#!/usr/bin/env python3
"""Package fixed-layout C3 candidates. Does not connect to or write a device."""
import argparse, hashlib, json, struct, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLASH_SIZE, SLOT_SIZE = 0x400000, 0x1a0000

def sha(data): return hashlib.sha256(data).hexdigest()

def verify_esp_image(data):
    """Check C3 segment boundaries, ESP checksum and appended SHA-256 offline."""
    if len(data) < 24 or data[0] != 0xe9 or struct.unpack_from('<H',data,12)[0] != 5:
        raise ValueError('Expected an ESP32-C3 image')
    cursor, checksum = 24, 0xef
    if not 1 <= data[1] <= 16: raise ValueError('Invalid image segment count')
    for _ in range(data[1]):
        if cursor + 8 > len(data): raise ValueError('Truncated segment header')
        length = struct.unpack_from('<I', data, cursor + 4)[0]
        cursor += 8
        if cursor + length > len(data): raise ValueError('Truncated segment')
        for value in data[cursor:cursor+length]: checksum ^= value
        cursor += length
    end = (cursor // 16 + 1) * 16
    if end > len(data) or data[end-1] != checksum: raise ValueError('ESP checksum mismatch')
    if data[23] != 1 or len(data) != end + 32 or hashlib.sha256(data[:end]).digest() != data[end:]:
        raise ValueError('ESP appended SHA-256 mismatch')

def image_identity(data):
    if len(data) < 288 or data[0] != 0xe9 or struct.unpack_from('<H',data,12)[0] != 5:
        raise ValueError('Expected an ESP32-C3 application image')
    if struct.unpack_from('<I',data,32)[0] != 0xabcd5432:
        raise ValueError('Missing ESP-IDF application descriptor')
    def string(offset): return data[32+offset:32+offset+32].split(b'\0',1)[0].decode('ascii')
    result = dict(version=string(16),project=string(48),idf=string(112),elf_sha256=data[176:208].hex())
    if result['project'] != 'sms_forwarding_dual' or '-dual.' not in result['version']:
        raise ValueError('Single-modem or unrelated firmware rejected')
    if result['idf'] not in ('v5.5.5', 'v5.5.5-dirty') or len(data) > SLOT_SIZE:
        raise ValueError('SDK version or OTA slot size mismatch')
    return result

def package(build, output):
    # Re-audit instead of trusting a stale PASS file or an image's version string.
    from verify_build import verify
    from upstream_lock import read_lock
    upstream = read_lock(ROOT)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    description = json.loads((build/'project_description.json').read_text('utf-8'))
    verify(build, Path(description['idf_path']).resolve())
    app = (build/'sms_forwarding_dual.bin').read_bytes()
    identity = image_identity(app)
    if output is None:
        output = ROOT / 'dist' / (identity['version'] + '-up' + upstream['commit'][:12] + '-src' + head[:12] + '-candidate')
    output.mkdir(parents=True,exist_ok=True)
    files = {'ota.bin':app, 'bootloader.bin':(build/'bootloader/bootloader.bin').read_bytes(),
             'partition-table.bin':(build/'partition_table/partition-table.bin').read_bytes()}
    for name in ('ota.bin', 'bootloader.bin'): verify_esp_image(files[name])
    if sha((build/'sms_forwarding_dual.elf').read_bytes()) != identity['elf_sha256']:
        raise ValueError('ELF and application descriptor differ')
    # FF intentionally replaces previous NVS, OTA metadata, app slots and inbox/config partition.
    # It never accesses the modem's own SMS storage. Installation always requires a verified backup.
    full = bytearray(b'\xff'*FLASH_SIZE)
    for offset,limit,name in [(0,0x8000,'bootloader.bin'),(0x8000,0x1000,'partition-table.bin'),(0x10000,SLOT_SIZE,'ota.bin')]:
        payload = files[name]
        if len(payload)>limit: raise ValueError(f'{name} does not fit')
        full[offset:offset+len(payload)] = payload
    files['first-install-4MB.bin'] = bytes(full)
    files['environment-audit.json'] = (build/'environment-audit.json').read_bytes()
    files['README.md'] = (ROOT/'dev_doc/upstream_dual_modem.md').read_bytes()
    for name,data in files.items(): (output/name).write_bytes(data)
    tracked = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).split(b'\0')
    source_hashes = {p.decode('utf-8'):sha((ROOT/p.decode('utf-8')).read_bytes()) for p in tracked if p and (ROOT/p.decode('utf-8')).is_file()}
    (output/'source-manifest.json').write_text(json.dumps(source_hashes,ensure_ascii=False,indent=2)+'\n','utf-8')
    manifest = {'status':'CANDIDATE_HARDWARE_PENDING','upstream_commit':upstream['commit'],
                'upstream_repository':upstream['repository'],'git_head':head,**identity,
                'chip':'esp32c3','flash_bytes':FLASH_SIZE,'ota_slot_bytes':SLOT_SIZE,
                'first_install_resets_business_configuration':True,'hardware_acceptance':False,
                'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in files.items()},
                'source_manifest_sha256':sha((output/'source-manifest.json').read_bytes())}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(f'{sha(data)}  {name}\n' for name,data in files.items()),'ascii')
    print(json.dumps({'output':str(output),'version':identity['version'],'app_bytes':len(app),'slot_free':SLOT_SIZE-len(app),'status':manifest['status']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'build/idf5.5.5')
    p.add_argument('--output',type=Path)
    args=p.parse_args();package(args.build.resolve(),args.output.resolve() if args.output else None)
