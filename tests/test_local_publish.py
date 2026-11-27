"""Verify publication stops on changed bytes and updates the feed last."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/publish-local-update.sh'
MOCK='''#!/usr/bin/env python3
import json,os,shutil,sys
from pathlib import Path
args=sys.argv[1:]
name=Path(sys.argv[0]).name
with open(os.environ['MOCK_LOG'],'a') as out: out.write(name+' '+ ' '.join(args)+'\\n')
if name=='gh' and args[:2]==['release','download']:
    dest=Path(args[args.index('--dir')+1])
    for p in Path(os.environ['MOCK_REMOTE']).iterdir(): shutil.copyfile(p,dest/p.name)
if name=='gh' and args[:1]==['api']:
    if '--method' not in args:
        sys.stderr.write('HTTP 404: Not Found');sys.exit(1)
    payload=json.load(sys.stdin)
    assert payload['branch']=='main'
'''


class Publishing(unittest.TestCase):
    def run_publish(self, local_tamper=False, remote_tamper=False, wrong_feed=False):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir();remote=root/'remote';remote.mkdir()
            binaries=root/'.local/bin';binaries.mkdir(parents=True)
            (root/'pixel-tablet/tmp').mkdir(parents=True)
            for name in ['gh','avbroot','custota-tool']:
                p=binaries/name;p.write_text(MOCK);p.chmod(0o755)
            tag='tangorpro-2026111800-r123'
            ota='tangorpro-test.zip'
            url=f'https://github.com/OpalVie/WildGraphene/releases/download/{tag}/{ota}'
            feed={'full':{'location_ota':url,'location_csig':url+'.csig'}}
            if wrong_feed: feed['full']['location_ota']='https://example.test/wrong.zip'
            files={ota:b'ota',ota+'.csig':b'signature','release-tag.txt':(tag+'\n').encode(),
                   'tangorpro.json':json.dumps(feed).encode()}
            sums=''
            for name,data in files.items():
                (out/name).write_bytes(data);(remote/name).write_bytes(data)
                sums+=hashlib.sha256(data).hexdigest()+'  '+name+'\n'
            (out/'SHA256SUMS').write_text(sums);(remote/'SHA256SUMS').write_text(sums)
            if local_tamper: (out/ota).write_bytes(b'changed')
            if remote_tamper: (remote/ota).write_bytes(b'changed')
            log=root/'calls'
            env={**os.environ,'HOME':str(root),'MOCK_LOG':str(log),'MOCK_REMOTE':str(remote),
                 'PATH':str(binaries)+':'+os.environ['PATH']}
            result=subprocess.run(['bash',str(SCRIPT),str(out)],env=env,capture_output=True,text=True)
            return result,log.read_text() if log.exists() else ''

    def test_changed_local_ota_stops_before_any_network(self):
        result,calls=self.run_publish(local_tamper=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(calls,'')

    def test_changed_uploaded_ota_cannot_be_published(self):
        result,calls=self.run_publish(remote_tamper=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('release edit',calls);self.assertNotIn('gh api',calls)

    def test_wrong_feed_url_stops(self):
        result,calls=self.run_publish(wrong_feed=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(calls,'')

    def test_feed_updates_only_after_verified_assets_and_promotion(self):
        result,calls=self.run_publish()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertLess(calls.index('avbroot ota verify'),calls.index('release download'))
        self.assertLess(calls.index('release download'),calls.index('release edit'))
        self.assertLess(calls.index('release edit'),calls.index('gh api'))


if __name__=='__main__': unittest.main()
