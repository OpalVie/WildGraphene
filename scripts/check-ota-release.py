#!/usr/bin/env python3
"""Validate the reviewed snapshot before a scheduled build may use it."""
import json, os, re, urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config = json.loads((root / 'ota/tangorpro.json').read_text())
provenance = json.loads((root / 'kernel/tangorpro/provenance.json').read_text())
release = config['release']
if not re.fullmatch(r'\d{10}', release):
    raise SystemExit('Invalid reviewed release')
if release != provenance['grapheneos_release']:
    raise SystemExit('OTA release and kernel snapshot release differ')
with urllib.request.urlopen('https://releases.grapheneos.org/tangorpro-stable', timeout=60) as response:
    latest = response.read(4096).decode().split()[0]
if not re.fullmatch(r'\d{10}', latest):
    raise SystemExit('Invalid upstream stable response')
if os.environ.get('GITHUB_EVENT_NAME') == 'schedule' and latest != release:
    raise SystemExit(f'GrapheneOS {latest} needs a reviewed matching kernel snapshot; pinned at {release}. No OTA published.')
if os.environ.get('GITHUB_OUTPUT'):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
        out.write(f'release={release}\nlatest={latest}\n')
print(f'Reviewed release: {release}; upstream stable: {latest}')
