#!/usr/bin/env bash
# Explicitly promotes a locally signed draft and switches the live Custota feed.
set -euo pipefail
repository=OpalVie/WildGraphene
out="${1:?Usage: bash scripts/publish-local-update.sh SIGNED_OUTPUT_DIRECTORY}"
cd "$out"
sha256sum --check SHA256SUMS
tag="$(cat release-tag.txt)"
[[ "$tag" =~ ^tangorpro-[0-9]{10}-r[0-9]+$ ]] || { echo 'Invalid release tag' >&2; exit 1; }
# Require the feed to point to this repository and immutable release.
python3 - "$repository" "$tag" <<'PY_CHECK'
import json,sys
from pathlib import Path
feed=json.loads(Path('tangorpro.json').read_text())['full']
otas=list(Path('.').glob('*.zip'))
if len(otas)!=1: raise SystemExit('Expected exactly one OTA')
url=f'https://github.com/{sys.argv[1]}/releases/download/{sys.argv[2]}/{otas[0].name}'
if feed['location_ota']!=url or feed['location_csig']!=url+'.csig':
    raise SystemExit('Feed points to a different update')
PY_CHECK
# Recheck both the OTA and CSIG signatures against our own local public trust files.
export PATH="$HOME/.local/bin:$PATH"
export TMPDIR="$HOME/pixel-tablet/tmp"
keys="$HOME/pixel-tablet/keys/tangorpro"
mapfile -t otas < <(find . -maxdepth 1 -type f -name '*.zip')
[[ "${#otas[@]}" == 1 ]]
avbroot ota verify --input "${otas[0]}" --cert-ota "$keys/ota.crt" --public-key-avb "$keys/avb_pkmd.bin"
custota-tool show-csig --input "${otas[0]}.csig" --cert "$keys/ota.crt" >/dev/null
# Check uploaded assets byte-for-byte before making them available to devices.
verify="$(mktemp -d "$TMPDIR/release-verify.XXXXXXXX")"
trap 'rm -rf -- "$verify"' EXIT
gh release download "$tag" --repo "$repository" --dir "$verify"
while read -r digest name; do
  name="${name#\*}"
  case "$name" in */*|..|'') echo 'Unexpected checksum filename' >&2; exit 1;; esac
  [[ "$(sha256sum "$verify/$name" | cut -d' ' -f1)" == "$digest" ]]
done < SHA256SUMS
gh release edit "$tag" --repo "$repository" --draft=false --prerelease=false
# A personal gh login triggers normal branch-based Pages deployment on this commit.
python3 - "$repository" <<'PY'
import base64,json,subprocess,sys
from pathlib import Path
endpoint=f'repos/{sys.argv[1]}/contents/tangorpro.json'
r=subprocess.run(['gh','api',endpoint+'?ref=main'],capture_output=True,text=True)
payload={'branch':'main','message':'Publish locally signed tangorpro Custota update',
         'content':base64.b64encode(Path('tangorpro.json').read_bytes()).decode()}
if r.returncode==0:
    payload['sha']=json.loads(r.stdout)['sha']
elif '404' not in r.stderr:
    raise SystemExit(r.stderr)
subprocess.run(['gh','api','--method','PUT',endpoint,'--input','-'],input=json.dumps(payload),text=True,check=True)
PY
echo 'Release published and Custota feed committed. Check GitHub Pages deployment before testing the updater.'
