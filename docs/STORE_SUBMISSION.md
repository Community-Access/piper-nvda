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
   If `lastTestedNVDAVersion` refers to an NVDA that is still in beta/alpha
   (marked experimental there), you must submit on the `beta` or `dev`
   channel, not `stable`.
3. Add a CHANGELOG entry for the version.
4. Confirm `summary` and `url` in the manifest are correct: the store
   `displayName` must match the manifest `summary`, and the store `homepage`
   must match the manifest `url`.

## Step 2: build and hash

```
python tools/build.py
```

Compute the SHA256 of the resulting file (the store requires it):

```
certutil -hashfile dist\piper-neural-0.1.0.nvda-addon SHA256
```

## Step 3: publish the file

Create a GitHub release (tag it, e.g. `v0.1.0`) and attach the
`.nvda-addon` as a release asset. Copy its direct download URL. It must:

- start with `https://`,
- end with `.nvda-addon`,
- download the file directly, and
- remain valid indefinitely.

## Step 4: submit to the store

Open the
[Add-on registration issue form](https://github.com/nvaccess/addon-datastore/issues/new?template=registerAddon.yml)
and fill it in. It produces a JSON metadata file (a PR) with these fields
(they must match your manifest):

| Field | Value |
|-------|-------|
| `addonId` | manifest `name` (e.g. `piperNeural`) |
| `channel` | `stable`, `beta`, or `dev` (see the beta/alpha rule above) |
| `addonVersionNumber` | `{major, minor, patch}` matching the manifest version |
| `addonVersionName` | the version string, e.g. `0.1.0` |
| `displayName` | must match manifest `summary` |
| `publisher` | you or your organization |
| `description` | the store description |
| `homepage` | must match manifest `url` |
| `minNVDAVersion` | `{major, minor, patch}` matching `minimumNVDAVersion` |
| `lastTestedVersion` | `{major, minor, patch}` matching `lastTestedNVDAVersion` |
| `URL` | the direct `.nvda-addon` download URL from step 3 |
| `sha256` | the checksum from step 2 |
| `sourceURL` / `license` | your repo URL and `GPL v2` |

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

## Optional: translations

If you want the store listing and UI translated, register the add-on with the
NVDA translation system (Crowdin) as described in the addonTemplate
translation docs. This add-on's strings are already wrapped for gettext
(`_()`), so adding `.po` files later is straightforward.

## References

- Submission guide:
  https://github.com/nvaccess/addon-datastore/blob/master/docs/submitters/submissionGuide.md
- JSON metadata schema:
  https://github.com/nvaccess/addon-datastore/blob/master/docs/design/jsonMetadata.md
- Valid NVDA API versions:
  https://github.com/nvaccess/addon-datastore-transform/blob/main/nvdaAPIVersions.json
- NVDA Developer Guide:
  https://www.nvaccess.org/files/nvda/documentation/developerGuide.html
