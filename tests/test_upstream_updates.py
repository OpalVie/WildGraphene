"""Test discovery identity, GrapheneOS patch adaptation, and artifact consistency."""
import importlib.util
import json
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'


def load(name):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


track=load('track-upstreams')
refresh=load('refresh-kernel-snapshot')
validate=load('validate-prepared-update')


class DiscoveryTests(unittest.TestCase):
    def test_annotated_release_tag_uses_commit_not_tag_object(self):
        tag='refs/tags/2026111800'
        text='a'*40+'\t'+tag+'\n'+'b'*40+'\t'+tag+'^{}\n'
        with patch.object(track.subprocess,'check_output',return_value=text):
            self.assertEqual(track.remote_commit('https://example.test/repo',tag),'b'*40)

    def run_discovery(self, ksu_changed=False):
        baseline=track.baseline()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'candidate.json'; outputs=Path(d)/'outputs'
            commits=[baseline['wrapper_commit'], 'f'*40 if ksu_changed else baseline['kernelsu_next_commit'], baseline['susfs_base_commit']]
            with patch('sys.argv',['track-upstreams.py','--output',str(out)]), \
                 patch.dict(os.environ,{'GITHUB_OUTPUT':str(outputs)}), \
                 patch.object(track.urllib.request,'urlopen',return_value=io.BytesIO(b'2026111800 1794968526 tangorpro stable')), \
                 patch.object(track,'remote_commit',side_effect=commits), \
                 patch('builtins.print'):
                track.main()
            return outputs.read_text(),json.loads(out.read_text())

    def test_unchanged_upstreams_skip_scheduled_build(self):
        output,state=self.run_discovery()
        self.assertIn('build=false',output)

    def test_kernelsu_update_triggers_build_without_os_update(self):
        output,state=self.run_discovery(ksu_changed=True)
        self.assertIn('build=true',output)
        self.assertEqual(state['release'],'2026111800')
        self.assertEqual(state['kernelsu_next_commit'],'f'*40)

    def test_missing_ref_fails(self):
        with patch.object(track.subprocess,'check_output',return_value=''):
            with self.assertRaises(ValueError): track.remote_commit('url','refs/heads/dev-susfs')

    def test_each_upstream_independently_triggers_new_fingerprint(self):
        state={'release':'2026111800','wrapper_commit':'a'*40,'kernelsu_next_commit':'b'*40,'susfs_base_commit':'c'*40}
        for key in state:
            changed=dict(state);changed[key]='2026112800' if key=='release' else 'd'*40
            self.assertNotEqual(track.fingerprint(state),track.fingerprint(changed))


class PatchTests(unittest.TestCase):
    def test_known_graphene_includes_preserved(self):
        patch_text='''@@ -64,6 +64,9 @@
 #include <linux/io_uring.h>
 #include <linux/syscall_user_dispatch.h>
 #include <linux/coredump.h>
+#ifdef CONFIG_KSU_SUSFS
+#include <linux/susfs_def.h>
+#endif
@@ -43,6 +43,21 @@
 #include "conditional.h"
 #include "ima.h"
\x20
+functional change retained
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'fs').mkdir();(root/'security/selinux').mkdir(parents=True)
            (root/'fs/exec.c').write_text('#include <linux/random.h>\n')
            (root/'security/selinux/selinuxfs.c').write_text('#include "ss/services.h"\n#include "ss/symtab.h"\n')
            result=refresh.adapt_patch(patch_text,root)
            self.assertIn(' #include <linux/random.h>\n+#ifdef',result)
            self.assertIn(' #include "ss/services.h"\n #include "ss/symtab.h"',result)
            self.assertIn('+functional change retained',result)

    def test_unknown_kbuild_layout_stops(self):
        with self.assertRaises(ValueError): refresh.pin_kbuild('new upstream layout',33647,'v3.4.2','a'*40)

    def test_manager_version_pinned_without_network_commands(self):
        text='# Check if this is a git repository\nfetch old branch\nKSU_NEW_DCACHE_FLUSH := value\n'
        result=refresh.pin_kbuild(text,33647,'v3.4.2','a'*40)
        self.assertIn('KSU_VERSION := 33647',result)
        self.assertIn('KSU_VERSION_TAG := v3.4.2',result)
        self.assertNotIn('fetch old branch',result)
        self.assertIn(r'-DKSU_VERSION_TAG=\"$(KSU_VERSION_TAG)\"',result)


class PreparedRecords(unittest.TestCase):
    def test_mixed_kernel_commits_rejected(self):
        state={'release':'2026111800','wrapper_commit':'a'*40,'kernelsu_next_commit':'b'*40,'susfs_base_commit':'c'*40,'fingerprint':'f'}
        provenance={**state,'grapheneos_release':'2026111800','kernelsu_next_commit':'d'*40,'upstream_fingerprint':'f'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,data in [('candidate.json',state),('source-provenance.json',provenance),('ota-config.json',{'release':'2026111800'})]:
                (root/name).write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Mismatched source commit'):
                validate.validate(root)


if __name__=='__main__': unittest.main()
