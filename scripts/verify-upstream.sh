#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
input="${1:?OTA path required}"
trust="$(mktemp -d)"
trap 'rm -rf -- "$trust"' EXIT
expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstream_avb_sha256"])' "$project/ota/tangorpro.json")"
avbroot ota extract --input "$input" --none --public-key-avb "$trust/avb.bin" --cert-ota "$trust/ota.crt"
test "$(sha256sum "$trust/avb.bin" | cut -d' ' -f1)" = "$expected" || { echo 'Unexpected GrapheneOS AVB signing key' >&2; exit 1; }
avbroot ota verify --input "$input" --public-key-avb "$trust/avb.bin" --cert-ota "$trust/ota.crt"
