# Changelog

All notable changes to this add-on are documented here. This project follows
[Semantic Versioning](https://semver.org): major.minor.patch.

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
