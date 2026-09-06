# Testing and verification

This project has three layers of checks: fast Rust unit tests, Python tests
(pure logic plus real-helper integration), and a manual NVDA test matrix that
must be run before a release.

## Rust tests

```
cd helper
cargo test                         # unit tests (no assets needed)
cargo test -- --ignored --test-threads=1   # tests that need dev assets
```

The `--ignored` tests load the real espeak-ng runtime and a real voice config
from `assets/`, so run `python tools/fetch_assets.py` first. They must run
single-threaded because espeak-ng is not thread safe.

Coverage includes: protocol framing (round trips, oversize rejection, audio
frame layout), the `.onnx.json` config parser and the Piper phoneme-id
sequence (the `interspersePad` convention), DSP (time-stretch length and
energy, pitch-shift frequency and duration, silence trim), text chunking, and
the audio cache (put/get, rate-independent keys, eviction, disk persistence).

## Python tests

```
python -m pytest tests/python -q
```

`tests/python/conftest.py` puts the add-on package on the path and installs
lightweight NVDA API stubs (`nvda_stubs/`) so the driver modules import
without NVDA. Coverage:

- `test_catalog_download.py` - parsing the HuggingFace `voices.json`, building
  model/config/sample URLs, multi-speaker handling, and the download engine
  (md5 verification, rejection of a bad checksum, ranged resume).
- `test_build_job.py` - converting an NVDA speech sequence into a SPEAK job:
  index boundaries, language switching to a different model, breaks, character
  mode, pitch commands, rate-as-stretch, speaker/variant to `sid`, and the
  available-voice/variant lists.
- `test_full_stack.py` - drives the **real** `piper-helper.exe` through the
  real `_helperProc` and `_audio` classes: speaks a phrase and checks audio,
  ordered index markers, and DONE; and plays a real demo mp3 through
  PLAY_SAMPLE. Skipped automatically if the release build or assets are
  missing.

## Latency benchmarks

```
python tools/bench_stream.py lessac-medium.onnx   # streaming first-audio
python tools/bench_ipc.py                          # pure IPC round-trip
helper/target/release/piper-helper.exe --model assets/lessac-medium.onnx --bench
```

Record the numbers in [../COMPARISON.md](../COMPARISON.md) when they change
materially. The targets that matter for a screen reader:

- Cancel-to-silence: effectively instant (sub-millisecond).
- Cached character echo and common words: effectively instant.
- New-text first audio: as low as the model allows on the target CPU.

## Manual NVDA test matrix

Automated tests cover logic and the helper, but the real synth must be
exercised inside NVDA before release.

Setup for quick iteration (no repackaging): copy `addon/synthDrivers/piper`
and `addon/globalPlugins/piperManager` into
`%APPDATA%\nvda\scratchpad\` under the matching subfolders (enable the
scratchpad in NVDA's Advanced settings first), build the helper, and copy the
`bin/` payload in. Reload plugins with NVDA+Control+F3. Open the log with
NVDA+F1 and the Python console with NVDA+Control+Z.

Run through this matrix on each supported configuration:

| Area | Check |
|------|-------|
| Install | Add-on installs and loads with no errors in the log |
| Voice manager | Opens from Tools; catalog loads; language filter works |
| Demo | "Play demo" plays a sample; "Stop demo" stops it; works while a different synth is active |
| Download | Voice downloads with progress; cancel works; installed status updates |
| Select synth | Piper appears in Speech settings and speaks |
| Settings ring | Voice, variant, rate, rate boost, pitch, volume all change speech |
| Multi-speaker | A multi-speaker voice changes speaker via Variant |
| Typing echo | Characters echo with no perceptible delay |
| Spelling | Reading by character speaks letters correctly |
| Say all | Reads a long document, tracks the caret, no stalls |
| Language switching | With auto language switching on, a mixed-language document uses matching voices |
| Rate boost | Very fast speech is intelligible |
| Cancel | Arrow/keystroke interruption is immediate |
| Uninstall | Uninstalls cleanly; prompts about deleting voices |

Configurations to cover: NVDA 2025.1 (32-bit) and the latest 2026.x (64-bit);
Windows 10 and 11; at least one low-quality and one medium-quality voice; and,
if available, a machine with a DirectML-capable GPU for the GPU toggle.

## Pre-release verification checklist

- [ ] `cargo test` and `cargo test -- --ignored --test-threads=1` pass.
- [ ] `python -m pytest tests/python` passes.
- [ ] Benchmarks recorded if performance changed.
- [ ] Version bumped in `manifest.ini` and `CHANGELOG.md` updated.
- [ ] `python tools/build.py` produces the `.nvda-addon` with no
      `__pycache__`/`.pyc` and with the helper and espeak payload present.
- [ ] Manual matrix passed on 32-bit and 64-bit NVDA.
- [ ] `readme.html` opens correctly from the Add-on Store help.
- [ ] `lastTestedNVDAVersion` matches the newest NVDA verified.
