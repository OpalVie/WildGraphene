#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
snapshot="$project_dir/kernel/tangorpro"
build_root="${RUNNER_TEMP:?Run this script on a GitHub-hosted runner}/graphene-kernel-build"
readarray -t pins < <(python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(p["grapheneos_release"]); print(p["wrapper_commit"]); print(p["kernel_commit"])' "$snapshot/provenance.json")
release="${pins[0]}"
wrapper_commit="${pins[1]}"
kernel_commit="${pins[2]}"
if [[ -e "$build_root" && "${WILDGRAPHENE_CANDIDATE_SOURCE:-}" != 1 ]]; then
  echo 'Build directory already exists; refusing to overwrite' >&2; exit 1
fi
mkdir -p "$project_dir/artifacts"
cd "$snapshot"
sha256sum -c SHA256SUMS
cp provenance.json "$project_dir/artifacts/source-provenance.json"
if [[ ! -d "$build_root" ]]; then
  git clone --depth 1 --branch "$release" --no-recurse-submodules \
    https://gitlab.com/grapheneos/kernel_pixel_6.1.git "$build_root"
fi
test "$(git -C "$build_root" rev-parse HEAD)" = "$wrapper_commit"
git -C "$build_root" submodule update --init --depth 1 common/ack
test "$(git -C "$build_root/common/ack" rev-parse HEAD)" = "$kernel_commit"
test -z "$(git -C "$build_root/common/ack" status --porcelain --untracked-files=all)"
git -C "$build_root/common/ack" apply --check "$snapshot/tracked.patch"
git -C "$build_root/common/ack" apply "$snapshot/tracked.patch"
tar -xzf "$snapshot/source-overlay.tar.gz" -C "$build_root/common/ack"
cd "$build_root"
test -f common/ack/fs/susfs.c
test -f common/ack/include/linux/susfs.h
test -f common/ack/include/linux/susfs_def.h
test -f common/ack/drivers/kernelsu/Kbuild
export TMPDIR="${RUNNER_TEMP}"
export KLEAF_REPO_MANIFEST=aosp_manifest.xml
# Kernel and device modules must be built together. Keep the source build,
# module signature checks, CFI, RANDSTRUCT and ABI checks enabled.
# Both options default to y in the integrated Kconfig. Explicitly adding
# them to gki_defconfig is redundant and fails the savedefconfig check.
# Verify the resolved configuration before spending time compiling.
tools/bazel build --config=stamp --config=tangorpro \
  --jobs=2 --local_cpu_resources=2 //common/ack:kernel_aarch64_config
config_dir="$(tools/bazel cquery --config=stamp --config=tangorpro \
  --output=files //common/ack:kernel_aarch64_config)"
test -f "$config_dir/.config"
cp "$config_dir/.config" "$project_dir/artifacts/gki-resolved.config"
grep -qx 'CONFIG_KSU=y' "$project_dir/artifacts/gki-resolved.config"
grep -qx 'CONFIG_KSU_SUSFS=y' "$project_dir/artifacts/gki-resolved.config"
for option in ARM64_4K_PAGES CFI_CLANG MODVERSIONS MODULE_SIG_FORCE RANDSTRUCT_FULL; do
  grep -qx "CONFIG_${option}=y" "$project_dir/artifacts/gki-resolved.config"
done
./build_tangorpro.sh --jobs=2 --local_cpu_resources=2
test -d out/tangorpro/dist
# Distribution outputs must never include generated private module keys.
tar --exclude='*.pem' --exclude='*.key' --exclude='*.pk8' \
    --exclude='*.p12' --exclude='*.pfx' \
    -czf "$project_dir/artifacts/tangorpro-dist.tar.gz" -C out/tangorpro/dist .
sha256sum "$project_dir/artifacts/tangorpro-dist.tar.gz" > "$project_dir/artifacts/dist-sha256.txt"
echo 'Experimental kernel build complete. No Android OTA signing or flashing performed.'
