#!/usr/bin/env python3
"""Resolve upstreams to immutable commits. Does not download or sign an OTA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'wrapper': 'https://gitlab.com/grapheneos/kernel_pixel_6.1.git',
    'kernelsu': 'https://github.com/pershoot/KernelSU-Next.git',
    'susfs': 'https://gitlab.com/simonpunk/susfs4ksu.git',
}


def remote_commit(url, ref):
    text = subprocess.check_output(['git', 'ls-remote', url, ref, ref+'^{}'], text=True)
    refs = dict(line.split()[::-1] for line in text.splitlines())
    sha = refs.get(ref+'^{}', refs.get(ref))
    if not sha or not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError(f'Cannot resolve {url} {ref}')
    return sha


def fingerprint(state):
    fields = ['release', 'wrapper_commit', 'kernelsu_next_commit', 'susfs_base_commit']
    return hashlib.sha256(json.dumps({k: state[k] for k in fields}, sort_keys=True).encode()).hexdigest()


def baseline():
    p = json.loads((ROOT/'kernel/tangorpro/provenance.json').read_text())
    return {**p, 'release': p['grapheneos_release']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    with urllib.request.urlopen('https://releases.grapheneos.org/tangorpro-stable', timeout=60) as r:
        tokens = r.read(4096).decode().split()
    if len(tokens) != 4 or tokens[2:] != ['tangorpro', 'stable'] or not re.fullmatch(r'\d{10}', tokens[0]):
        raise ValueError('Unexpected GrapheneOS stable response')
    state = {
        'release': tokens[0],
        'wrapper_commit': remote_commit(SOURCES['wrapper'], 'refs/tags/'+tokens[0]),
        'kernelsu_next_commit': remote_commit(SOURCES['kernelsu'], 'refs/heads/dev-susfs'),
        'susfs_base_commit': remote_commit(SOURCES['susfs'], 'refs/heads/gki-android14-6.1'),
    }
    state['fingerprint'] = fingerprint(state)
    previous = json.loads(args.previous.read_text()) if args.previous else baseline()
    changed = fingerprint(state) != fingerprint(previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(state, indent=2)+'\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f'release={state["release"]}\nbuild={str(changed or args.force).lower()}\n')
    print(json.dumps({'candidate': state, 'changed': changed, 'forced': args.force}, indent=2))


if __name__ == '__main__':
    main()
