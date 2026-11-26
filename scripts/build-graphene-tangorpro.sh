#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
snapshot="$project_dir/kernel/tangorpro"
build_root="${RUNNER_TEMP:?Run this script on a GitHub-hosted runner}/graphene-kernel-build"
wrapper_commit=800b61f19d81645d0d55e3b932eeec64152ef0d5
kernel_commit=d888ecda03b1e9774d4eca52acefd363a8268ed9
test ! -e "$build_root" || { echo 'Build directory already exists; refusing to overwrite'; exit 1; }
mkdir -p "$project_dir/artifacts"
cd "$snapshot"
sha256sum -c SHA256SUMS
cp provenance.json "$project_dir/artifacts/source-provenance.json"
git clone --depth 1 --branch 2026111800 --no-recurse-submodules \
  https://gitlab.com/grapheneos/kernel_pixel_6.1.git "$build_root"
test "$(git -C "$build_root" rev-parse HEAD)" = "$wrapper_commit"
git -C "$build_root" submodule update --init --depth 1 common/ack
test "$(git -C "$build_root/common/ack" rev-parse HEAD)" = "$kernel_commit"
git -C "$build_root/common/ack" apply --check "$snapshot/tracked.patch"
git -C "$build_root/common/ack" apply "$snapshot/tracked.patch"
tar -xzf "$snapshot/source-overlay.tar.gz" -C "$build_root/common/ack"
cd "$build_root"
test -f common/ack/fs/susfs.c
test -f common/ack/include/linux/susfs.h
test -f common/ack/include/linux/susfs_def.h
test -f common/ack/drivers/kernelsu/Kbuild
grep -qx 'CONFIG_KSU=y' common/ack/arch/arm64/configs/gki_defconfig
grep -qx 'CONFIG_KSU_SUSFS=y' common/ack/arch/arm64/configs/gki_defconfig
export TMPDIR="${RUNNER_TEMP}"
export KLEAF_REPO_MANIFEST=aosp_manifest.xml
# Kernel and device modules must be built together. Keep the source build,
# module signature checks, CFI, RANDSTRUCT and ABI checks enabled.
./build_tangorpro.sh --jobs=2 --local_cpu_resources=2
test -d out/tangorpro/dist
# Distribution outputs must never include generated private module keys.
tar --exclude='*.pem' --exclude='*.key' --exclude='*.pk8' \
    --exclude='*.p12' --exclude='*.pfx' \
    -czf "$project_dir/artifacts/tangorpro-dist.tar.gz" -C out/tangorpro/dist .
sha256sum "$project_dir/artifacts/tangorpro-dist.tar.gz" > "$project_dir/artifacts/dist-sha256.txt"
echo 'Experimental kernel build complete. No Android OTA signing or flashing performed.'
