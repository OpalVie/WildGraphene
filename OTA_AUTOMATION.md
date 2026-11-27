# WildGraphene Custota update pipeline

The `WildGraphene - signed Custota updates` workflow prepares complete OTA updates
for tangorpro. It runs daily at 10:17 UTC and can be run manually. The original
kernel-only workflow remains available.

## What runs

1. Compare the upstream stable release with `ota/tangorpro.json` and the reviewed
   kernel snapshot in `kernel/tangorpro/provenance.json`.
2. Build the pinned GrapheneOS kernel and matching KernelSU-Next/SUSFS modules.
   Require root support, module signature enforcement, CFI, RANDSTRUCT, MODVERSIONS,
   and 4 KiB pages in the resolved configuration.
3. Download the matching official OTA. Check its embedded AVB public-key hash
   against the pinned official GrapheneOS tangorpro key and verify its signatures.
4. Verify every replacement module's signature against a certificate embedded in
   the newly built kernel; verify its kernel release and compressed kernel match.
5. Rebuild the original OTA's module partitions and vendor kernel ramdisk with
   signed matching modules, retaining filesystem ownership, modes, SELinux labels,
   non-module files, boot headers, DTB, and original AVB image sizes. Built loose
   modules are used because the upstream build signs them after producing images.
6. In a separate job, sign the OTA with your existing release keys and verify
   the result against your OTA certificate and AVB public key.
7. Generate and verify Custota's `.csig`, then generate its update JSON.
8. Publish versioned ZIP/CSIG/checksum/provenance assets to GitHub Releases, then
   update `/tangorpro.json` on main and request a Pages build. The live feed only
   changes after signed assets are published.

The signer never uploads private keys, passphrases, or its working directory.
The kernel job receives no signing secrets. Environment keys are removed on exit;
GitHub destroys the hosted runner after the job. There are no device operations.

## First setup

Install and authenticate GitHub CLI locally:

```sh
sudo pacman -S --needed github-cli
gh auth login --hostname github.com
bash scripts/configure-ota-secrets.sh
```

The helper creates the `ota-signing` environment, restricts it to the main branch,
and uploads your existing encrypted key files, public trust material, and key
passphrases as environment secrets. It reads passphrases silently in your terminal.
It does not generate or change keys. GitHub Actions can decrypt and use your keys
once these secrets are configured: repository owners and anyone able to modify
trusted main-branch workflow code must be trusted with signing authority. Base64
is transport encoding; GitHub provides secret storage encryption. Keep an offline
backup of the keys and passphrases.

Required environment secrets:

- `WG_AVB_KEY_B64`: base64 of `avb.key`
- `WG_OTA_KEY_B64`: base64 of `ota.key`
- `WG_OTA_CERT_B64`: base64 of `ota.crt`
- `WG_AVB_PUBLIC_KEY_B64`: base64 of `avb_pkmd.bin`
- `WG_AVB_PASSPHRASE`
- `WG_OTA_PASSPHRASE`

Run the workflow once with **publish unchecked** to test the hosted packaging path.
It uploads prepared inputs and logs only. Until a tablet has successfully booted
this release, do not enable publication to the live Custota feed.

After successful device testing of release `2026111800`, set repository variables:

```sh
gh variable set WILDGRAPHENE_BOOT_TESTED_RELEASE --repo OpalVie/WildGraphene --body 2026111800
gh variable set WILDGRAPHENE_AUTO_PUBLISH --repo OpalVie/WildGraphene --body true
```

Then manually run the workflow with **publish checked** for the first live update.
Scheduled runs skip a release once it is already published. Manual runs can create
an additional version for the same OS release; CSIG v2 includes the vbmeta digest.

Pages must stay configured to deploy `main` at `/` (root). The Custota server URL is:

`https://opalvie.github.io/WildGraphene/`

The tablet still needs the Custota KernelSU module installed and its server URL
configured after first boot. Publishing does not install the module. Disable the
ordinary GrapheneOS updater's automatic installation so it cannot replace the
custom kernel with an upstream build; use Custota for this distribution's updates.

## New releases and dependency updates

A new GrapheneOS stable release stops the scheduled workflow with a message rather
than pairing a new OS with the old kernel. Review its exact wrapper and kernel
commits, rebase the patches, update the snapshot/overlay and `SHA256SUMS`, and
update `ota/tangorpro.json` to the same release. Test the prepared release before
updating `WILDGRAPHENE_BOOT_TESTED_RELEASE`. This review step is deliberate:
automatically compiling an arbitrary newer kernel does not prove it boots.

KernelSU, SUSFS, avbroot and custota-tool are pinned, not silently updated to branch
tips. Review dependency updates and their compatibility in the same repository.
Custota's tablet module can be updated separately through KernelSU. Your Android
apps retain their own ordinary update mechanisms.

If signature verification, building, packaging, signing, publication, or Pages
fails, inspect the workflow. GitHub's own Actions notifications report scheduled
failures; this workflow does not message anyone. If a release is created but feed
publication fails, use its existing `tangorpro.json` asset to repair the feed after
review. Unique release tags prevent asset overwrites.
