#!/usr/bin/env bash
set -euo pipefail
project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
root="${RUNNER_TEMP:?}/ota-tools"
mkdir -p "$root/bin"
# Use the runner's current stable compiler; dependency versions remain Cargo.lock-pinned.
rustup toolchain install stable --profile minimal --no-self-update
for tool in avbroot custota; do
  commit="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]+"_commit"])' "$project/ota/tangorpro.json" "$tool")"
  case "$tool" in
    avbroot) repo=avbroot; package=avbroot ;;
    custota) repo=Custota; package=custota-tool ;;
  esac
  git init -q "$root/$tool"
  git -C "$root/$tool" remote add origin "https://github.com/chenxiaolong/$repo.git"
  git -C "$root/$tool" fetch --depth 1 origin "$commit"
  git -C "$root/$tool" checkout --detach FETCH_HEAD
  test "$(git -C "$root/$tool" rev-parse HEAD)" = "$commit"
  cargo +stable build --locked --release --manifest-path "$root/$tool/Cargo.toml" -p "$package" --target-dir "$root/target"
  install -m755 "$root/target/release/$package" "$root/bin/$package"
done
rm -rf -- "$root/target"
if [[ -n "${GITHUB_PATH:-}" ]]; then echo "$root/bin" >> "$GITHUB_PATH"; fi
