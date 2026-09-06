# Design decisions

Why this add-on is built the way it is. Each entry states the situation, the
decision, and what it costs, so a future maintainer can tell a deliberate
choice from an accident and knows what evidence would justify reversing it.

## Inference runs in a separate 64-bit helper process

**Context.** NVDA 2025.x is 32-bit and NVDA 2026.1 is 64-bit. ONNX Runtime is
a large native dependency, and a fault in a model or in the runtime takes down
the process it lives in.

**Decision.** Put all inference in `piper-helper.exe`, an out-of-process
64-bit binary the driver talks to over stdio.

**Consequences.** One build serves both NVDA generations, and a crash costs a
helper restart rather than the user's screen reader. The cost is an IPC hop,
measured at about 0.06 ms round trip, which is noise next to inference. It
also means the add-on ships a 22 MB executable.

## The audio cache stores raw model output

**Context.** A screen reader speaks the same characters, roles, and states
constantly. Synthesizing "checkbox" from scratch every time is waste that the
user experiences as latency.

**Decision.** Cache the model's output before any DSP, keyed on voice,
character-mode, expressiveness, lexicon revision, and text — but not on
pitch, volume, or rate. Warm the alphabet and a curated list of common NVDA
words during idle time and persist the cache between sessions.

**Consequences.** Character echo and navigation cost no inference at all, at
any rate or pitch. This is the single largest behavioural difference from
other Piper add-ons for NVDA. The cost is disk and memory for the cache, and
the discipline that anything affecting model output must be in the key.

## Rate is a post-cache time-stretch, not a model parameter

**Context.** Piper exposes `length_scale`, which changes how fast the model
speaks. Using it would put rate into the cache key and make every rate change
a fresh synthesis.

**Decision.** Always run the model at the voice's trained speed and apply the
entire rate setting as a WSOLA time-stretch after the cache. Pitch is a
post-cache shift for the same reason.

**Consequences.** One cached entry serves every rate, pitch, and volume, so
changing rate is free and NVDA's capital-letter pitch change costs nothing.
The cost is that extreme rates are a stretch artefact rather than the model
genuinely speaking faster; at the ranges screen reader users work in this is
the better trade.

## The lexicon revision is scoped to affected chunks

**Context.** A pronunciation entry changes model output, so it has to be in
the cache key for correctness. Putting a global revision in every key would
throw away the whole warmed cache each time a user adds one word.

**Decision.** Fold the lexicon revision into the key only for chunks that
actually contain an overridden word; every other chunk keys with revision 0.

**Consequences.** Adding a pronunciation invalidates the handful of chunks
that use it. Removing an entry falls back to the pre-lexicon cache entries,
which are still correct. This is verified end to end in
`tests/python/test_full_stack.py`.

## Pronunciation overrides are spliced as IPA, not as respelled text

**Context.** Voices take phonemes from espeak-ng, which mispronounces names,
acronyms, and loan words often enough that Piper-based add-ons document it as
a known limitation. A user cannot retrain a voice.

**Decision.** Accept a word to IPA map. Split each chunk into runs: overridden
words become their IPA verbatim, everything between them still goes through
espeak-ng, and the results are joined with spaces (which is how espeak already
separates words in its own output).

**Consequences.** A fix is exact and works in every voice and language,
rather than depending on finding a misspelling that happens to sound right.
Prosody around the substitution is unaffected. The cost is that users must
write IPA, which is why the editor has a Preview button.

## The DirectML GPU option was removed

**Context.** Version 0.1.0 shipped an optional DirectML execution provider and
the 18.5 MB `DirectML.dll` it needs.

**Evidence.** Measured on the integrated GPU of an AMD Ryzen 5 Surface Edition,
same benchmark as the CPU numbers in [../COMPARISON.md](../COMPARISON.md):

| Case | CPU | DirectML |
|------|-----|----------|
| single char | 30-38 ms | 234 ms |
| short line | 77-82 ms | 277 ms |
| full sentence | 180-194 ms | 305 ms |

**Decision.** Remove the setting, the `directml` cargo feature, and the DLL.

**Consequences.** Piper models are small enough that per-inference dispatch
overhead dominates, and short utterances are what a screen reader spends its
time on, so the option made the common case six times worse while looking like
an optimization. Removing it also took 18.5 MB off the download. Reverting
would need measurements on a discrete GPU showing a win on *short* utterances,
not just on long ones.

## One Expressiveness control instead of three raw parameters

**Context.** Piper voices carry `noise_scale`, `noise_w`, and `length_scale`.
Other add-ons expose all three directly.

**Decision.** Expose a single Expressiveness setting, 0-100, that scales the
voice's trained `noise_scale` and `noise_w` together (0.4x to 1.6x, with 50
meaning "as trained"). `length_scale` stays at the trained value because rate
is handled by time-stretch.

**Consequences.** One setting in the settings ring that a non-technical user
can turn, instead of three numbers whose interaction is hard to predict. Power
users lose direct control; if that proves to matter, the raw parameters can be
added without changing the cache design, since variance is already in the key.

## Voices are read from the live catalog

**Context.** Voices could be repackaged into archives the add-on hosts, or
read straight from the upstream catalog.

**Decision.** Parse `voices.json` from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) and
download models directly, verifying the md5 the catalog publishes.

**Consequences.** New upstream voices appear without an add-on update and
without maintainer effort. The cost is a dependency on that repository's
layout staying stable, and on the user having internet access for the first
download — which is why "Install from file" exists.

## Interoperating with other add-ons by layout, not by code

**Context.** Sonata Neural Voices and its maintained fork Dengjen store
ordinary Piper models on disk. Users switching over should not re-download
gigabytes.

**Decision.** Read their published directory layout
(`<NVDA config>/sonata/voices/piper/`, `<NVDA config>/dengjen/voices/piper/`)
and copy voices in. Accept the `.tar.gz` archives they distribute. Use no code
from either project.

**Consequences.** Switching is cheap and nothing is moved or deleted, so the
other add-on keeps working. The licensing position stays simple, and the
attribution in [../THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) can
state plainly that no code was reused. The cost is that a layout change
upstream breaks import, which fails visibly (nothing found) rather than
silently.

## Translation tooling is part of the repository

**Context.** NVDA add-ons translate through gettext, but `xgettext` and
`msgfmt` are not present on a typical Windows build machine, and requiring
them would put a barrier in front of translators and contributors.

**Decision.** Implement extraction and `.mo` compilation in `tools/i18n.py`,
about 250 lines with no dependencies, and test the round trip through Python's
own `gettext`.

**Consequences.** `python tools/build.py` is the only build step, on any
machine. A test fails if `nvda.pot` goes stale, so translators never work from
an out-of-date template. The cost is maintaining a small amount of format code;
the MO and PO formats are stable and well specified.

## User data lives in the NVDA configuration directory

**Decision.** Voices, cache, catalog, lexicon, and language assignments all
live under `<NVDA config>/piper/`, never inside the add-on directory.

**Consequences.** Updating or reinstalling the add-on never destroys a user's
downloaded voices or their pronunciation work, and uninstall can ask before
removing them. Files are plain JSON, so they can be backed up or shared.

## The Rust crate is not blanket-formatted

**Context.** `cargo fmt --check` reports differences in most files. Most are
deliberate: the warmup word list in `server.rs` is a dense table that rustfmt
would expand to one word per line, roughly 120 lines of noise.

**Decision.** Write new code in rustfmt style — new files are clean — but do
not run `cargo fmt` across the crate, and do not treat its output as a gate.

**Consequences.** Diffs stay small and reviewable, and hand-laid-out data
tables stay readable. The cost is that formatting is a matter of review rather
than a tool, which is only tolerable because the crate is small.
