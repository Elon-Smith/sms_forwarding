"""校验上游来源；SDK 版本不随上游更新。"""
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = 'MineSunshineone/sms_forwarding'
BRANCH = 'master'
SDK = '5.5.5'


def read_lock(root, check_history=True):
    root = Path(root)
    value = json.loads((root / 'upstream.lock.json').read_text('utf-8'))
    if (value.get('repository'), value.get('branch'), value.get('sdk_version')) != (REPOSITORY, BRANCH, SDK):
        raise ValueError('Unexpected upstream repository, branch or SDK')
    if not re.fullmatch(r'[0-9a-f]{40}', value.get('commit', '')):
        raise ValueError('Upstream commit must be a full SHA-1')
    if check_history:
        result = subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', value['commit'], 'HEAD'], capture_output=True)
        if result.returncode:
            raise ValueError('Locked upstream commit is not an ancestor of the packaged source')
    return value
