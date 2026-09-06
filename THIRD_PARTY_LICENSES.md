# Third-party components, licences, and credits

This add-on bundles, links, or downloads the components below. The licences
impose obligations, notably espeak-ng's GPL v3. Keep this file updated when
dependencies change (`cargo tree -e normal --depth 1` for the Rust side).

## Bundled in the add-on package

| Component | Role | Licence | Source |
|-----------|------|---------|--------|
| espeak-ng | Text to phonemes, loaded by the helper as `libespeak-ng.dll` | GPL-3.0-or-later | https://github.com/espeak-ng/espeak-ng |
| ONNX Runtime | Neural network inference, statically linked into `piper-helper.exe` | MIT | https://github.com/microsoft/onnxruntime |
| Visual C++ runtime | `msvcp140.dll`, `msvcp140_1.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`, which the helper and espeak-ng link against | Microsoft redistributable | Redistributed under the Visual Studio distributable-code terms, from the Visual Studio Build Tools' own redistributable directory. Shipping them beside the executable means users need no separate redistributable install. |

Because espeak-ng is GPL v3 and is loaded by the helper, `piper-helper.exe` is
distributed under GPL-v3-compatible terms.

### Rust crates linked into the helper

| Crate | Role | Licence |
|-------|------|---------|
| [`ort`](https://crates.io/crates/ort) | ONNX Runtime bindings, and the source of the bundled runtime binary | MIT OR Apache-2.0 |
| [`anyhow`](https://crates.io/crates/anyhow) | Error handling | MIT OR Apache-2.0 |
| [`serde`](https://crates.io/crates/serde), [`serde_json`](https://crates.io/crates/serde_json) | Protocol and voice-config JSON | MIT OR Apache-2.0 |
| [`libloading`](https://crates.io/crates/libloading) | Loading `libespeak-ng.dll` at runtime | ISC |
| [`minimp3`](https://crates.io/crates/minimp3) | Decoding voice demo samples | MIT; wraps [lieff/minimp3](https://github.com/lieff/minimp3) (CC0-1.0) |

Transitive dependencies and their licences are recorded in
`helper/Cargo.lock`.

## Downloaded at runtime, not bundled

| Component | Role | Licence | Source |
|-----------|------|---------|--------|
| Piper voices | The voice models and configs the voice manager downloads | Various, per voice | https://huggingface.co/rhasspy/piper-voices |
| Voice demo samples | The mp3 previews played before download | Per voice, as above | Same repository, `samples/` beside each voice |

Each voice has its own MODEL_CARD stating its licence and training dataset.
Many are permissive; some datasets restrict commercial use. Only voices the
user selects are downloaded, and the add-on does not restate or override those
terms: users should read the MODEL_CARD for any voice they rely on.

## Credits

- **[Piper](https://github.com/rhasspy/piper)** (MIT) by Michael Hansen and
  contributors: the voice models this add-on speaks with, and the phoneme-id
  conventions its inference code follows. This project is not affiliated with
  the Piper project.
- **[espeak-ng](https://github.com/espeak-ng/espeak-ng)**: phonemization for
  every supported language.
- **[NV Access](https://www.nvaccess.org/)** (NVDA is GPL-2.0): NVDA and its
  synthesizer driver API, which this add-on is written against. Two lists in
  this add-on are derived from NVDA's own English symbol dictionary
  (`source/locale/en/symbols.dic`): the symbol names prepared in advance, in
  `helper/src/server.rs`, and the character-name fallback table in
  `helper/src/charnames.rs`. Using NVDA's names rather than invented ones
  means a symbol is spoken here exactly as it is everywhere else in NVDA.
  Both are generated rather than hand-copied, and this add-on is
  GPL-2.0-or-later, so the licences agree.
- **[Sonata Neural Voices](https://github.com/mush42/sonata-nvda)** (GPL-2.0)
  by Musharraf Omer / Blind Pandas Team, and its maintained fork
  **[Dengjen Neural Voices](https://github.com/OnjLouis/dengjen-nvda)** by
  OnjLouis: the add-ons that brought Piper to NVDA first. No code from either
  project is used here. This add-on reads their published on-disk voice layout
  (`<NVDA config>/sonata/voices/piper/` and `<NVDA config>/dengjen/voices/
  piper/`) so that users switching over can reuse voices they already
  downloaded, and accepts the `.tar.gz` voice archives they distribute. Both
  add-ons keep working after an import; nothing is moved or deleted.

## This add-on's own code

Licensed GPL-2.0-or-later (see [LICENSE](LICENSE)), the conventional licence
for NVDA add-ons. The NVDA-side Python code contains no third-party code
beyond the Python standard library and NVDA's own API.

## Compliance checklist before release

- [ ] Include the full GPL v2 text (and GPL v3 for the helper, or a clear
      pointer) in the repository and, where practical, in the package.
- [ ] Re-run `cargo tree -e normal --depth 1` and update the crate table.
- [ ] Do not misrepresent voice licences; direct users to each voice's
      MODEL_CARD for its terms.
- [ ] Credit translators in their `.po` headers and in the changelog.
