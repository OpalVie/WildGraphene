"""Exercise actual shallow Git fetches rather than mocking patch extraction."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/refresh-kernel-snapshot.py'
spec=importlib.util.spec_from_file_location('refresh_shallow',SCRIPT)
refresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(refresh)


def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True,stderr=subprocess.DEVNULL).strip()


class ShallowFix(unittest.TestCase):
    def setup_repos(self,root,unexpected=False):
        source=root/'upstream';source.mkdir()
        git(source,'init','-q')
        git(source,'config','user.name','Test')
        git(source,'config','user.email','test@example.invalid')
        file=source/'kernel_patches/fs/susfs.c';file.parent.mkdir(parents=True)
        file.write_text('before\n')
        (source/'LICENSE').write_text('unchanged license\n')
        git(source,'add','.');git(source,'commit','-qm','base')
        base=git(source,'rev-parse','HEAD')
        file.write_text('after\n')
        if unexpected: (source/'LICENSE').write_text('unexpected change\n')
        git(source,'add','.');git(source,'commit','-qm','fix')
        fix=git(source,'rev-parse','HEAD')
        target=root/'target';target.mkdir();git(target,'init','-q')
        url=source.as_uri()
        git(target,'fetch','--depth','1',url,base)
        git(target,'checkout','--detach','FETCH_HEAD')
        return target,url,fix

    def test_reproduces_original_root_diff_then_applies_only_real_fix(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,url,fix=self.setup_repos(root)
            git(target,'fetch','--depth','1',url,fix)
            wrong=git(target,'show','--format=','--binary',fix)
            self.assertIn('new file mode',wrong)
            self.assertIn('diff --git a/LICENSE',wrong)
            self.assertTrue(refresh.apply_susfs_fix(target,fix,root,remote=url))
            self.assertEqual((target/'kernel_patches/fs/susfs.c').read_text(),'after\n')
            self.assertEqual((target/'LICENSE').read_text(),'unchanged license\n')
            diff=git(target,'diff','--name-only')
            self.assertEqual(diff,'kernel_patches/fs/susfs.c')
            self.assertNotIn('new file mode',(root/(fix+'.patch')).read_text())

    def test_already_present_fix_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,url,fix=self.setup_repos(root)
            (target/'kernel_patches/fs/susfs.c').write_text('after\n')
            self.assertFalse(refresh.apply_susfs_fix(target,fix,root,remote=url))

    def test_unexpected_extra_files_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target,url,fix=self.setup_repos(root,unexpected=True)
            with self.assertRaisesRegex(ValueError,'Unexpected files'):
                refresh.apply_susfs_fix(target,fix,root,remote=url)
            self.assertEqual((target/'LICENSE').read_text(),'unchanged license\n')
            self.assertEqual((target/'kernel_patches/fs/susfs.c').read_text(),'before\n')


if __name__=='__main__': unittest.main()
