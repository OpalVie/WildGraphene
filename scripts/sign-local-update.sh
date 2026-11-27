#!/usr/bin/env bash
# Downloads successful Actions results, signs locally, and uploads a DRAFT release.
set -euo pipefail
umask 077
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repository=OpalVie/WildGraphene
run_id="${1:?Usage: bash scripts/sign-local-update.sh ACTIONS_RUN_ID}"
[[ "$run_id" =~ ^[0-9]+$ ]] || { echo 'Invalid Actions run ID' >&2; exit 1; }
keys="$HOME/pixel-tablet/keys/tangorpro"
work="$HOME/pixel-tablet/tmp/local-update-$run_id"
out="$HOME/pixel-tablet/output/actions-$run_id"
for file in avb.key ota.key ota.crt avb_pkmd.bin; do test -f "$keys/$file"; done
for dir in "$work" "$out"; do
  [[ ! -e "$dir" ]] || { echo "Already exists: $dir. Refusing to overwrite." >&2; exit 1; }
done
export PATH="$HOME/.local/bin:$PATH"
command -v avbroot >/dev/null
command -v custota-tool >/dev/null || { echo 'custota-tool is missing. Run: bash scripts/install-local-ota-tools.sh' >&2; exit 1; }
mkdir -p "$work/state" "$work/prepared" "$out"
export TMPDIR="$HOME/pixel-tablet/tmp"
gh run view "$run_id" --repo "$repository" --json status,conclusion,headSha,headBranch,workflowName > "$work/run.json"
python3 - "$work/run.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if r['status']!='completed' or r['conclusion']!='success' or r['headBranch']!='main':
    raise SystemExit('Only a successful completed main-branch run can be signed')
if r['workflowName'] != 'WildGraphene - upstream builds and OTA preparation':
    raise SystemExit('Unexpected workflow; refusing to sign')
PY
gh run download "$run_id" --repo "$repository" --name upstream-state --dir "$work/state"
release="$(python3 - "$work/state/candidate.json" <<'PY'
import json,re,sys
r=json.load(open(sys.argv[1]))['release']
if not re.fullmatch(r'\d{10}',r): raise SystemExit('Invalid release')
print(r)
PY
)"
gh run download "$run_id" --repo "$repository" --name "prepared-tangorpro-$release" --dir "$work/prepared"
cd "$work/prepared"
sha256sum --check SHA256SUMS
cmp candidate.json "$work/state/candidate.json"
python3 "$project/scripts/validate-prepared-update.py" "$PWD"
# Verify upstream against the same fixed official trust anchor used in CI.
bash "$project/scripts/verify-upstream.sh" "$PWD/upstream.zip"
ota="$out/tangorpro-WildGraphene-$release-r$run_id.zip"
echo 'Enter your existing signing-key passphrases in this terminal only.'
avbroot ota patch --input upstream.zip --output "$ota" \
  --key-avb "$keys/avb.key" --key-ota "$keys/ota.key" --cert-ota "$keys/ota.crt" \
  --prepatched boot.img --replace system_dlkm system_dlkm.img \
  --replace vendor_dlkm vendor_dlkm.img --replace vendor_kernel_boot vendor_kernel_boot.img
avbroot ota verify --input "$ota" --cert-ota "$keys/ota.crt" --public-key-avb "$keys/avb_pkmd.bin"
custota-tool gen-csig --input "$ota" --key "$keys/ota.key" --cert "$keys/ota.crt"
custota-tool show-csig --input "$ota.csig" --cert "$keys/ota.crt" > "$out/custota-signature-info.txt"
tag="tangorpro-$release-r$run_id"
custota-tool gen-update-info --file "$out/tangorpro.json" \
  --location "https://github.com/$repository/releases/download/$tag/$(basename "$ota")"
cp candidate.json source-provenance.json verification-report.json "$out/"
cp "$work/run.json" "$out/"
printf '%s\n' "$tag" > "$out/release-tag.txt"
cd "$out"
sha256sum "$(basename "$ota")" "$(basename "$ota").csig" tangorpro.json \
  candidate.json source-provenance.json verification-report.json run.json release-tag.txt > SHA256SUMS
head_sha="$(python3 -c 'import json; print(json.load(open("run.json"))["headSha"])')"
gh release create "$tag" --repo "$repository" --target "$head_sha" --draft \
  --title "WildGraphene tangorpro $release (build $run_id)" \
  --notes 'Locally signed and verified OTA. Source commits and module verification report are included. Draft until selected for the Custota feed.' \
  ./*.zip ./*.csig ./*.json SHA256SUMS custota-signature-info.txt release-tag.txt
printf '\nSigned update saved to %s\n' "$out"
printf 'Uploaded as a DRAFT; the live update feed is unchanged.\n'
printf 'After testing this build, publish it with:\nbash %q %q\n' "$project/scripts/publish-local-update.sh" "$out"
