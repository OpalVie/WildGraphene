#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
release="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release"])' "$project/ota/tangorpro.json")"
root="${RUNNER_TEMP:?}/ota-preparation"
mkdir -p "$root/original" "$project/prepared"
export TMPDIR="$RUNNER_TEMP"
input="$project/prepared/upstream.zip"
curl --fail --location --retry 3 --output "$input" "https://releases.grapheneos.org/tangorpro-ota_update-$release.zip"
bash "$project/scripts/verify-upstream.sh" "$input"
avbroot ota extract --input "$input" --directory "$root/original" \
  --partition boot --partition system_dlkm --partition vendor_dlkm --partition vendor_kernel_boot
python3 "$project/scripts/prepare-ota-images.py" \
  --original "$root/original" --work "$root/repack" \
  --dist "$RUNNER_TEMP/graphene-kernel-build/out/tangorpro/dist" \
  --tools "$RUNNER_TEMP/graphene-kernel-build/prebuilts/kernel-build-tools/linux-x86/bin" \
  --output "$project/prepared"
cp "$project/artifacts/source-provenance.json" "$project/prepared/"
cp "$project/ota/tangorpro.json" "$project/prepared/ota-config.json"
cp "$project/upstream-state/candidate.json" "$project/prepared/candidate.json"
mkdir -p "$project/prepared/snapshot"
cp "$project/kernel/tangorpro/"* "$project/prepared/snapshot/"
cd "$project/prepared"
sha256sum upstream.zip boot.img system_dlkm.img vendor_dlkm.img vendor_kernel_boot.img \
  verification-report.json source-provenance.json ota-config.json candidate.json snapshot/* > SHA256SUMS
