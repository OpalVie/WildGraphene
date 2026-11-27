#!/usr/bin/env bash
# User runs locally. Private values are piped to gh, never printed or committed.
set -euo pipefail
repository=OpalVie/WildGraphene
keys="$HOME/pixel-tablet/keys/tangorpro"
command -v gh >/dev/null || { echo 'Install GitHub CLI first: sudo pacman -S github-cli'; exit 1; }
gh auth status
# Restrict the signing environment to main so other branches cannot request keys.
gh api --method PUT "repos/$repository/environments/ota-signing" --input - <<'JSON'
{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}
JSON
policies="$(gh api "repos/$repository/environments/ota-signing/deployment-branch-policies")"
if ! printf '%s' "$policies" | python3 -c 'import json,sys; sys.exit(0 if any(x["name"]=="main" for x in json.load(sys.stdin)["branch_policies"]) else 1)'; then
  gh api --method POST "repos/$repository/environments/ota-signing/deployment-branch-policies" -f name=main -f type=branch >/dev/null
fi
for file in avb.key ota.key ota.crt avb_pkmd.bin; do
  test -f "$keys/$file" || { echo "Missing $keys/$file" >&2; exit 1; }
done
# Use an environment instead of repository-wide secrets. No prompts for values in chat.
for mapping in WG_AVB_KEY_B64:avb.key WG_OTA_KEY_B64:ota.key WG_OTA_CERT_B64:ota.crt WG_AVB_PUBLIC_KEY_B64:avb_pkmd.bin; do
  base64 -w0 "$keys/${mapping#*:}" | gh secret set "${mapping%%:*}" --repo "$repository" --env ota-signing
done
read -rsp 'AVB key passphrase (terminal only): ' avb_pass; printf '\n'
printf '%s' "$avb_pass" | gh secret set WG_AVB_PASSPHRASE --repo "$repository" --env ota-signing
unset avb_pass
read -rsp 'OTA key passphrase (terminal only): ' ota_pass; printf '\n'
printf '%s' "$ota_pass" | gh secret set WG_OTA_PASSPHRASE --repo "$repository" --env ota-signing
unset ota_pass
echo 'Signing secrets configured. Automatic publishing is still disabled until the boot-tested release and auto-publish variables are set.'
