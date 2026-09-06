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
  troubleshooting.
- [Architecture](docs/ARCHITECTURE.md) - how the helper, driver, cache, and
  audio pipeline fit together.
- [IPC protocol](docs/PROTOCOL.md) - the driver-to-helper message reference.
- [Building from source](docs/BUILDING.md) - prerequisites and the build
  pipeline.
- [Testing and verification](docs/TESTING.md) - the automated suites, the
  latency benchmarks, and the manual NVDA test matrix.
- [Add-on Store submission](docs/STORE_SUBMISSION.md) - the full release and
  submission process.
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
  tools/            build.py (packaging), fetch_assets.py, benchmarks
  tests/python/     pytest suite with NVDA API stubs
  docs/             this documentation set
```

## Credits

Voices come from the [Piper voices](https://huggingface.co/rhasspy/piper-voices)
project. Phonemization uses [espeak-ng](https://github.com/espeak-ng/espeak-ng).
Inference uses [ONNX Runtime](https://onnxruntime.ai/) via the
[`ort`](https://crates.io/crates/ort) crate. This project is not affiliated
with NV Access or the Piper project.
