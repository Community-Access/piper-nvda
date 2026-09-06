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
- `test_voice_data.py` - the files the add-on manages: lexicon load/save and
  revision bumps, recovery from a damaged file, language assignment
  resolution and fallback, discovery and import of Sonata/Dengjen voices, and
  installing from an archive or a model file (including rejection of a
  path-traversal archive and of an archive with no model/config pair).
- `test_manager_ui_imports.py` - the voice manager cannot be driven without a
  real wx, so this imports it against a permissive `wx` stub and checks every
  dialog is still there. It catches the failure that would otherwise only
  appear inside NVDA: a name used at module scope that no longer exists.
- `test_catalog_download.py` also covers percent-encoding of the one
  published voice whose name is not ASCII.
- `test_i18n.py` - the translation pipeline: string extraction with
  translator comments, that the committed `.pot` matches the source, and a
  `.po` to `.mo` round trip read back through `gettext`, including that fuzzy
  and untranslated entries do not ship.
- `test_full_stack.py` - drives the **real** `piper-helper.exe` through the
  real `_helperProc` and `_audio` classes: speaks a phrase and checks audio,
  ordered index markers, and DONE; plays a real demo mp3 through PLAY_SAMPLE;
  proves a lexicon entry changes the audio and that clearing it restores the
  original; proves expressiveness is cached separately; proves a
  PhonemeCommand reaches the model as phonemes and falls back to its text
  when the voice lacks one; proves the sentence pause lengthens gaps by the
  requested amount; and proves a voice needing another phonemizer is refused
  with `unsupportedVoice` and no audio, while still finishing so speech never
  stalls. Skipped
  automatically if the release build or assets are missing.

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
| Language voices | An assignment overrides the default choice for that language; "Automatic" restores it |
| Pronunciations | An entry changes how the word is spoken, in every voice; Preview speaks it before saving; removing it restores the original |
| Import voices | Voices from an installed Sonata or Dengjen add-on are listed and copied in; that add-on still works afterwards |
| Install from file | A `.tar.gz` archive and a `.onnx`+`.onnx.json` pair both install |
| Expressiveness | Changing it audibly changes delivery, and echo stays instant once re-warmed |
| Advanced parameters | Toggling "Show advanced voice parameters" swaps Expressiveness for the three raw parameters (reopening Speech settings if needed); each changes the voice; length scale above 50 slows the model |
| Sentence pause | Raising it lengthens the gaps at full stops and, less, at commas; 0 removes them; gaps shrink as the rate rises |
| Unsupported voice | Downloading zh_CN-xiao_ya-medium, he_IL-saspeech-medium, ja_JA-hi_fi_captain-medium, th_TH-tsync2-medium, or uk_UA-ukrainian_tts-medium explains why it cannot be used and does not download the model |
| 16 kHz voice | A low-quality voice (for example en_GB-alan-low) sounds clean rather than harsh |
| Rate boost | Very fast speech is intelligible |
| Cancel | Arrow/keystroke interruption is immediate |
| Uninstall | Uninstalls cleanly; prompts about deleting voices |

### Accessibility pass on the dialogs

Automated tests can only prove the manager's dialogs import. Every dialog
(voice manager, Import voices, Pronunciations, Pronunciation entry, Language
voices) needs a keyboard-only pass before release:

| Check | Expectation |
|-------|-------------|
| Reachability | Every control is reachable with Tab and Shift+Tab, in reading order |
| Labels | Each control announces a meaningful name, not "edit" or "button" alone |
| Accelerators | Every `&` accelerator works and none collide within a dialog |
| Initial focus | Focus lands on the list or first field, and is announced |
| Focus after action | After add, edit, remove, or import, focus is on a sensible item and the change is announced |
| Escape and Enter | Escape cancels without saving; Enter activates the default button |
| Progress and errors | Download progress and failures are announced, not only drawn |
| Screen reader output | Announcements are useful heard aloud, not just technically present |

Configurations to cover: NVDA 2025.1 (32-bit) and the latest 2026.x (64-bit);
Windows 10 and 11; at least one low-quality and one medium-quality voice; and,
if available, a second machine with a slower CPU to sanity-check latency.

## Pre-release verification checklist

- [ ] `cargo test` and `cargo test -- --ignored --test-threads=1` pass.
- [ ] `python -m pytest tests/python` passes.
- [ ] Benchmarks recorded if performance changed.
- [ ] Version bumped in `manifest.ini` and `CHANGELOG.md` updated.
- [ ] `python tools/build.py` produces the `.nvda-addon` with no
      `__pycache__`/`.pyc` and with the helper and espeak payload present.
- [ ] Manual matrix passed on 32-bit and 64-bit NVDA.
- [ ] Accessibility pass completed on all five dialogs.
- [ ] `python tools/pe_imports.py addon/synthDrivers/piper/bin/piper-helper.exe`
      lists nothing beyond `api-ms-win-*` apisets, core Windows DLLs, and
      files the package ships. Anything else is a dependency users would have
      to install themselves.
- [ ] `python tools/i18n.py extract` run and `nvda.pot` committed if strings
      changed (the `test_pot_is_current` test enforces this).
- [ ] `python tools/i18n.py compile` reports no unreadable `.po` files.
- [ ] `readme.html` opens correctly from the Add-on Store help.
- [ ] `lastTestedNVDAVersion` matches the newest NVDA verified.
