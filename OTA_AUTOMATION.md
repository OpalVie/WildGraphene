# WildGraphene: upstream builds, local signing, Custota updates

## Automatic work in Actions

`WildGraphene - upstream builds and OTA preparation` runs daily at 10:17 UTC.
It also has a manual **force_build** option, enabled by default.

It tracks:

- The official GrapheneOS tangorpro stable release and its exact kernel wrapper tag.
- `pershoot/KernelSU-Next`, branch `dev-susfs` (the SUSFS-integrated fork used here).
- `simonpunk/susfs4ksu`, branch `gki-android14-6.1`, with the two existing
  pershoot compatibility fixes when they are not already present.

A new OS release OR KernelSU-Next commit OR SUSFS commit triggers a candidate
build. A scheduled run reuses the upstream state of the last successful run so
unchanged versions are not compiled every day. Failed combinations are retried;
their candidate snapshots and logs are preserved. Expired/missing state may cause
a harmless rebuild. A manual force build always rebuilds the current combination.

Discovery resolves branch names to full commit hashes before building. The source
snapshot is generated from these exact commits, including the existing KernelSU
wiring and pinned manager version. Only the two previously reviewed include-context
adjustments are made to the SUSFS patch; any other patch conflict stops the run.
A future upstream Kbuild layout that no longer supports our version pin also stops
rather than guessing. Compatibility fixes may need maintenance when upstream changes.

The workflow checks the resolved configuration for root/SUSFS support, enforced
module signatures, CFI, RANDSTRUCT, MODVERSIONS, and 4 KiB pages. It builds the
kernel and all device modules together, verifies every replacement module's
signature against a certificate embedded in that kernel, checks module release
strings, verifies the official OTA against GrapheneOS's AVB trust anchor, and
repackages its original partition layouts with the new kernel and signed modules.

Success means compilation and packaging passed. It does not prove a new
combination boots or that an OTA installation succeeds on hardware.

Artifacts include:

- `upstream-state`: immutable upstream commit selections and fingerprint.
- `prepared-tangorpro-<release>`: official OTA, four replacement images,
  checksums, generated source snapshot, provenance and verification report.
- `kernel-logs-<release>` and `candidate-snapshot-<release>` for diagnosis.

**Actions has no signing job or signing secrets. It never installs anything.**
The old fixed-version kernel-only workflow remains available for reproducing the
original build. The `publish` input and cloud-signing scripts from the first
pipeline have been removed to keep the private keys exclusively on your computer.

## One-time local tool setup

Install the prerequisites on Arch if needed:

```sh
sudo pacman -S --needed github-cli rustup base-devel openssl pkgconf cmake clang protobuf
```

Then, from the WildGraphene repository:

```sh
bash scripts/install-local-ota-tools.sh
```

This compiles avbroot and custota-tool at the exact commits in
`ota/tangorpro.json`, with locked Rust dependencies, into `~/.local/bin`.
It does not open your release keys or change your default Rust toolchain.
GitHub authentication uses `gh auth login --hostname github.com`.

## Sign a successful build locally

Use the run ID of the NEW upstream-tracking workflow after it finishes successfully:

```sh
bash scripts/sign-local-update.sh ACTIONS_RUN_ID
```

The script refuses incomplete, failed, non-main, or unrelated workflow runs.
It downloads that run's prepared artifacts, checks checksums and source records,
reverifies upstream trust, patches and signs the OTA using the existing
`~/pixel-tablet/keys/tangorpro/{avb.key,ota.key,ota.crt,avb_pkmd.bin}`, and verifies
it against your own public trust files. Key passphrases are entered interactively
in the terminal. They are never sent to GitHub. Custota's CSIG v2 is generated and
verified with the same OTA certificate.

The result is written to `~/pixel-tablet/output/actions-<run-id>/` and uploaded to
GitHub Releases as a **draft**. Only public signed artifacts are uploaded. The
live Custota feed is unchanged, so an untested candidate is not sent to devices.
The script refuses to overwrite existing local output directories.

## Publish a tested signed build

After hardware testing, run the command printed by the signing script:

```sh
bash scripts/publish-local-update.sh "$HOME/pixel-tablet/output/actions-ACTIONS_RUN_ID"
```

This verifies local checksums, OTA and CSIG signatures, and the feed URL, downloads
the draft assets to confirm byte equality, promotes the release, then commits
`tangorpro.json` to main using your authenticated local GitHub CLI. Normal Pages
branch deployment updates the feed. If publishing fails after release promotion,
rerun this command; the feed will still point to its previous update until the
commit succeeds. Old immutable release assets are not overwritten.

GitHub Pages must deploy `main`, `/` (root). The tablet's Custota server URL is:

`https://opalvie.github.io/WildGraphene/`

The first device installation, KernelSU manager, and Custota module installation
still need to be completed. Disable ordinary GrapheneOS updater automatic
installation for this custom distribution and use Custota for its signed updates.
Custota does not create updates or compile kernels: it installs our published
signed updates. The KernelSU manager/Custota app modules have their own app/module
update paths; this pipeline updates the KernelSU-Next and SUSFS kernel components.

## What remains manual

- Local signing, because the release private keys stay exclusively on your computer.
- Hardware testing and explicitly publishing to the live feed.
- Resolving future patch/API incompatibilities if automated checks fail.

No new private keys are needed. Maintain your existing key backups.
