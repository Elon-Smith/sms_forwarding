#!/usr/bin/env python3
"""GitHub 上游提醒及人工批准同步。控制脚本不执行候选源码或连接设备。"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from upstream_lock import REPOSITORY, BRANCH, read_lock

OWNER = 'Elon-Smith'
FORK = OWNER + '/sms_forwarding'
BASE = 'codex/upstream-dual-modem'
LABEL = 'upstream-sync'
MARKER = 'dual-upstream-request-v1'
PROTECTED = (
    '.github/workflows/', 'patches/', 'tools/upstream_sync.py', 'tools/upstream_lock.py',
    'tools/package_candidate.py', 'tools/verify_build.py', 'tools/apply_idf_patches.py',
    'tools/idf.ps1', 'tools/build.ps1', 'upstream.lock.json', 'CMakeLists.txt',
    'sdkconfig.defaults', 'partitions_ota_1m6.csv',
)


def git(root, *args, check=True, env=None):
    p = subprocess.run(['git', '-C', str(root), '-c', 'core.hooksPath=/dev/null',
                       '-c', 'user.name=github-actions[bot]', '-c',
                       'user.email=41898282+github-actions[bot]@users.noreply.github.com', *args],
                       text=True, encoding='utf-8', errors='replace', capture_output=True,
                       env=env, check=False)
    if check and p.returncode:
        raise RuntimeError('git ' + args[0] + ' failed: ' + p.stderr.strip())
    return p.stdout.strip() if check else p


def ancestor(root, older, newer):
    return git(root, 'merge-base', '--is-ancestor', older, newer, check=False).returncode == 0


def guard_paths(paths):
    return sorted(p for p in paths if any(p.startswith(x) if x.endswith('/') else p == x for x in PROTECTED))


def mirror_needs_update(root, mirror, target):
    if mirror == target:
        return False
    if ancestor(root, mirror, target):
        return True
    if ancestor(root, target, mirror):
        return False
    raise ValueError('Upstream mirror has diverged; refusing to overwrite')


def parse_request(issue):
    if issue.get('user', {}).get('login') != 'github-actions[bot]' or issue.get('pull_request'):
        raise ValueError('Only workflow-created notification issues are accepted')
    if LABEL not in [x['name'] for x in issue.get('labels', [])]:
        raise ValueError('Missing upstream notification label')
    matches = re.findall(r'<!-- ' + MARKER + r' (\{[^\n]+\}) -->', issue.get('body', ''))
    if len(matches) != 1:
        raise ValueError('Invalid notification metadata')
    data = json.loads(matches[0])
    if data.get('repository') != FORK or data.get('upstream') != REPOSITORY:
        raise ValueError('Unexpected notification repository')
    for key in ('base_sha', 'upstream_sha', 'previous_upstream'):
        if not re.fullmatch('[0-9a-f]{40}', data.get(key, '')):
            raise ValueError('Invalid notification SHA')
    return data


def validate_approval(issue, target, current_base, actor, triggering_actor):
    if actor != OWNER or triggering_actor != OWNER:
        raise ValueError('Only the repository owner may approve or re-run synchronization')
    data = parse_request(issue)
    if issue.get('state') != 'open':
        raise ValueError('Notification is closed; request a fresh check')
    if target != data['upstream_sha']:
        raise ValueError('Approved SHA does not match notification')
    if current_base != data['base_sha']:
        raise ValueError('Dual-modem baseline changed; a new approval is required')
    return data


def merge_candidate(root, base, target, previous):
    """仅在隔离仓库调用。冲突退出后不提交，不选择 ours/theirs。"""
    if not ancestor(root, previous, target):
        raise ValueError('Upstream history changed: previous commit is not an ancestor')
    changed = git(root, 'diff', '--name-only', previous, target).splitlines()
    protected = guard_paths(changed)
    if protected:
        raise ValueError('Manual adaptation required for protected build/sync files: ' + ', '.join(protected))
    git(root, 'checkout', '--detach', base)
    result = git(root, 'merge', '--no-commit', '--no-ff', target, check=False)
    if result.returncode:
        conflicts = git(root, 'diff', '--name-only', '--diff-filter=U').splitlines()
        git(root, 'merge', '--abort', check=False)
        raise ValueError('Merge conflicts: ' + ', '.join(conflicts or ['see merge diagnostics']))
    lock = read_lock(root)
    lock['commit'] = target
    (Path(root) / 'upstream.lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    git(root, 'add', 'upstream.lock.json')
    git(root, '-c', 'user.name=github-actions[bot]', '-c',
        'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', 'Merge approved upstream ' + target[:12] + ' with ESP-IDF 5.5.5 retained')
    return git(root, 'rev-parse', 'HEAD')


class GitHub:
    def __init__(self):
        self.token = os.environ['GH_TOKEN']

    def api(self, method, path, data=None):
        req = urllib.request.Request('https://api.github.com' + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization':'Bearer ' + self.token, 'Accept':'application/vnd.github+json',
                     'X-GitHub-Api-Version':'2022-11-28', 'Content-Type':'application/json',
                     'User-Agent':'dual-modem-upstream-sync'})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError('GitHub HTTP ' + str(exc.code) + ': ' + exc.read().decode()) from None

    def pages(self, path):
        rows = []
        for page in range(1, 101):
            batch = self.api('GET', path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise RuntimeError('Pagination exceeded safety bound')

    def ref(self, repo, branch):
        return self.api('GET', f'/repos/{repo}/git/ref/heads/{branch}')['object']['sha']

    def pulls(self, branch):
        return self.pages(f'/repos/{FORK}/pulls?state=all&head={OWNER}:{branch}&base={BASE}')

    def comment(self, number, body, key):
        marker = '<!-- dual-sync-result:' + key + ' -->'
        for old in self.pages(f'/repos/{FORK}/issues/{number}/comments'):
            if old['user']['login'] == 'github-actions[bot]' and marker in old['body']:
                return self.api('PATCH', f'/repos/{FORK}/issues/comments/{old["id"]}', {'body':body + '\n' + marker})
        return self.api('POST', f'/repos/{FORK}/issues/{number}/comments', {'body':body + '\n' + marker})


def output(**values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            for key, value in values.items():
                f.write(f'{key}={value}\n')


def summary(message):
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(message + '\n')


def detect(root, gh):
    lock = read_lock(root)
    base = gh.ref(FORK, BASE)
    if git(root, 'rev-parse', 'HEAD') != base:
        raise ValueError('Default branch changed during detection; retry check')
    target = gh.ref(REPOSITORY, BRANCH)
    if target == lock['commit'] or ancestor(root, target, base):
        summary('当前没有新的上游提交。没有创建提醒、PR 或候选固件。')
        return
    branch = 'codex/sync-upstream-' + target[:12]
    if gh.pulls(branch):
        summary('本次上游已有同步 PR，不重复创建。')
        return
    issues = gh.pages(f'/repos/{FORK}/issues?state=all&labels={LABEL}')
    for old in issues:
        try:
            data = parse_request(old)
        except ValueError:
            continue
        if data['base_sha'] == base and data['upstream_sha'] == target:
            summary('相同更新已提醒；保持原有处理状态，不重复通知。')
            return
    # 仅使旧提醒失效；不扩大任何已经批准的请求。
    for old in issues:
        try:
            data = parse_request(old)
        except ValueError:
            continue
        if old['state'] == 'open' and data['base_sha'] != base:
            gh.comment(old['number'], '双模组基线已改变，本提醒已失效；请使用最新提醒重新批准。', 'stale')
            gh.api('PATCH', f'/repos/{FORK}/issues/{old["number"]}', {'state':'closed'})
    labels = gh.pages(f'/repos/{FORK}/labels')
    if not any(x['name'] == LABEL for x in labels):
        gh.api('POST', f'/repos/{FORK}/labels', {'name':LABEL,'color':'1d76db','description':'人工批准后同步上游'})
    comparison = gh.api('GET', f'/repos/{REPOSITORY}/compare/{lock["commit"]}...{target}')
    commits = comparison.get('commits', [])
    lines = ['- `' + x['sha'][:12] + '` ' + x['commit']['message'].splitlines()[0].replace('@', '@\u200b') for x in commits[:30]]
    meta = {'repository':FORK,'upstream':REPOSITORY,'base_sha':base,'upstream_sha':target,'previous_upstream':lock['commit']}
    body = ('发现上游更新，尚未创建 PR 或构建固件。\n\n'
        f'- 上游：`{lock["commit"]}` → `{target}`\n- 双模组基线：`{base}`\n'
        f'- [查看变更](https://github.com/{REPOSITORY}/compare/{lock["commit"]}...{target})\n'
        f'- [批准同步并构建](https://github.com/{FORK}/actions/workflows/upstream-approve.yml)：点击 **Run workflow**，填写本 Issue 编号和上述完整上游 SHA。\n\n'
        '批准仅创建待审核 PR 和候选固件，不自动合并或烧录。SDK 固定 5.5.5。\n\n' + '\n'.join(lines) + '\n\n'
        '<!-- ' + MARKER + ' ' + json.dumps(meta, separators=(',', ':')) + ' -->')
    issue = gh.api('POST', f'/repos/{FORK}/issues', {'title':'上游更新待批准：' + target[:12], 'body':body,'labels':[LABEL],'assignees':[OWNER]})
    summary('已创建更新提醒：' + issue['html_url'])


def prepare(root, gh, number, target):
    output(prepared='false')
    if not re.fullmatch('[0-9a-f]{40}', target):
        raise ValueError('Enter the full upstream SHA from the notification')
    issue = gh.api('GET', f'/repos/{FORK}/issues/{number}')
    current = gh.ref(FORK, BASE)
    try:
        data = validate_approval(issue, target, current, os.environ.get('GITHUB_ACTOR'), os.environ.get('GITHUB_TRIGGERING_ACTOR'))
    except ValueError as exc:
        if str(exc).startswith('Dual-modem baseline changed'):
            gh.comment(number, '双模组基线已变化，旧批准请求失效。将重新检查上游，请批准新提醒。', 'stale')
            gh.api('PATCH', f'/repos/{FORK}/issues/{number}', {'state':'closed'})
            if git(root, 'rev-parse', 'HEAD') == current:
                detect(root, gh)
            summary(str(exc))
            return
        raise
    if git(root, 'rev-parse', 'HEAD') != current:
        raise ValueError('Workflow revision differs from approved baseline')
    lock = read_lock(root)
    if lock['commit'] != data['previous_upstream']:
        raise ValueError('Upstream lock differs from notification')
    branch = 'codex/sync-upstream-' + target[:12]
    existing = gh.pulls(branch)
    if existing:
        gh.comment(number, '已有同步 PR，不重复构建：' + existing[0]['html_url'], 'existing')
        summary('重复批准已跳过：' + existing[0]['html_url'])
        return
    try:
        with tempfile.TemporaryDirectory(prefix='dual-upstream-') as temp:
            git(root, 'clone', '--no-checkout', '--no-local', str(root), temp)
            git(temp, 'fetch', '--no-tags', 'https://github.com/' + REPOSITORY + '.git', BRANCH)
            if not ancestor(temp, target, 'FETCH_HEAD'):
                raise ValueError('Approved commit is no longer in upstream master history')
            head = merge_candidate(temp, current, target, lock['commit'])
            if gh.ref(FORK, BASE) != current:
                raise ValueError('Baseline changed while merging; re-approval required')
            # 该进程只执行 git，不执行候选源码。令牌只在此 push 的环境中传递。
            authorization = base64.b64encode(('x-access-token:' + gh.token).encode()).decode()
            env = {**os.environ,'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'http.https://github.com/.extraheader',
                   'GIT_CONFIG_VALUE_0':'AUTHORIZATION: basic ' + authorization,'GIT_TERMINAL_PROMPT':'0'}
            remote = 'https://github.com/' + FORK + '.git'
            saved = git(temp, 'ls-remote', '--heads', remote, 'refs/heads/' + branch)
            if saved:
                git(temp, 'fetch', '--no-tags', remote, branch)
                saved_head = git(temp, 'rev-parse', 'FETCH_HEAD')
                if git(temp, 'show', '-s', '--format=%P', saved_head) != current + ' ' + target or git(temp, 'rev-parse', saved_head + '^{tree}') != git(temp, 'rev-parse', head + '^{tree}'):
                    raise ValueError('Existing sync branch differs; refusing to overwrite')
                head = saved_head
            else:
                git(temp, 'push', remote, head + ':refs/heads/' + branch, env=env)
            mirror = gh.ref(FORK, BRANCH)
            git(temp, 'fetch', '--no-tags', remote, BRANCH)
            if mirror_needs_update(temp, mirror, target):
                gh.api('PATCH', f'/repos/{FORK}/git/refs/heads/master', {'sha':target,'force':False})
        pr = gh.api('POST', f'/repos/{FORK}/pulls', {'title':'同步上游 ' + target[:12] + '（ESP-IDF 5.5.5）',
            'head':branch,'base':BASE,'draft':True,'body':f'经 @{OWNER} 手动批准，合并上游 `{target}`，双模组基线 `{current}`。\n\n关联提醒 #{number}。SDK 保持 5.5.5；构建结果随后附上。候选未经硬件验收，不自动合并或烧录。'})
        gh.comment(number, '已创建草稿 PR，正在执行主机测试和 5.5.5 构建：' + pr['html_url'], 'prepared')
        output(prepared='true', head=head, pr=pr['number'], issue=number)
        summary('已批准并准备：' + pr['html_url'])
    except (ValueError, RuntimeError) as exc:
        gh.comment(number, '同步已停止，未修改双模组主分支、未构建固件。\n\n```text\n' + str(exc)[:6000] + '\n```\n请处理冲突或适配后重新检查。', 'blocked')
        summary('同步停止：' + str(exc))


def finalize(gh, number, pr_number, head, result):
    pr = gh.api('GET', f'/repos/{FORK}/pulls/{pr_number}')
    if pr['head']['sha'] != head or pr['base']['ref'] != BASE or pr['head']['repo']['full_name'] != FORK:
        raise ValueError('PR changed since the approved build')
    url = f'https://github.com/{FORK}/actions/runs/' + os.environ['GITHUB_RUN_ID']
    message = f'固定 SDK 检查与构建：**{result}**。\n\n[日志及候选产物]({url})，源码 `{head}`。\n\n仍需人工审核及实机验收；没有自动合并或烧录。'
    gh.comment(pr_number, message, 'build-' + head)
    gh.comment(number, message + '\n\nPR：' + pr['html_url'], 'build-' + head)
    if result == 'success' and pr.get('draft'):
        response = gh.api('POST', '/graphql', {'query':'mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{id}}}', 'variables':{'id':pr['node_id']}})
        if response.get('errors'):
            raise RuntimeError('Could not mark PR ready: ' + json.dumps(response['errors']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('detect','prepare','finalize'))
    p.add_argument('--issue', type=int)
    p.add_argument('--sha')
    p.add_argument('--pr', type=int)
    p.add_argument('--head')
    p.add_argument('--result', choices=('success','failure','cancelled','skipped'))
    args = p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != FORK or os.environ.get('GITHUB_REF') != 'refs/heads/' + BASE:
        raise ValueError('Run only on the configured fork default branch')
    root = Path(__file__).resolve().parents[1]
    gh = GitHub()
    if args.action == 'detect':
        detect(root, gh)
    elif args.action == 'prepare':
        if not args.issue or not args.sha: p.error('--issue and --sha required')
        prepare(root, gh, args.issue, args.sha)
    else:
        if not args.issue or not args.pr or not args.head or not args.result: p.error('finalize arguments missing')
        finalize(gh, args.issue, args.pr, args.head, args.result)


if __name__ == '__main__':
    main()
