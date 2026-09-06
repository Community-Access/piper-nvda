# Changelog

All notable changes to this add-on are documented here. This project follows
[Semantic Versioning](https://semver.org): major.minor.patch.

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
