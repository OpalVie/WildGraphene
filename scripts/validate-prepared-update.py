#!/usr/bin/env python3
"""Check that downloaded source records refer to one upstream combination."""
import json
from pathlib import Path
import re
import sys


def validate(directory):
    directory=Path(directory)
    state=json.loads((directory/'candidate.json').read_text())
    provenance=json.loads((directory/'source-provenance.json').read_text())
    config=json.loads((directory/'ota-config.json').read_text())
    if not re.fullmatch(r'\d{10}',state['release']):
        raise ValueError('Invalid release')
    if state['release'] != provenance['grapheneos_release'] or state['release'] != config['release']:
        raise ValueError('Mismatched OS release')
    for key in ['wrapper_commit','kernelsu_next_commit','susfs_base_commit']:
        if not re.fullmatch('[0-9a-f]{40}',state[key]) or provenance[key] != state[key]:
            raise ValueError('Mismatched source commit: '+key)
    if provenance.get('upstream_fingerprint') != state['fingerprint']:
        raise ValueError('Mismatched upstream fingerprint')
    print('Prepared update source records agree')


if __name__=='__main__':
    validate(sys.argv[1])
