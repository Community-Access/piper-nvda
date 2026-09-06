# Building from source

## Prerequisites

- **Rust** (stable) with the MSVC toolchain, targeting
  `x86_64-pc-windows-msvc`. Install from https://rustup.rs.
- **Python 3.11+** for the build and test scripts. (The add-on code itself is
  written to run on NVDA's embedded Python, which is 3.11 on NVDA 2025.x and
  3.13 on 2026.1+; avoid syntax newer than 3.11 in `addon/`.)
- **Windows 10/11 64-bit**.
- Internet access for the first build (to download crates and dev assets).

You do not need NVDA installed to build or run the automated tests, but you
do need it to run the manual test matrix in [TESTING.md](TESTING.md).

## One-time: fetch development assets

The helper needs espeak-ng, and the tests and benchmarks need a couple of
sample voices. Fetch them once:

```
python tools/fetch_assets.py
```

This downloads into `assets/` (which is gitignored):

- `espeak-ng/` - the espeak-ng 1.52 runtime (DLL plus `espeak-ng-data`),
  extracted from the official MSI.
- `lessac-medium.onnx` and `ryan-low.onnx` plus their `.onnx.json` configs -
  two test voices.
- `sample_lessac.mp3` - a demo sample for the demo-playback test.

These dev assets are for building and testing only. End users download voices
at runtime through the voice manager; no voices are bundled in the package.

## Build the helper

```
cd helper
cargo build --release
```

Output: `helper/target/release/piper-helper.exe`. ONNX Runtime is linked in,
so the exe runs on its own. `DirectML.dll` is produced beside it for the
optional GPU path.

Run it directly to sanity-check:

```
piper-helper.exe --model ../assets/lessac-medium.onnx --say "Hello." --out test.wav
piper-helper.exe --model ../assets/lessac-medium.onnx --bench
```

## Package the add-on

```
python tools/build.py
```

This runs `cargo build --release`, stages the `addon/` tree, copies
`piper-helper.exe`, `onnxruntime.dll`, `DirectML.dll`, and the espeak-ng
runtime into `synthDrivers/piper/bin/`, renders `doc/en/readme.html` from the
Markdown, and writes `dist/piper-neural-<version>.nvda-addon`.

Use `--skip-cargo` to package without rebuilding the helper:

```
python tools/build.py --skip-cargo
```

The resulting `.nvda-addon` is a zip. It contains code and the helper binary
but no voice models; those download at runtime.

## What goes in the package

```text
manifest.ini
installTasks.py
doc/en/readme.html
synthDrivers/piper/*.py
synthDrivers/piper/bin/piper-helper.exe
synthDrivers/piper/bin/onnxruntime.dll
synthDrivers/piper/bin/DirectML.dll
synthDrivers/piper/bin/espeak-ng/libespeak-ng.dll
synthDrivers/piper/bin/espeak-ng/espeak-ng-data/...
globalPlugins/piperManager/__init__.py
```

No `__pycache__`, `.pyc`, tests, or dev assets are included.

## Versioning

The version lives in `addon/manifest.ini` (`version = major.minor.patch`).
Bump it before every release and add a matching entry to
[../CHANGELOG.md](../CHANGELOG.md). Keep `lastTestedNVDAVersion` current with
the newest NVDA you have verified against. See
[STORE_SUBMISSION.md](STORE_SUBMISSION.md) for the release flow.
