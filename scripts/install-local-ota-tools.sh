#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$HOME/pixel-tablet/tmp"
export RUNNER_TEMP="$(mktemp -d "$HOME/pixel-tablet/tmp/ota-tools.XXXXXXXX")"
trap 'rm -rf -- "$RUNNER_TEMP"' EXIT
# The pinned tools are compiled locally; this script does not open release keys.
bash "$project/scripts/install-ota-tools.sh"
mkdir -p "$HOME/.local/bin"
install -m755 "$RUNNER_TEMP/ota-tools/bin/avbroot" "$HOME/.local/bin/avbroot"
install -m755 "$RUNNER_TEMP/ota-tools/bin/custota-tool" "$HOME/.local/bin/custota-tool"
