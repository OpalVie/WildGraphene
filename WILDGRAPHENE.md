# WildGraphene build infrastructure

This imports Wild Kernels orchestration into this repository. No separate fork is required.
Only main.yml, prepare.yml and build.yml are installed as executable workflows.
The upstream license is retained under third_party/wild-kernels; the existing root LICENSE is preserved.

The manual workflow defaults to android14-6.1 / 162 / KernelSU-Next / SUSFS,
4 KiB pages, preserved KMI suffix, no custom version branding and no module
version mismatch bypass. Extra NoMount, networking, Baseband Guard,
DroidSpaces, USB Arsenal and NTSync features default off.

This is an experimental compilation target based on the tablet's current stock
kernel. It is NOT confirmed compatible with GrapheneOS 2026111800. A successful
build does not establish device compatibility or preserve GrapheneOS hardening.
Do not flash it until the target OTA, vendor modules and boot image are checked.

GitHub Actions does not sign Android images. Keep AVB and OTA private keys local.
Custota, OTA modification, local signing, and device installation are not implemented.
The upstream manual workflow may publish a nightly kernel prerelease in this repo.
Do not add Telegram secrets; they are unnecessary for this project.
Upstream verified mode does not pin every dependency (notably KernelSU-Next).

Review with git diff --stat and git diff -- .github/workflows/main.yml, then commit
and push when ready. Run the workflow manually from the Actions tab after push.
The upstream checkout revision and imported file hashes are in provenance.json.
