#!/usr/bin/env bash
# Run in a separate job: the kernel build never receives the release keys.
set -euo pipefail
umask 077
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
release="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release"])' "$project/ota/tangorpro.json")"
: "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}" "${GITHUB_RUN_ID:?}"
for name in WG_AVB_KEY_B64 WG_OTA_KEY_B64 WG_OTA_CERT_B64 WG_AVB_PUBLIC_KEY_B64 WG_AVB_PASSPHRASE WG_OTA_PASSPHRASE; do
  [[ -n "${!name:-}" ]] || { echo "Missing secret: $name" >&2; exit 1; }
done
keys="$(mktemp -d "$RUNNER_TEMP/release-keys.XXXXXXXX")"
trap 'rm -rf -- "$keys"' EXIT
printf '%s' "$WG_AVB_KEY_B64" | base64 --decode > "$keys/avb.key"
printf '%s' "$WG_OTA_KEY_B64" | base64 --decode > "$keys/ota.key"
printf '%s' "$WG_OTA_CERT_B64" | base64 --decode > "$keys/ota.crt"
printf '%s' "$WG_AVB_PUBLIC_KEY_B64" | base64 --decode > "$keys/avb_pkmd.bin"
unset WG_AVB_KEY_B64 WG_OTA_KEY_B64 WG_OTA_CERT_B64 WG_AVB_PUBLIC_KEY_B64
export TMPDIR="$RUNNER_TEMP"
cd "$project/prepared"
sha256sum --check SHA256SUMS
bash "$project/scripts/verify-upstream.sh" "$PWD/upstream.zip"
mkdir -p "$project/release"
ota="$project/release/tangorpro-WildGraphene-$release.zip"
avbroot ota patch --input upstream.zip --output "$ota" \
  --key-avb "$keys/avb.key" --key-ota "$keys/ota.key" --cert-ota "$keys/ota.crt" \
  --pass-avb-env-var WG_AVB_PASSPHRASE --pass-ota-env-var WG_OTA_PASSPHRASE \
  --prepatched boot.img --replace system_dlkm system_dlkm.img \
  --replace vendor_dlkm vendor_dlkm.img --replace vendor_kernel_boot vendor_kernel_boot.img
avbroot ota verify --input "$ota" --cert-ota "$keys/ota.crt" --public-key-avb "$keys/avb_pkmd.bin"
custota-tool gen-csig --input "$ota" --key "$keys/ota.key" --cert "$keys/ota.crt" \
  --passphrase-env-var WG_OTA_PASSPHRASE
# show-csig is also a parse check; generation verifies the OTA against our certificate.
custota-tool show-csig --input "$ota.csig" --cert "$keys/ota.crt" > "$project/release/custota-signature-info.txt"
tag="tangorpro-$release-${GITHUB_SHA:0:12}-r$GITHUB_RUN_ID"
url="https://github.com/$GITHUB_REPOSITORY/releases/download/$tag/$(basename "$ota")"
custota-tool gen-update-info --file "$project/release/tangorpro.json" --location "$url"
cp verification-report.json source-provenance.json "$project/release/"
cd "$project/release"
sha256sum "$(basename "$ota")" "$(basename "$ota").csig" > SHA256SUMS
printf '%s\n' "$tag" > release-tag.txt
