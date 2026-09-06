# Publishing to the NVDA Add-on Store

This is the end-to-end process to release a version and get it into the
official NVDA Add-on Store. It reflects the current NV Access
[addon-datastore](https://github.com/nvaccess/addon-datastore) submission
process (issue-form based, with an auto-generated pull request).

## How the store works, in short

1. You host the built `.nvda-addon` file at a stable public URL (a GitHub
   release asset is recommended).
2. You open an "Add-on registration" issue form on the addon-datastore repo.
   It generates a pull request adding a small JSON metadata file for your
   version.
3. For a brand-new add-on you must first be approved as a publisher for that
   add-on (up to two weeks). Later updates do not need re-approval.
4. The submitted file is scanned by VirusTotal and validated automatically. If
   validation passes (and the publisher is approved), the PR is merged
   automatically and the version appears in the store.

## Before your first submission

- Decide the add-on **name** (manifest `name`, e.g. `piperNeural`). It must be
  unique in the store and contain only letters, numbers, underscores, and
  hyphens. This is the `addonId`.
- Host the code in a public repository (the `sourceURL` / homepage). Add-ons
  are expected to be open source; this one is GPL v2.
- Make sure the add-on's own GUI is accessible and the docs (`readme.html`)
  are present, since reviewers and users rely on them.
- Read and follow the
  [NVDA code of conduct](https://github.com/nvaccess/nvda/blob/master/CODE_OF_CONDUCT.md).

## Step 1: prepare the release

Follow [TESTING.md](TESTING.md) and complete its pre-release checklist. Then:

1. Bump `version` in `addon/manifest.ini` to `major.minor.patch`.
2. Set `minimumNVDAVersion` and `lastTestedNVDAVersion` to valid NVDA API
   versions (year.major.minor). Valid values are listed in
   [nvdaAPIVersions.json](https://github.com/nvaccess/addon-datastore-transform/blob/main/nvdaAPIVersions.json).
   See "Choosing your NVDA versions and channel" below - this is the single
   most important decision for this add-on.
3. Add a CHANGELOG entry for the version.
4. Confirm `summary` and `url` in the manifest are correct: the store
   `displayName` must match the manifest `summary`, and the store `homepage`
   must match the manifest `url`.

## Choosing your NVDA versions and channel

NVDA 2026.1 is the first 64-bit NVDA and is a compatibility-breaking release:
its `backCompatTo` is 2026.1.0, so an add-on is only offered to a 2026.1+ user
when its `lastTestedNVDAVersion` is at least 2026.1.0. At the time of writing,
2026.1 and 2026.2 are still marked `experimental` in nvdaAPIVersions.json.

The store enforces this rule: **if `lastTestedNVDAVersion` refers to an
experimental (beta/alpha) NVDA, the submission must use the `beta` or `dev`
channel, not `stable`.** That creates a genuine either/or right now:

- **Stable channel, 2025.x users:** set `lastTestedNVDAVersion = 2025.3.3`
  (the newest non-experimental version). Works on NVDA 2025.1 through 2025.3.x.
  It will not be offered to 2026.1 users.
- **Beta or dev channel, 2026.1+ users:** set
  `lastTestedNVDAVersion = 2026.1.0` (or 2026.2.0) and submit on `beta`.
  Required to reach 64-bit NVDA users while those versions are experimental.

Because this add-on's architecture (an always-x64 helper) is designed for the
64-bit era, the natural path is a `beta`-channel release with
`lastTestedNVDAVersion = 2026.1.0` now, then moving it to `stable` once 2026.1
loses its experimental flag (re-check nvdaAPIVersions.json at submission time).
`minimumNVDAVersion = 2025.1.0` keeps 2025.x users covered on the stable
release. Keep the manifest and the store metadata in agreement.

## Step 2: build

```
python tools/build.py
```

The submission form computes the SHA256 for you, so you do not normally paste
it by hand. To verify the file yourself:

```
certutil -hashfile dist\piper-neural-0.4.1.nvda-addon SHA256
```

## Step 3: publish the file

Create a GitHub release (tag it, e.g. `v0.4.1`) and attach the
`.nvda-addon` as a release asset. Copy its direct download URL. It must:

- start with `https://`,
- end with `.nvda-addon`,
- download the file directly, and
- remain valid indefinitely.

## Step 4: submit to the store

Open the
[Add-on registration issue form](https://github.com/nvaccess/addon-datastore/issues/new?template=registerAddon.yml)
and fill it in. The form itself asks for only a few things: the **download
URL**, the **source URL**, the **publisher**, the **channel** (stable / beta /
dev), and the **license name** and **license URL** (defaulting to "GPL v2" and
the GNU GPL-2.0 URL). From those plus your packaged add-on it generates a JSON
metadata file (a PR) with the fields below. Every field is cross-checked
against your manifest, so they must agree:

| Field | Value |
|-------|-------|
| `addonId` | manifest `name` (e.g. `piperNeural`) |
| `channel` | `stable`, `beta`, or `dev` (see the beta/alpha rule above) |
| `addonVersionNumber` | `{major, minor, patch}` matching the manifest version |
| `addonVersionName` | the version string, e.g. `0.4.1` |
| `displayName` | must match manifest `summary` |
| `publisher` | you or your organization |
| `description` | the store description |
| `homepage` | must match manifest `url` |
| `minNVDAVersion` | `{major, minor, patch}` matching `minimumNVDAVersion` |
| `lastTestedVersion` | `{major, minor, patch}` matching `lastTestedNVDAVersion` |
| `URL` | the direct `.nvda-addon` download URL from step 3 |
| `sha256` | computed automatically by the submission tooling |
| `sourceURL` / `license` / `licenseURL` | your repo URL, `GPL v2`, and the GPL-2.0 URL |

Version numbers must be unique per `addonId` across channels, and released in
increasing order (newer versions prompt users to update).

## Step 5: approval and validation

- **First time only:** wait for an NV Access staff member to approve you as a
  publisher for this add-on (up to two weeks). You do not need to do anything
  if you maintain the repo.
- Automated checks validate the manifest (name uniqueness and character rules,
  version format, valid NVDA API versions, all URLs `https://`) and confirm
  the download works and the manifest loads from inside the package.
- VirusTotal scans the file. Neural TTS bundles native DLLs (onnxruntime,
  espeak-ng), which are common false-positive triggers. If flagged, comment on
  the PR explaining the components; NV Access reviews and can accept false
  positives (up to two weeks).
- If checks fail, a comment explains why. Fix the issue (often the manifest),
  resubmit the issue form, and the PR updates.
- When checks pass and you are approved, the PR merges automatically and the
  version appears in the store shortly after.

## Updating later

Repeat steps 1-4 with a higher version number. No re-approval is needed once
you are an approved publisher for the add-on. Keep `lastTestedNVDAVersion`
current so users on new NVDA releases do not see the "not tested" warning.

## Translations

All user-visible strings are extracted to `addon/locale/nvda.pot`, including
the manifest `summary` and `description` that the store listing shows.
Packaging compiles any `addon/locale/<lang>/LC_MESSAGES/nvda.po` into the
add-on automatically, so shipping a language needs nothing but a `.po` file in
the tree. See [TRANSLATING.md](TRANSLATING.md).

To translate through the NVDA translation system instead, register the add-on
with Crowdin as described in the addonTemplate translation docs; the `.pot`
this repository generates is the file to upload.

## Readiness before the first store submission

Known gaps at 0.4.1, none of which block a GitHub release but all of which are
worth closing before asking users to depend on the add-on:

- **No completed translations.** The pipeline, the template, and the
  documentation for translators exist; no language has been translated yet.
  English-only is acceptable for the store, but a screen reader add-on gets
  much wider use with translations.
- **The dialogs have not had a manual accessibility pass.** The five dialogs
  are import-tested only. Run the accessibility table in
  [TESTING.md](TESTING.md) inside NVDA first.
- **The manual NVDA matrix has not been run on both NVDA generations.** The
  32-bit/64-bit claim rests on the helper being out-of-process, which is
  sound, but it has not been exercised end to end on a 2025.x and a 2026.x
  install.
- **The helper binary is unsigned.** Expect SmartScreen friction and possible
  VirusTotal false positives on the bundled native DLLs; the submission
  section above covers how NV Access handles that.
- **No user base yet.** Sonata and Dengjen are established. Expect the first
  reports to be about voices and pronunciations rather than about the engine.

## References

- Submission guide:
  https://github.com/nvaccess/addon-datastore/blob/master/docs/submitters/submissionGuide.md
- JSON metadata schema:
  https://github.com/nvaccess/addon-datastore/blob/master/docs/design/jsonMetadata.md
- Valid NVDA API versions:
  https://github.com/nvaccess/addon-datastore-transform/blob/main/nvdaAPIVersions.json
- NVDA Developer Guide:
  https://www.nvaccess.org/files/nvda/documentation/developerGuide.html
