#!/usr/bin/env python3
"""Prepare unsigned replacement partitions in scratch; never access private keys."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tomllib

ROOT = AVB = TOOLS = SIGNED = ORIGINAL = None

def run(args, cwd=None, codes=(0,)):
    p=subprocess.run([str(x) for x in args],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode not in codes:
        raise RuntimeError(f'{args}: {p.returncode}\n{p.stdout}\n{p.stderr}')
    return p.stdout

def dbg(image,command):
    return run(['debugfs','-R',command,image])

def inventory(image):
    result={}
    def visit(path):
        st=dbg(image,'stat '+path)
        mode=re.search(r'Mode:\s+0*([0-7]+)',st)[1]
        uid,gid=re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)',st).groups()
        attrs=dbg(image,'ea_list '+path)
        names=re.findall(r'^  ([\w.]+) \(',attrs,re.M)
        if any(n!='security.selinux' for n in names):
            raise ValueError(f'Unsupported xattr at {path}: {names}')
        label=re.search(r'security.selinux \(\d+\) = "([^"\\]+)',attrs)
        result[path]={'mode':mode,'uid':uid,'gid':gid,'label':label[1] if label else None}
        if 'Type: directory' in st:
            for row in dbg(image,'ls -p '+path).splitlines():
                if not row.startswith('/'): continue
                parts=row.split('/')
                name=parts[5]
                if parts[1]=='0' or name in ('','.','..'): continue
                visit(path.rstrip('/')+'/'+name)
    visit('/')
    return result

def rebuild_fs(part):
    d=ROOT/part
    original=ORIGINAL/(part+'.img')
    if not (d/'avb.toml').exists(): run([AVB,'avb','unpack','-q','-i',original],cwd=d)
    raw=d/'raw.img'
    metadata=inventory(raw)
    tree=d/'tree'
    if not tree.exists():
        tree.mkdir()
        dbg(raw,f'rdump / {tree}')
    modules=list(tree.rglob('*.ko'))
    assert modules
    before={str(p.relative_to(tree)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tree.rglob('*') if p.is_file() and p.suffix!='.ko'}
    for p in modules:
        replacement=SIGNED/p.name
        if not replacement.is_file(): raise ValueError(f'Missing rebuilt module {p.name}')
        info=run(['modinfo',replacement])
        if not re.search(r'^signer:\s+\S',info,re.M): raise ValueError(f'Unsigned replacement {p.name}')
        shutil.copyfile(replacement,p)
    fsconfig=d/'fs_config'
    contexts=d/'file_contexts'
    rootstat=metadata['/']
    fsconfig.write_text(f'/ {rootstat["uid"]} {rootstat["gid"]} {rootstat["mode"]} capabilities=0x0\n'+''.join(f'{part}{p.rstrip("/")} {s["uid"]} {s["gid"]} {s["mode"]} capabilities=0x0\n' for p,s in metadata.items()))
    contexts.write_text(''.join(f'/{part}{re.escape(p.rstrip("/"))} {s["label"]}\n' for p,s in metadata.items() if s['label']))
    uuid=re.search(r'Filesystem UUID:\s+(\S+)',dbg(raw,'stats'))[1]
    newraw=d/'rebuilt.raw.img'
    if newraw.exists(): newraw.unlink()
    inode_count=re.search(r'Inode count:\s+(\d+)',dbg(raw,'stats'))[1]
    args=[TOOLS/'mkuserimg_mke2fs','--timestamp','1230768000','--journal_size','0',
          '--inode_size','256','--inodes',inode_count,'--fs_config',fsconfig,
          '--label',part,'--mke2fs_uuid',uuid,'--share_dup_blocks',
          tree,newraw,'ext4',part,str(raw.stat().st_size),contexts]
    print(run(args),flush=True)
    # Android's image builder hardcodes lost+found ownership to system.
    # Restore the original image's ownership for that directory explicitly.
    if '/lost+found' in metadata:
        for field in ['uid','gid']:
            run(['debugfs','-w','-R',f'sif /lost+found {field} {metadata["/lost+found"][field]}',newraw])
    check=inventory(newraw)
    if metadata!=check:
        differences={p:(s,check.get(p)) for p,s in metadata.items() if check.get(p)!=s}
        raise ValueError('Filesystem metadata changed: '+str(differences))
    verify=d/'verify-tree';verify.mkdir()
    dbg(newraw,f'rdump / {verify}')
    for p in modules:
        rel=p.relative_to(tree)
        assert (verify/rel).read_bytes()==(SIGNED/p.name).read_bytes(), rel
    for rel,digest in before.items():
        assert hashlib.sha256((verify/rel).read_bytes()).hexdigest()==digest, rel
    run(['e2fsck','-fn',newraw])
    # Preserve original AVB descriptor metadata and rebuild verity/FEC from new data.
    shutil.copyfile(raw,d/'original.raw.img')
    shutil.copyfile(newraw,raw)
    try:
        run([AVB,'avb','pack','-q','-o',d/(part+'.img')],cwd=d)
    finally:
        shutil.copyfile(d/'original.raw.img',raw)
    run([AVB,'avb','verify','-i',d/(part+'.img')])
    return {'modules':len(modules),'metadata_entries_verified':len(metadata),'unchanged_nonmodule_files':len(before),'size':(d/(part+'.img')).stat().st_size}

def rebuild_ramdisk():
    d=ROOT/'vendor_kernel_boot'
    tree=d/'cpio_tree'
    modules=list(tree.rglob('*.ko'))
    assert len(modules)>0
    meta=(d/'cpio.toml').read_bytes()
    for p in modules:
        replacement=SIGNED/p.name
        assert replacement.is_file(),p.name
        shutil.copyfile(replacement,p)
    run([AVB,'cpio','pack','-q','-o',d/'ramdisk.img.0'],cwd=d)
    assert meta==(d/'cpio.toml').read_bytes()
    run([AVB,'boot','pack','-q','-o',d/'vendor_kernel_boot.img'],cwd=d)
    # Unpack anew and compare every module byte-for-byte.
    verify=d/'verify';verify.mkdir()
    run([AVB,'cpio','unpack','-q','-i',d/'ramdisk.img.0'],cwd=verify)
    for p in modules:
        rel=p.relative_to(tree)
        assert (verify/'cpio_tree'/rel).read_bytes()==(SIGNED/p.name).read_bytes()
    return {'modules_replaced_and_verified':len(modules),'cpio_metadata_preserved':True,'boot_header_preserved':True}

def verify_modules(dist):
    """Every replacement must be signed by a certificate embedded in this Image."""
    raw = (dist/'Image').read_bytes()
    certs = []
    for match in re.finditer(b'\\x30\\x82', raw):
        offset = match.start()
        size = int.from_bytes(raw[offset+2:offset+4], 'big')+4
        if not 500 <= size <= 10000:
            continue
        candidate = ROOT/'candidate.der'
        candidate.write_bytes(raw[offset:offset+size])
        result = subprocess.run(['openssl','x509','-inform','DER','-in',str(candidate),
                                 '-outform','PEM'],capture_output=True)
        if result.returncode == 0:
            certs.append(result.stdout)
    if not certs:
        raise ValueError('No embedded X.509 certificates found in kernel Image')
    certfile = ROOT/'kernel-certs.pem'
    certfile.write_bytes(b''.join(certs))
    signature_file, content_file = ROOT/'module.sig', ROOT/'module.content'
    version_match = re.search(rb'Linux version ([^ \x00]+)', raw)
    if not version_match:
        raise ValueError('Kernel release string missing')
    expected_version = version_match[1].decode()
    count = 0
    for module in dist.glob('*.ko'):
        vermagic = run(['modinfo','-F','vermagic',module]).split()[0]
        if vermagic != expected_version:
            raise ValueError(f'Module kernel release mismatch: {module.name}')
        data = module.read_bytes()
        magic = b'~Module signature appended~\n'
        if not data.endswith(magic):
            raise ValueError(f'Unsigned module: {module.name}')
        end = len(data)-len(magic)
        header = data[end-12:end]
        # Linux sign-file PKCS#7 signature: no signer/key-id fields.
        if header[2] != 2 or header[3] or header[4]:
            raise ValueError(f'Unsupported module signature: {module.name}')
        size = int.from_bytes(header[8:12], 'big')
        start = end-12-size
        if start <= 0:
            raise ValueError('Invalid signature size')
        signature_file.write_bytes(data[start:end-12])
        content_file.write_bytes(data[:start])
        run(['openssl','cms','-verify','-binary','-inform','DER',
             '-in',signature_file,'-content',content_file,'-certfile',certfile,
             '-nointern','-noverify','-out',os.devnull])
        shutil.copyfile(module, SIGNED/module.name)
        count += 1
    if not count:
        raise ValueError('No signed loose modules found')
    signature_file.unlink()
    content_file.unlink()
    return count


def prepare_boot(dist):
    d = ROOT/'boot'
    run([AVB,'avb','unpack','-q','-i',ORIGINAL/'boot.img'], cwd=d)
    run([AVB,'boot','unpack','-q','-i',d/'raw.img'], cwd=d)
    # Retain the original boot header and replace only its kernel blob.
    shutil.copyfile(dist/'Image.lz4',d/'kernel.img')
    run([AVB,'boot','pack','-q','-o',d/'raw.img'],cwd=d)
    run([AVB,'avb','pack','-q','-o',d/'boot.img'],cwd=d)
    run([AVB,'avb','verify','-i',d/'boot.img'])


def main():
    global ROOT,AVB,TOOLS,SIGNED,ORIGINAL
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--dist',type=Path,required=True)
    parser.add_argument('--tools',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    ROOT=args.work.resolve(); ORIGINAL=args.original.resolve()
    TOOLS=args.tools.resolve(); AVB=Path(shutil.which('avbroot') or 'avbroot')
    dist=args.dist.resolve(); output=args.output.resolve()
    ROOT.mkdir(parents=True,exist_ok=False)
    SIGNED=ROOT/'signed-modules'; SIGNED.mkdir()
    for name in ['boot','system_dlkm','vendor_dlkm','vendor_kernel_boot']:
        (ROOT/name).mkdir()
    expanded = ROOT/'kernel.raw'
    with expanded.open('wb') as output_kernel:
        subprocess.run(['lz4','-d','-c',str(dist/'Image.lz4')],stdout=output_kernel,check=True)
    if expanded.read_bytes() != (dist/'Image').read_bytes():
        raise ValueError('Compressed boot kernel differs from the kernel used for module certificate verification')
    report={'module_signatures_verified':verify_modules(dist)}
    for name in ['system_dlkm','vendor_dlkm']:
        report[name]=rebuild_fs(name)
    d=ROOT/'vendor_kernel_boot'
    run([AVB,'avb','unpack','-q','-i',ORIGINAL/'vendor_kernel_boot.img'],cwd=d)
    run([AVB,'boot','unpack','-q','-i',d/'raw.img'],cwd=d)
    run([AVB,'cpio','unpack','-q','-i',d/'ramdisk.img.0'],cwd=d)
    report['vendor_kernel_boot']=rebuild_ramdisk()
    shutil.copyfile(d/'vendor_kernel_boot.img',d/'raw.img')
    run([AVB,'avb','pack','-q','-o',d/'vendor_kernel_boot.img'],cwd=d)
    run([AVB,'avb','verify','-i',d/'vendor_kernel_boot.img'])
    prepare_boot(dist)
    output.mkdir(parents=True,exist_ok=True)
    for name in ['boot','system_dlkm','vendor_dlkm','vendor_kernel_boot']:
        shutil.copyfile(ROOT/name/(name+'.img'),output/(name+'.img'))
    (output/'verification-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
