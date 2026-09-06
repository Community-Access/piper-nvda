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
character-mode, the inference-parameter multipliers, lexicon revision, and
text — but not on pitch, volume, or rate. Warm the alphabet and a curated list of common NVDA
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

## One control by default, the raw parameters behind advanced mode

**Context.** Piper voices carry `noise_scale`, `noise_w`, and `length_scale`.
Other add-ons expose all three directly, which is precise but asks every user
to understand three interacting numbers.

**Decision.** Default to a single Expressiveness setting that scales
`noise_scale` and `noise_w` together (0.4x to 1.6x, 50 = as trained), and put
the three raw parameters behind a "Show advanced voice parameters" toggle that
replaces it. `supportedSettings` is computed per instance rather than fixed on
the class, which is what lets the two sets swap.

**Decision detail: percentages, not absolute values.** Voices are trained with
different values, so an absolute `noise_scale` of 0.667 means something
different from voice to voice. Each advanced control is a percentage of the
voice's own trained value, with 50 meaning "as trained". The advanced defaults
are therefore identical to Expressiveness at 50, so toggling the mode without
changing anything cannot change how a voice sounds.

**Consequences.** A non-technical user turns one dial; a user coming from
another Piper tool gets the parameters they already know, under the names they
already know. The cost is that NVDA builds settings controls when the panel
opens, so toggling the mode needs the Speech settings dialog reopened; the
driver attempts a live refresh first and says so when it cannot.

`length_scale` deserves its own warning in the user guide: it looks like a
rate control and is not one. Rate is a post-cache time-stretch and is free;
`length_scale` changes model output and re-warms the cache.

## Voices we cannot phonemize are refused, not approximated

**Context.** A voice config declares `phoneme_type`. Six of the 176 published
voices name a phonemizer this add-on does not bundle: two Chinese voices want
pinyin, and there is one each for Hebrew, Japanese, and Thai. A model trained
on those symbols still runs happily on espeak's IPA and still produces fluent
speech; the speech is simply wrong.

**Decision.** Read `phoneme_type` and refuse. The configuration is downloaded
before the model, so an unusable voice costs a few kilobytes rather than tens
of megabytes; already-installed ones are left out of the voice list; and the
helper reports `unsupportedVoice` and stays silent if one reaches it anyway.
Reading the type does not load the model.

**Consequences.** A user gets an explanation instead of nonsense, and other
voices in the same languages still work. The cost is that adding one of those
phonemizers later is the only way to support those six voices; nothing here
gets us closer to it. `text` voices, whose phonemes are their own code points,
need no phonemizer and are supported directly.

## Gaps between clauses are inserted, not inherited

**Context.** Every model run carries 20-80 ms of near-silence at each end.
Speaking clause by clause, as streaming requires, meant every clause boundary
got two of those, so the rhythm of a sentence depended on how much silence the
model happened to generate at each join.

**Decision.** Trim both ends of every chunk before caching, then insert a
pause chosen from the punctuation the chunk ends with: the user's sentence
pause for `.`, `!`, `?`, and two fifths of it for `,`, `;`, `:`. Divide by the
rate stretch so pauses shrink as speech speeds up, and hold a pause over to
emit before the next chunk so an utterance never ends on silence.

**Consequences.** Rhythm is consistent and adjustable, cached entries are
smaller, and the old "trim the first chunk only" special case is gone. This
also replaces the espeak clause-terminator API we cannot use: the bundled
espeak-ng exports `espeak_TextToPhonemes` but not the newer variant that
reports which punctuation ended a clause, and the chunker already knows,
because it keeps punctuation attached to its clause.

## Sample-rate conversion uses a windowed sinc

**Context.** 40 of the 176 published voices are not at the 22050 Hz output
rate (39 at 16 kHz, one at 44.1 kHz). Linear interpolation was cheap but its
imaging and aliasing are audible on exactly those voices, as a slight
harshness.

**Decision.** Use a Lanczos-3 windowed-sinc resampler for sample-rate
conversion, widening the window when downsampling so the same filter
anti-aliases. Keep linear interpolation inside the pitch shifter, where the
read rate varies continuously and the quality difference does not justify the
cost.

**Consequences.** The 16 kHz voices, which are the fast ones people choose on
slower machines, stop sounding worse than they need to. The cost is roughly
seven multiply-adds per output sample on those voices only; voices already at
the output rate skip resampling entirely.

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
