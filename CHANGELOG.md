# Changelog

All notable changes to this add-on are documented here. This project follows
[Semantic Versioning](https://semver.org): major.minor.patch.

## [0.5.0] - 2026-09-06

### Added
- "Prepared audio" in the voice manager. Piper already prepares the alphabet
  and the words NVDA says most often while it is idle, so they speak with no
  delay; this adds words and short phrases of your own to that list, queued
  ahead of the built-in ones. It also reports how much space the prepared
  audio uses and can rebuild it from scratch. Phrases are limited to 40
  characters, because beyond that an utterance is split before it is spoken
  and the prepared audio would never be looked up.
- A "Prepare audio in the background" setting, for turning preparation and
  reuse off entirely.

### Changed
- Supported Windows is now Windows 11 and later. The add-on still runs on
  Windows 10, and nothing blocks installing it there, but it is not tested on
  it. The driver logs a warning naming the Windows build when it starts on
  anything older, so a report from an unsupported machine explains itself.
- The protocol gained SET_CACHE and CLEAR_CACHE, and LOAD_VOICE carries the
  user's phrases.

## [0.4.1] - 2026-09-06

### Fixed
- The add-on now bundles the Visual C++ runtime (`msvcp140.dll`,
  `msvcp140_1.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`). Both the helper
  and espeak-ng link against it, and it is not part of Windows, so on a
  machine that had never had the Visual C++ redistributable installed the
  helper failed to start with a bare missing-DLL error. There are now no
  prerequisites at all. Packaging fails loudly if the runtime cannot be found
  rather than shipping without it.

### Added
- `tools/pe_imports.py`, which lists what a packaged binary actually depends
  on at run time. `dumpbin` is not present on a machine with only the Rust
  toolchain, and static linking hides these dependencies from the source.

### Changed
- Documented that Windows 10 (64-bit) or Windows 11 is required, and why: the
  ONNX Runtime build in use imports DirectML and Direct3D 12, which Windows
  8.1 does not have. Removing the DirectML *option* in 0.2.0 did not remove
  those imports, because the prebuilt runtime is a DirectML build and the
  cargo feature only gated the Rust-side API.

## [0.4.0] - 2026-09-06

### Fixed
- Six published voices declare a language-specific phonemizer this add-on does
  not include (two Chinese voices want pinyin; one each for Hebrew, Japanese,
  and Thai). They were being synthesized from espeak's IPA, which produces
  fluent nonsense rather than an error. The voice configuration is now read
  before the model is downloaded, unusable voices are explained and refused,
  already-installed ones are left out of the voice list, and the helper
  reports `unsupportedVoice` rather than speaking.
- `pt_PT-tugão-medium` could not be downloaded or auditioned at all: its
  catalog path is not ASCII, and Python's `urllib` refuses such a URL before
  sending it. Catalog paths are now percent-encoded.
- Voice-level `phoneme_map` substitutions were ignored. Piper applies them
  before phoneme ids are looked up; now so do we.
- `inference.phoneme_silence` was ignored. Voices asking for silence after
  particular phonemes now get it, synthesized around the gap as Piper does.

### Added
- Support for NVDA's `PhonemeCommand`, the one synth-facing command in NVDA's
  API that was missing. A pronunciation NVDA supplies is spoken as given, and
  falls back to the text it stood for if the voice has no sound for one of the
  phonemes.
- A "Pause between sentences" setting. Model output is now trimmed at both
  ends and the gaps between clauses are inserted deliberately: the full pause
  after `.`, `!`, `?` and two fifths of it after `,`, `;`, `:`. Pauses shorten
  with the rate, and never trail the end of an utterance.
- `helper/examples/model_io.rs`, which prints a model's ONNX inputs and
  outputs. It is what establishes that the published models expose audio only,
  with no durations or alignments, so word-level timing is not available
  without re-exporting every voice.

### Changed
- Sample-rate conversion uses a Lanczos-3 windowed-sinc resampler instead of
  linear interpolation. 40 of the 176 published voices are not at the output
  rate, and linear interpolation was audibly harsh on them.
- The audio cache stores trimmed entries and its format version is 2, so
  caches written by earlier versions are discarded and rebuilt.
- Protocol segments carry `ipa`, `fallbackText`, and `sentencePauseMs`.

## [0.3.0] - 2026-09-06

### Added
- Advanced voice parameters. "Show advanced voice parameters" in the Speech
  settings replaces the single Expressiveness control with Piper's own
  `noise_scale`, `noise_w`, and `length_scale`, under the names Piper uses.
  Each is a percentage of the voice's trained value, where 50 means "as
  trained", so one setting means the same thing across voices trained with
  different values, and the advanced defaults are identical to Expressiveness
  at 50. This brings parity with the controls the Sonata and Dengjen add-ons
  expose, without making every user meet three interacting numbers.

### Changed
- The driver now sends inference-parameter multipliers as a `scales` object
  per segment instead of a single `variance` value, and all three are in the
  audio cache key. Protocol version 2.
- `supportedSettings` is computed per driver instance rather than fixed on the
  class, so the advanced parameters can replace the simple control. Toggling
  the mode refreshes the open Speech settings panel where it can, and says to
  reopen the dialog where it cannot.

## [0.2.0] - 2026-09-06

### Added
- Pronunciation lexicon: give any word the exact IPA phonemes it should be
  spoken with, from "Pronunciations" in the voice manager, with a Preview
  button that speaks the entry before it is saved. Entries match whole words,
  ignore capitalization, and apply to every voice. Stored in `lexicon.json`.
- Per-language voice assignment: with several voices for one language,
  "Language voices" in the voice manager says which one automatic language
  switching uses. Stored in `language_voices.json`.
- Import voices from other add-ons: voices installed by Sonata Neural Voices
  and Dengjen Neural Voices are found automatically and copied in, instead of
  being downloaded again. Nothing is moved or deleted, so those add-ons keep
  working.
- Install a voice from a file: a `.tar.gz` voice archive or a `.onnx` model
  with its `.onnx.json` beside it, for computers with no internet connection.
  Archives are extracted defensively (no path traversal, models and configs
  only).
- Expressiveness setting: scales the voice's trained noise parameters. 50 is
  the voice as trained, lower is flatter and steadier, higher is more
  animated. Available in the settings ring.
- Translation support: `tools/i18n.py` extracts strings to
  `addon/locale/nvda.pot` and compiles `.po` files into the package, with no
  dependency on GNU gettext. See `docs/TRANSLATING.md`.

### Removed
- The DirectML GPU option. Measured on an integrated GPU it was 6x slower than
  the CPU for single characters and 1.7x slower for a full sentence, because
  Piper models are small enough that dispatch overhead dominates. Removing it
  also drops 18.5 MB (`DirectML.dll`) from the download.

### Changed
- The audio cache key now covers expressiveness and, for chunks that contain
  an overridden word, the lexicon revision. Editing a pronunciation
  invalidates only the chunks that use it.
- Renamed internal identifiers, log messages, and the cache file that still
  carried the name of the project this helper was adapted from.
- `COMPARISON.md` now compares against the maintained Dengjen fork rather than
  the discontinued Sonata release, and separates measured numbers from
  structural claims.

## [0.1.0] - 2026-09-05

### Added
- Initial release: "Piper Neural Voices" synthesizer for NVDA.
- Bundled 64-bit inference helper (Rust + ONNX Runtime + espeak-ng); works on
  32-bit NVDA 2025.x and 64-bit NVDA 2026.1+, with crash isolation.
- In-app voice manager (Tools menu): browse the full Piper voices catalog,
  filter by language, download voices with md5 verification and resume, and
  remove installed voices.
- Hear a demo of any voice before downloading, played through NVDA's audio.
- Full synthesizer support: voice selection, multi-speaker voices via the
  Variant setting, rate, rate boost, pitch, volume, index/done notifications,
  spelling/character mode, break, prosody commands, and automatic language
  switching.
- Audio cache with idle-time warmup of the alphabet and common NVDA words,
  persisted between sessions, making character echo and navigation instant at
  any rate.
- Optional DirectML GPU acceleration with automatic CPU fallback.
