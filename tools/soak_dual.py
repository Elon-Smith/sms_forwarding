#!/usr/bin/env python3
"""Read-only 12-hour sampler; never sends AT, SMS, reboot, reset or configuration requests."""
import argparse, base64, json, os, statistics, time, urllib.request
from pathlib import Path

def analyse(rows, required_hours=12, warmup_seconds=600):
    problems=[]
    good=[r for r in rows if 'status' in r]
    if len(good)!=len(rows): problems.append('采样请求失败')
    if len(good)<2: return {'sample_checks_pass':False,'problems':['采样不足'],'hardware_acceptance':False}
    duration=good[-1]['at']-good[0]['at']
    if duration<required_hours*3600: problems.append('不足连续 12 小时')
    first=good[0]['status']; identity=first.get('firmwareElfSha256')
    if not identity or '-dual.' not in first.get('version',''): problems.append('缺少双卡版本及固定镜像标识')
    for i,r in enumerate(good):
        s=r['status']
        if s.get('firmwareElfSha256')!=identity or s.get('version')!=first.get('version'): problems.append('运行镜像发生变化')
        mods=s.get('modems',[])
        if [m.get('sim') for m in mods]!=[1,2]: problems.append('双卡状态缺失或来源异常')
        if any(m.get('uartErrors',-1)!=0 for m in mods): problems.append('UART 错误或未提供计数')
        if i:
            prev=good[i-1]
            if s.get('uptime',0)<prev['status'].get('uptime',0): problems.append('检测到重启')
            if r['at']-prev['at']>90: problems.append('一分钟采样不连续')
    heaps=[r['status']['freeHeap'] for r in good if r['at']-good[0]['at']>=warmup_seconds and 'freeHeap' in r['status']]
    medians=[]
    if len(heaps)<8: problems.append('堆采样不足')
    else:
        medians=[statistics.median(heaps[i*len(heaps)//4:(i+1)*len(heaps)//4]) for i in range(4)]
        if all(medians[i]>medians[i+1] for i in range(3)) and medians[0]-medians[3]>4096:
            problems.append('预热后四段堆中位数持续下降超过 4 KiB，待排查')
    return {'sample_checks_pass':not problems,'problems':sorted(set(problems)),'samples':len(rows),
            'duration_hours':duration/3600,'heap_quarter_medians':medians,'firmware_elf_sha256':identity,
            'hardware_acceptance':False,'manual_checks_required':'真实短信来源及正文、通知投递、单卡复位隔离、冷启动、Wi-Fi 恢复、OTA 及错误镜像拒绝、供电/电平'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',help='e.g. http://sms.local')
    p.add_argument('--output',type=Path,default=Path('hardware-tests/soak.jsonl'))
    p.add_argument('--analyse',type=Path)
    args=p.parse_args()
    if args.analyse:
        rows=[json.loads(line) for line in args.analyse.read_text('utf-8').splitlines() if line.strip()]
    else:
        if not args.url: p.error('--url or --analyse required')
        user=os.environ.get('SMS_WEB_USER','admin');password=os.environ.get('SMS_WEB_PASSWORD')
        if password is None: p.error('Set SMS_WEB_PASSWORD (never passed in the URL or output)')
        token=base64.b64encode(f'{user}:{password}'.encode()).decode()
        rows=[];args.output.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation prevents mixing runs or silently overwriting acceptance evidence.
        with args.output.open('x',encoding='utf-8') as f:
            start=time.monotonic();deadline=start+12*3600;next_sample=start
            while True:
                time.sleep(max(0,next_sample-time.monotonic()))
                row={'at':time.time()}
                try:
                    req=urllib.request.Request(args.url.rstrip('/')+'/status?sim=1',headers={'Authorization':'Basic '+token})
                    with urllib.request.urlopen(req,timeout=15) as response: row['status']=json.load(response)
                except Exception as exc: row['error']=type(exc).__name__
                # Do not persist phone numbers, ICCIDs, IPs, credentials or SMS bodies.
                if 'status' in row:
                    s=row['status'];row['status']={k:s[k] for k in ('version','firmwareElfSha256','uptime','freeHeap','minFreeHeap','maxAllocHeap') if k in s}
                    row['status']['modems']=[{k:m[k] for k in ('sim','generation','ready','uartErrors','stackFree','smsTotal','phase') if k in m} for m in s.get('modems',[])]
                rows.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                if time.monotonic()>=deadline: break
                next_sample=min(next_sample+60,deadline)
    report=analyse(rows)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['sample_checks_pass'] else 1

if __name__=='__main__': raise SystemExit(main())
