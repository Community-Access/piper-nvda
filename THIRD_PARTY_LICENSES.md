# Third-party components and licenses

This add-on bundles or downloads the following components. Review these before
distribution; the licenses impose obligations (notably espeak-ng's GPL v3).

## Bundled in the add-on package

| Component | Role | License | Notes |
|-----------|------|---------|-------|
| espeak-ng | Text-to-phoneme conversion, loaded by the helper as `libespeak-ng.dll` | GPL v3 | https://github.com/espeak-ng/espeak-ng . Because espeak-ng is GPL v3 and is linked/loaded by the helper, the helper executable is distributed under GPL-v3-compatible terms. |
| ONNX Runtime | Neural network inference, linked into `piper-helper.exe` | MIT | https://github.com/microsoft/onnxruntime |
| DirectML | Optional GPU execution provider (`DirectML.dll`) | Proprietary (Microsoft redistributable) | Shipped only to enable the optional GPU path. |
| Rust crates | Helper dependencies (`ort`, `serde`, `serde_json`, `anyhow`, `libloading`, `minimp3`) | MIT / Apache-2.0 (per crate) | See `helper/Cargo.toml` and each crate's license. |

## Downloaded at runtime (not bundled)

| Component | Role | License | Notes |
|-----------|------|---------|-------|
| Piper voices | The neural voice models and configs downloaded through the voice manager | Various, per voice | From https://huggingface.co/rhasspy/piper-voices . Each voice has its own MODEL_CARD stating its license and dataset. Many are permissive; some datasets restrict commercial use. The add-on downloads only voices the user selects. |

## This add-on's own code

Licensed GPL-2.0-or-later (see LICENSE), the conventional license for NVDA
add-ons. The NVDA-side Python code contains no third-party bundled code beyond
the standard library and NVDA's own API.

## Compliance checklist before release

- [ ] Include the full GPL v2 text (and GPL v3 for the helper, or a clear
      pointer) in the repository and, where practical, in the package.
- [ ] Keep this file updated when dependencies change (`cargo tree` for the
      Rust side).
- [ ] Do not misrepresent voice licenses; direct users to each voice's
      MODEL_CARD for its terms.
