# How this add-on compares

Two comparisons matter for this project: against the other Piper-based NVDA
add-ons a user could install today, and against the Kokoro neural voices
add-on that shares this project's architecture.

## What is on offer today

| Add-on | Status | Engine |
|--------|--------|--------|
| [Sonata Neural Voices](https://github.com/mush42/sonata-nvda) | Last release v3.1.0, June 2024 | Rust `sonata` engine over gRPC, ONNX Runtime, espeak-ng |
| [Dengjen Neural Voices](https://github.com/OnjLouis/dengjen-nvda) | Maintained fork of Sonata; documents NVDA 2025.1 through 2026.1 | Same engine, kept building against current NVDA |
| [rmcpantoja/piper-nvda](https://github.com/rmcpantoja/piper-nvda) | Separate Piper driver | Piper |
| This add-on | 0.4.1 | Rust helper over stdio, ONNX Runtime, espeak-ng |

Sonata is the original and is no longer released; Dengjen is the version to
compare against, and is the one this document means whenever it says "the
Sonata family".

**Honesty about method.** The Piper and Kokoro numbers below were measured on
this machine. The Sonata-family behaviour described here comes from reading
[its source](https://github.com/mush42/sonata-nvda) and its documentation, not
from a head-to-head run on the same hardware. Where this document says
something is faster, it says why structurally rather than quoting a number
that was never measured.

## Measured: first-audio latency for new (uncached) text

AMD Ryzen 5 Surface Edition (Zen 2 mobile, 6 cores), CPU inference, plugged
in. Reproduce with
`helper/target/release/piper-helper.exe --bench --model assets/lessac-medium.onnx`.

| Case | Kokoro (fp16) | Piper lessac-medium | Piper ryan-low |
|------|---------------|---------------------|----------------|
| single char / word | ~370-450 ms | ~21-34 ms | ~21 ms |
| short line | ~630 ms | ~55-92 ms | ~55 ms |
| full sentence (total synth) | ~2.0-5.5 s (RTF ~1x) | ~180-200 ms (RTF ~17x) | ~134 ms (RTF ~22x) |

## Measured: cached text (character echo, common words, re-reads)

| Case | Kokoro | Piper |
|------|--------|-------|
| warmed char / word / re-read | 0-13 ms (instant) | 0 ms (instant) |
| cancel-to-silence | <1 ms | <1 ms |

## Measured: DirectML is slower than the CPU here

Version 0.1.0 shipped an optional DirectML GPU path and the 18.5 MB
`DirectML.dll` that goes with it. Measured on the integrated GPU of the
machine above, same benchmark:

| Case | CPU | DirectML |
|------|-----|----------|
| single char | 30-38 ms | 234 ms |
| short line | 77-82 ms | 277 ms |
| full sentence | 180-194 ms | 305 ms |

Piper models are small enough that per-inference GPU dispatch overhead
dominates, and short utterances are exactly what a screen reader spends its
time on. The option was removed in 0.2.0 rather than left as a setting that
makes things worse, which also took 18.5 MB off the download.

## Structural differences from the Sonata family

These follow from the design rather than from a benchmark:

- **Audio cache and idle warmup.** This add-on caches raw model output and
  warms the alphabet plus the words NVDA says most (roles, states, common
  words) during idle time, persisted between sessions, so character echo and
  navigation cost no inference at all. The Sonata family has no such cache;
  its answer to latency is shipping separate "fast" (RT) model variants, which
  trades quality for speed. Both approaches help; only one of them is free.
- **Rate does not re-synthesize.** Rate here is a post-cache WSOLA
  time-stretch and pitch is a post-cache shift, so one cached entry serves
  every rate, pitch, and volume. The Sonata family changes the model's
  `length_scale`, so a rate change is new model output.
- **Live catalog.** Voices are read straight from the
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  `voices.json` (~176 voices), so new voices appear without an add-on update.
  The Sonata family installs repackaged archives, which need maintainer action
  for anything new. This add-on can also install those archives (see below).
- **Pronunciation lexicon.** Whole-word IPA overrides with a preview button,
  applied before phonemization. The Sonata family, and Piper generally, leave
  you with whatever espeak-ng guesses; its own documentation notes that "some
  voices may exhibit incorrect or weird pronunciation".
- **Per-language voice assignment.** With several voices for one language, you
  choose which one automatic language switching uses.
- **Complete NVDA synth API.** Every synth-facing command NVDA defines is
  implemented, including `PhonemeCommand`, so a pronunciation NVDA supplies is
  spoken as given rather than falling back to its plain text.
- **No prerequisites.** The Visual C++ runtime ships inside the add-on, so
  installing it is enough. The Sonata family documents the Visual C++
  redistributable as something the user must install first.
- **Voices it cannot speak are refused.** Six published voices declare a
  phonemizer no NVDA Piper add-on bundles. This add-on reads `phoneme_type`
  and explains the problem before downloading the model, rather than
  synthesizing them from the wrong phonemes.
- **Punctuation-timed pauses.** Model output is trimmed at both ends and the
  gaps between clauses are inserted deliberately, with a user setting, so
  rhythm does not depend on how much silence each model run happened to
  produce.
- **Simple by default, precise on request.** One Expressiveness control by
  default; "Show advanced voice parameters" swaps it for `noise_scale`,
  `noise_w`, and `length_scale` under the names Piper uses, so users coming
  from the Sonata family get the same control they had. They are expressed as
  percentages of each voice's trained value rather than absolute numbers, so
  one setting means the same thing across voices.

## Where the Sonata family is still ahead

- **Maturity.** Sonata has been in use for years and Dengjen is actively
  maintained; this add-on is new and has no user base yet.
- **Translations.** Sonata ships many locales and translated documentation.
  This add-on has the extraction pipeline and a template, and no completed
  translations yet.

## Fidelity details

Both projects run the same models, so audio quality differences come from what
happens around them:

- 40 of the 176 voices are not at 22050 Hz (39 at 16 kHz, one at 44.1 kHz).
  This add-on resamples them with a windowed sinc rather than linear
  interpolation, which is audible on exactly those voices.
- `phoneme_map` and `inference.phoneme_silence`, two rarely used per-voice
  fields in the Piper contract, are honored.
- The one published voice whose name is not ASCII (`pt_PT-tugão-medium`) is
  downloadable; a raw non-ASCII URL is rejected by Python's `urllib` before it
  is ever sent.

## Switching cost

Because both store ordinary Piper `.onnx` models on disk, "Import voices" in
the voice manager copies voices installed by Sonata or Dengjen instead of
re-downloading them, and "Install from file" accepts their `.tar.gz` voice
archives. Nothing is moved or deleted, so the other add-on keeps working.

## Takeaway

- Against Kokoro: Piper is roughly 10x faster per inference on this CPU while
  keeping the same instant cached echo, and offers far more voices and
  languages.
- Against the Sonata family: the cache, the rate design, and the live catalog
  are real advantages, and the lexicon addresses a limitation those add-ons
  document but do not fix. Their advantages are maturity and translations,
  both of which are time rather than architecture.
