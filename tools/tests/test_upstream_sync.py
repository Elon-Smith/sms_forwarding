import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upstream_sync as sync
from upstream_lock import read_lock


def notification(base='a'*40, target='b'*40, previous='c'*40):
    meta={'repository':sync.FORK,'upstream':sync.REPOSITORY,'base_sha':base,'upstream_sha':target,'previous_upstream':previous}
    return {'number':1,'user':{'login':'github-actions[bot]'},'state':'open','labels':[{'name':sync.LABEL}],
            'body':'<!-- '+sync.MARKER+' '+json.dumps(meta)+' -->'}


class FakeGitHub:
    def __init__(self, base, target, issues=None, prs=None):
        self.base=base;self.target=target;self.issues=issues or [];self.prs=prs or [];self.writes=[]
    def ref(self, repo, branch):return self.base if repo==sync.FORK else self.target
    def pulls(self, branch):return self.prs
    def pages(self, path):
        if '/issues?' in path:return self.issues
        if path.endswith('/labels'):return [{'name':sync.LABEL}]
        return []
    def api(self, method, path, data=None):
        if method=='GET' and path.endswith('/issues/1'):return self.issues[0]
        if method=='GET' and '/compare/' in path:return {'commits':[]}
        self.writes.append((method,path,data));return {'number':2,'html_url':'https://example.test/issue/2'}
    def comment(self, number, body, key):self.writes.append(('comment',number,key))


class ApprovalTests(unittest.TestCase):
    def test_exact_approval_and_invalid_inputs(self):
        issue=notification()
        self.assertEqual(sync.validate_approval(issue,'b'*40,'a'*40,sync.OWNER,sync.OWNER)['upstream_sha'],'b'*40)
        for target,base,actor,rerun in [('d'*40,'a'*40,sync.OWNER,sync.OWNER),('b'*40,'d'*40,sync.OWNER,sync.OWNER),('b'*40,'a'*40,'someone',sync.OWNER),('b'*40,'a'*40,sync.OWNER,'someone')]:
            with self.subTest(actor=actor,base=base):
                with self.assertRaises(ValueError):sync.validate_approval(issue,target,base,actor,rerun)
        for change in ('author','closed','metadata','label','pr'):
            bad=copy.deepcopy(issue)
            if change=='author':bad['user']['login']='someone'
            if change=='closed':bad['state']='closed'
            if change=='metadata':bad['body']=bad['body'].replace('b'*40,'HEAD; echo injected')
            if change=='label':bad['labels']=[]
            if change=='pr':bad['pull_request']={ 'url':'unexpected' }
            with self.assertRaises(ValueError):sync.validate_approval(bad,'b'*40,'a'*40,sync.OWNER,sync.OWNER)

    def test_duplicate_approval_does_not_merge_or_build(self):
        issue=notification();gh=FakeGitHub('a'*40,'b'*40,[issue],[{'html_url':'existing'}])
        with patch.dict(os.environ,{'GITHUB_ACTOR':sync.OWNER,'GITHUB_TRIGGERING_ACTOR':sync.OWNER}), \
             patch.object(sync,'git',return_value='a'*40),patch.object(sync,'read_lock',return_value={'commit':'c'*40}), \
             patch.object(sync,'merge_candidate') as merge,patch.object(sync,'output') as out:
            sync.prepare(Path('.'),gh,1,'b'*40)
            merge.assert_not_called();out.assert_called_once_with(prepared='false')

    def test_detection_deduplicates_and_never_creates_pr(self):
        lock={'commit':'c'*40}
        with patch.object(sync,'read_lock',return_value=lock),patch.object(sync,'git',return_value='a'*40),patch.object(sync,'ancestor',return_value=False):
            for gh in (FakeGitHub('a'*40,'c'*40),FakeGitHub('a'*40,'b'*40,[notification()]),FakeGitHub('a'*40,'b'*40,prs=[{'html_url':'pr'}])):
                sync.detect(Path('.'),gh);self.assertEqual(gh.writes,[])
            gh=FakeGitHub('a'*40,'b'*40);sync.detect(Path('.'),gh)
            self.assertEqual(len(gh.writes),1)
            self.assertTrue(gh.writes[0][1].endswith('/issues'))
            self.assertIn('b'*40,gh.writes[0][2]['body'])

    def test_stale_request_is_closed_and_rechecked(self):
        gh=FakeGitHub('d'*40,'b'*40,[notification()])
        with patch.dict(os.environ,{'GITHUB_ACTOR':sync.OWNER,'GITHUB_TRIGGERING_ACTOR':sync.OWNER}), \
             patch.object(sync,'git',return_value='d'*40),patch.object(sync,'detect') as detect,patch.object(sync,'merge_candidate') as merge:
            sync.prepare(Path('.'),gh,1,'b'*40)
            detect.assert_called_once();merge.assert_not_called()
            self.assertIn(('PATCH','/repos/'+sync.FORK+'/issues/1',{'state':'closed'}),gh.writes)

    def test_finalize_only_readies_successful_unchanged_pr(self):
        from unittest.mock import Mock
        gh=Mock();pr={'head':{'sha':'a'*40,'repo':{'full_name':sync.FORK}},'base':{'ref':sync.BASE},'draft':True,'node_id':'PR_NODE','html_url':'pr'}
        gh.api.side_effect=lambda method,path,data=None: pr if method=='GET' else {'data':{}}
        with patch.dict(os.environ,{'GITHUB_RUN_ID':'123'}):
            sync.finalize(gh,1,2,'a'*40,'failure')
            self.assertFalse(any(call.args[0]=='POST' for call in gh.api.call_args_list))
            gh.reset_mock();sync.finalize(gh,1,2,'a'*40,'success')
            self.assertTrue(any(call.args[0]=='POST' and call.args[1]=='/graphql' for call in gh.api.call_args_list))
            with self.assertRaises(ValueError):sync.finalize(gh,1,2,'b'*40,'success')


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        sync.git(self.root,'init','-b','main')
        self.write('shared.txt','baseline\n');self.previous=self.commit('upstream baseline')
        self.write('upstream.lock.json',json.dumps({'repository':sync.REPOSITORY,'branch':'master','commit':self.previous,'sdk_version':'5.5.5'}))
        self.write('dual.txt','local dual behavior\n');self.base=self.commit('dual baseline')
        sync.git(self.root,'branch','dual',self.base)
        sync.git(self.root,'checkout','--detach',self.previous)
    def tearDown(self):self.temp.cleanup()
    def write(self,name,text):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    def commit(self,text):
        sync.git(self.root,'add','.');sync.git(self.root,'commit','-m',text);return sync.git(self.root,'rev-parse','HEAD')
    def test_clean_merge_preserves_history_and_lock(self):
        self.write('upstream-feature.txt','new feature');target=self.commit('upstream addition')
        head=sync.merge_candidate(self.root,self.base,target,self.previous)
        self.assertEqual(sync.git(self.root,'show','-s','--format=%P',head),self.base+' '+target)
        self.assertEqual(read_lock(self.root)['commit'],target)
        self.assertEqual(sync.git(self.root,'rev-parse','dual'),self.base)
        self.assertEqual((self.root/'dual.txt').read_text(),'local dual behavior\n')
    def test_text_conflict_does_not_move_baseline(self):
        self.write('shared.txt','upstream change\n');target=self.commit('conflicting upstream')
        sync.git(self.root,'checkout','--detach',self.base);self.write('shared.txt','dual change\n');base=self.commit('local change')
        with self.assertRaisesRegex(ValueError,'Merge conflicts: shared.txt'):sync.merge_candidate(self.root,base,target,self.previous)
        self.assertEqual(sync.git(self.root,'rev-parse','HEAD'),base)
        self.assertFalse((self.root/'.git/MERGE_HEAD').exists())
    def test_sdk_and_workflow_changes_stop_before_merge(self):
        self.write('CMakeLists.txt','set(IDF_VERSION 6.0.2)');self.write('.github/workflows/new.yml','unsafe')
        target=self.commit('SDK and workflow changed')
        with self.assertRaisesRegex(ValueError,'protected build/sync'):sync.merge_candidate(self.root,self.base,target,self.previous)
        self.assertEqual(sync.git(self.root,'rev-parse','dual'),self.base)
    def test_rewritten_history_rejected(self):
        sync.git(self.root,'checkout','--orphan','rewritten');sync.git(self.root,'rm','-rf','.')
        self.write('fresh','new root');target=self.commit('unrelated')
        with self.assertRaisesRegex(ValueError,'history changed'):sync.merge_candidate(self.root,self.base,target,self.previous)
    def test_invalid_sdk_lock_and_nonancestor_rejected(self):
        sync.git(self.root,'checkout','--detach',self.base)
        lock=read_lock(self.root);lock['sdk_version']='6.0.2';self.write('upstream.lock.json',json.dumps(lock))
        with self.assertRaises(ValueError):read_lock(self.root)
        lock['sdk_version']='5.5.5';lock['commit']='f'*40;self.write('upstream.lock.json',json.dumps(lock))
        with self.assertRaises(Exception):read_lock(self.root)


if __name__=='__main__':unittest.main()
