#!/usr/bin/env python3
"""Construct a candidate snapshot; fail on any unhandled source conflict."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None, binary=False):
    return subprocess.check_output([str(a) for a in args], cwd=cwd, text=not binary)


def clone(url, commit, dest, full=False):
    if full:
        run('git','clone','--no-checkout',url,dest)
        run('git','-C',dest,'fetch','origin','dev')
    else:
        dest.mkdir(parents=True)
        run('git','-C',dest,'init','-q')
        run('git','-C',dest,'remote','add','origin',url)
    run('git','-C',dest,'fetch',*(() if full else ('--depth','1')),'origin',commit)
    run('git','-C',dest,'checkout','--detach',commit)
    if run('git','-C',dest,'rev-parse','HEAD').strip() != commit:
        raise ValueError('Checkout does not match resolved commit')


def apply_susfs_fix(repo, commit, temp, remote='https://gitlab.com/pershoot/susfs4ksu.git'):
    # Fetch the parent too: depth=1 makes `git show` treat a commit as a root,
    # generating an add-every-file patch instead of just this compatibility fix.
    run('git','-C',repo,'fetch','--depth','2',remote,commit)
    parents=run('git','-C',repo,'rev-list','--parents','-n','1',commit).split()
    if len(parents) != 2:
        raise ValueError('Compatibility fix must have exactly one available parent')
    parent=parents[1]
    paths=run('git','-C',repo,'diff','--name-only',parent,commit).splitlines()
    if paths != ['kernel_patches/fs/susfs.c']:
        raise ValueError('Unexpected files in SUSFS compatibility fix: '+str(paths))
    patch=run('git','-C',repo,'diff','--binary',parent,commit,binary=True)
    p=temp/(commit+'.patch');p.write_bytes(patch)
    if subprocess.run(['git','-C',str(repo),'apply','--reverse','--check',str(p)],capture_output=True).returncode == 0:
        return False  # This exact fix is already present.
    run('git','-C',repo,'apply','--check',p)
    run('git','-C',repo,'apply',p)
    return True


def adapt_patch(patch, kernel):
    """Only account for the two already-reviewed GrapheneOS include additions.

    Other source changes must apply normally. Never discard failed hunks or
    relax context matching for the functional SUSFS changes.
    """
    exec_path = kernel/'fs/exec.c'
    selinux_path = kernel/'security/selinux/selinuxfs.c'
    old = '@@ -64,6 +64,9 @@\n #include <linux/io_uring.h>\n #include <linux/syscall_user_dispatch.h>\n #include <linux/coredump.h>\n'
    if '#include <linux/random.h>' in exec_path.read_text() and old in patch:
        patch = patch.replace(old, old.replace('-64,6 +64,9','-64,7 +64,10')+' #include <linux/random.h>\n', 1)
    old = '@@ -43,6 +43,21 @@\n #include "conditional.h"\n #include "ima.h"\n'
    includes = '#include "ss/services.h"\n#include "ss/symtab.h"'
    if includes in selinux_path.read_text() and old in patch:
        patch = patch.replace(old, old.replace('-43,6 +43,21','-43,8 +43,23')+' #include "ss/services.h"\n #include "ss/symtab.h"\n', 1)
    return patch.lstrip('\n')


def pin_kbuild(text, version, tag, commit):
    if not re.fullmatch(r'v?[A-Za-z0-9_.+-]+', tag):
        raise ValueError('Unexpected KernelSU version tag')
    start = text.index('# Check if this is a git repository')
    end = text.index('KSU_NEW_DCACHE_FLUSH :=', start)
    replacement = (f'# WildGraphene: pinned KernelSU-Next {commit}\n'
                   f'KSU_VERSION := {version}\nKSU_VERSION_TAG := {tag}\n'
                   'ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n'
                   'ccflags-y += -DKSU_VERSION_TAG=\\"$(KSU_VERSION_TAG)\\"\n\n')
    return text[:start]+replacement+text[end:]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args()
    state=json.loads(args.state.read_text())
    release=state['release']
    if not re.fullmatch(r'\d{10}',release):
        raise ValueError('Invalid release')
    for key in ['wrapper_commit','kernelsu_next_commit','susfs_base_commit']:
        if not re.fullmatch('[0-9a-f]{40}',state[key]):
            raise ValueError('Invalid pinned commit')
    temp=Path(os.environ['RUNNER_TEMP'])
    build=temp/'graphene-kernel-build'
    clone('https://gitlab.com/grapheneos/kernel_pixel_6.1.git',state['wrapper_commit'],build)
    # Ensure the resolved release tag still identifies this wrapper checkout.
    tag=run('git','ls-remote','origin','refs/tags/'+release,'refs/tags/'+release+'^{}',cwd=build)
    refs=dict(line.split()[::-1] for line in tag.splitlines())
    if refs.get('refs/tags/'+release+'^{}',refs.get('refs/tags/'+release)) != state['wrapper_commit']:
        raise ValueError('GrapheneOS release tag changed after discovery')
    run('git','-C',build,'fetch','--depth','1','origin','tag',release)
    if run('git','-C',build,'rev-parse',release+'^{commit}').strip() != state['wrapper_commit']:
        raise ValueError('Fetched GrapheneOS tag differs from resolved commit')
    run('git','-C',build,'submodule','update','--init','--depth','1','common/ack')
    kernel=build/'common/ack'
    kernel_commit=run('git','-C',kernel,'rev-parse','HEAD').strip()
    susfs=temp/'candidate-susfs'
    clone('https://gitlab.com/simonpunk/susfs4ksu.git',state['susfs_base_commit'],susfs)
    provenance=json.loads((ROOT/'kernel/tangorpro/provenance.json').read_text())
    extras=[]
    for commit in provenance['susfs_extra_commits']:
        if apply_susfs_fix(susfs,commit,temp):
            extras.append(commit)
    patch=adapt_patch((susfs/'kernel_patches/50_add_susfs_in_gki-android14-6.1.patch').read_text(),kernel)
    # Retain only the known KernelSU driver wiring from our existing snapshot.
    existing=(ROOT/'kernel/tangorpro/tracked.patch').read_text()
    sections=re.split(r'(?=^diff --git )',existing,flags=re.M)
    driver_patch=''.join(s for s in sections if s.startswith(('diff --git a/drivers/Kconfig ','diff --git a/drivers/Makefile ')))
    if driver_patch.count('diff --git ') != 2:
        raise ValueError('Expected exactly two driver-wiring patch sections')
    snapshot=ROOT/'kernel/tangorpro'
    (snapshot/'tracked.patch').write_text(patch+driver_patch)
    run('git','-C',kernel,'apply','--check',snapshot/'tracked.patch')
    ksu=temp/'candidate-kernelsu'
    clone('https://github.com/pershoot/KernelSU-Next.git',state['kernelsu_next_commit'],ksu,full=True)
    base=run('git','-C',ksu,'merge-base','HEAD','refs/remotes/origin/dev').strip()
    version=30000+int(run('git','-C',ksu,'rev-list','--count',base))
    tag=run('git','-C',ksu,'describe','--tags','--abbrev=0',base).strip()
    archive=run('git','-C',ksu,'archive',state['kernelsu_next_commit'],binary=True)
    overlay=temp/'candidate-overlay'; overlay.mkdir()
    ksu_export=overlay/'KernelSU-Next';ksu_export.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(ksu_export,filter='data')
    kbuild=ksu_export/'kernel/Kbuild'
    kbuild.write_text(pin_kbuild(kbuild.read_text(),version,tag,state['kernelsu_next_commit']))
    for target,source in [('fs/susfs.c','fs/susfs.c'),('include/linux/susfs.h','include/linux/susfs.h'),('include/linux/susfs_def.h','include/linux/susfs_def.h')]:
        dest=overlay/target;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(susfs/'kernel_patches'/source,dest)
    (overlay/'drivers').mkdir();(overlay/'drivers/kernelsu').symlink_to('../KernelSU-Next/kernel')
    with tarfile.open(snapshot/'source-overlay.tar.gz','w:gz') as tar:
        for child in sorted(overlay.iterdir()):
            tar.add(child,arcname=child.name)
    provenance.update(grapheneos_release=release,wrapper_commit=state['wrapper_commit'],kernel_commit=kernel_commit,
                      kernelsu_next_commit=state['kernelsu_next_commit'],kernelsu_version=version,
                      susfs_base_commit=state['susfs_base_commit'],susfs_extra_commits=provenance['susfs_extra_commits'],
                      susfs_fixes_applied=extras,upstream_fingerprint=state['fingerprint'],
                      status='Candidate snapshot. Patch application checked; compilation, packaging and runtime tests pending.')
    (snapshot/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    names=['tracked.patch','source-overlay.tar.gz','provenance.json']
    (snapshot/'SHA256SUMS').write_text(''.join(hashlib.sha256((snapshot/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names))
    config_path=ROOT/'ota/tangorpro.json'
    config=json.loads(config_path.read_text());config['release']=release
    config_path.write_text(json.dumps(config,indent=2)+'\n')
    print(json.dumps(provenance,indent=2))


if __name__=='__main__':
    main()
