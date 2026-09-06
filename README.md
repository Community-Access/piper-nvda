# Piper Neural Voices for NVDA

Fast, natural, fully offline neural text-to-speech for the NVDA screen reader,
powered by the [Piper](https://github.com/rhasspy/piper) voices. Browse,
audition, and download dozens of voices in many languages from inside NVDA,
and speak with the responsiveness of a classic synthesizer thanks to an audio
cache that makes typing echo and navigation instant.

- Dozens of languages, multiple quality tiers, and multi-speaker voices.
- Runs entirely on your machine. No internet needed after voices are
  downloaded, no accounts, no telemetry.
- A bundled 64-bit inference helper keeps heavy code out of NVDA, so a model
  fault can never crash your screen reader, and one build works on both
  32-bit NVDA (2025.x) and 64-bit NVDA (2026.1+).
- Hear a demo of any voice before you download it.
- Fix how any word is pronounced, in IPA phonemes, with a preview button.
- Choose which voice each language uses when NVDA switches language.
- Reuse voices you already downloaded for the Sonata or Dengjen add-ons, or
  install a voice from a file with no internet connection at all.

## Quick start

1. Install the add-on (NVDA menu, Tools, Add-on Store, or Install from
   external source, then choose the `.nvda-addon` file).
2. Open NVDA menu, Tools, "Piper voice manager".
3. Pick a language, select a voice, press **Play demo** to hear it, then
   **Download**.
4. Open NVDA menu, Preferences, Settings, Speech, and choose "Piper Neural
   Voices" as your synthesizer.

Full instructions are in [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Why it is fast

Piper is a light VITS model that runs many times faster than real time on a
normal CPU. On top of that, this add-on caches synthesized audio and warms
the alphabet plus the words NVDA speaks most (roles, states, common words)
during idle time, so character echo and navigation are effectively instant at
any speech rate. See [COMPARISON.md](COMPARISON.md) for measured numbers and a
head-to-head against the Kokoro neural voices add-on.

## Documentation

- [User guide](docs/USER_GUIDE.md) - install, settings, voice manager,
  pronunciations, troubleshooting.
- [Architecture](docs/ARCHITECTURE.md) - how the helper, driver, cache, and
  audio pipeline fit together.
- [Design decisions](docs/DECISIONS.md) - why it works that way, and what
  evidence would justify changing it.
- [IPC protocol](docs/PROTOCOL.md) - the driver-to-helper message reference.
- [Building from source](docs/BUILDING.md) - prerequisites and the build
  pipeline.
- [Testing and verification](docs/TESTING.md) - the automated suites, the
  latency benchmarks, and the manual NVDA test matrix.
- [Add-on Store submission](docs/STORE_SUBMISSION.md) - the full release and
  submission process.
- [Translating](docs/TRANSLATING.md) - how to add a language.
- [Contributing and coding standards](CONTRIBUTING.md).
- [Changelog](CHANGELOG.md).
- [Licensing](LICENSE) and [third-party notices](THIRD_PARTY_LICENSES.md).

## Project layout

```text
piper/
  addon/            NVDA add-on tree (packaged into the .nvda-addon)
    synthDrivers/piper/     the SynthDriver and its helper-facing modules
    globalPlugins/piperManager/   Tools-menu entry for the voice manager
    manifest.ini, installTasks.py, doc/
  helper/           Rust crate: piper-helper.exe (ONNX inference + espeak-ng)
  tools/            build.py (packaging), i18n.py, fetch_assets.py, benchmarks
  tests/python/     pytest suite with NVDA API stubs
  docs/             this documentation set
```

## Credits

Voices come from the [Piper voices](https://huggingface.co/rhasspy/piper-voices)
project; each voice has its own MODEL_CARD stating its licence and dataset.
Phonemization uses [espeak-ng](https://github.com/espeak-ng/espeak-ng).
Inference uses [ONNX Runtime](https://onnxruntime.ai/) via the
[`ort`](https://crates.io/crates/ort) crate. Demo samples are decoded with
[`minimp3`](https://crates.io/crates/minimp3).

[Sonata Neural Voices](https://github.com/mush42/sonata-nvda) by Musharraf
Omer, and its maintained fork
[Dengjen Neural Voices](https://github.com/OnjLouis/dengjen-nvda), brought
Piper to NVDA first. No code from either project is used here; this add-on
reads their on-disk voice layout so users switching over can reuse voices they
already have.

This project is not affiliated with NV Access, the Piper project, or the
add-ons named above. Full attribution and licences are in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
