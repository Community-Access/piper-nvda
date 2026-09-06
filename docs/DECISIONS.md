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

## A character is never silent

**Context.** espeak-ng returns no phonemes for a punctuation character sent on
its own: it reads it as clause punctuation and drops it. Twenty characters
behave that way, including the full stop, comma, brackets, quotes and the
space. Reading by character or typing one of them produced silence, which is
not a slow synthesizer but an unusable one.

**Decision.** Name the character instead, in two layers. The driver asks NVDA
for the name, because NVDA has one per locale and it is what other
synthesizers say. The helper keeps an English table behind that, so a
character that still arrives with no pronunciation is spoken rather than
dropped.

**Consequences.** Two mechanisms for one problem, which is one more than
ideal, but they fail in different directions: the driver's is correct in the
user's language and depends on an NVDA API, and the helper's is always
available and only English. Silence is the outcome neither of them allows.
Character-mode text also stopped being trimmed, since the character in
question may be a space.

## The symbol names come from NVDA's dictionary, not from intuition

**Context.** Reading by character and spelling a word are exactly where a
delay is felt, and punctuation is as common there as letters. Preparing a
symbol means preparing what the synthesizer will actually be asked to say,
which is not the symbol but the name NVDA gives it.

**Decision.** Take the names from NVDA's own English symbol dictionary
(`source/locale/en/symbols.dic`) rather than writing them by hand. Prepare the
symbol characters as well, the digits both as digits and as words, and the
number words.

**Consequences.** The prepared names are the ones NVDA really says: "bang" for
`!`, "graav" for a backtick, "semi" for `;`, "dot dot dot" for an ellipsis.
None of those are what a reasonable person would guess, and a guessed list
would have prepared audio that is never asked for. The cost is that the list
is English: a French voice spends idle time preparing English symbol names it
will never be asked for. Sending NVDA's current locale symbols from the driver
would fix that and is the obvious next step if it matters.

## Character mode is not part of the cache key

**Context.** The key once included NVDA's character-mode flag, on the
assumption that spelling a letter and speaking it are different sounds.

**Decision.** Drop it. Character mode decides how an utterance is split into
chunks, and the key is built per chunk, so by the time there is a key the
flag can no longer change the audio.

**Consequences.** A letter spelled and the same letter spoken share one entry,
which halved the cost of preparing symbols, and a symbol name prepared once
serves however NVDA chose to send it. The cache format version was raised so
that files keyed the old way are discarded rather than never matching.

## The prepared list is extensible, and the whole cache is optional

**Context.** The built-in warmup list is what every NVDA user hears: control
types, states, punctuation names, the alphabet. It cannot cover one person's
own vocabulary, and there was no way to see the cache, turn it off, or throw
it away.

**Decision.** Let the user add phrases, queued ahead of the built-in words
because they were asked for specifically. Add a setting that turns preparation
and reuse off entirely, and a rebuild action that discards everything and
prepares again.

**Decision detail: 40 characters.** A prepared phrase only pays off if it
reaches the synthesizer as one chunk, and the chunker splits the first clause
near 40 characters to get speech started sooner. Anything longer would be
prepared as text that is never asked for as a unit, so the dialog refuses it
and says why rather than silently wasting the work.

**Consequences.** Someone who hears "Unread message from" fifty times a day
can make it instant. Someone short of disk can turn the whole thing off and
still have working speech, just without instant echo. The cost is three more
protocol messages and one more file in the data directory.

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

**What removing it did not do.** The prebuilt ONNX Runtime that `ort`
downloads is a DirectML-enabled build, and `ort-sys`'s build script emits
`cargo:rustc-link-lib=DirectML`, `D3D12`, `DXGI`, and `DXCORE` unconditionally,
so `piper-helper.exe` still imports `DirectML.dll`, `d3d12.dll`, and
`dxgi.dll` at load time. The cargo feature only ever gated the Rust-side API.
`tools/pe_imports.py` is what makes this checkable.

Dropping those imports would mean `ort`'s `load-dynamic` feature and shipping
our own CPU-only `onnxruntime.dll`. That work is not being done: every one of
those libraries is part of Windows 11, which is the only version this add-on
supports, so the imports cost nothing. It is worth revisiting only if the
supported range ever widens downward.

## Windows 11 and later only

**Context.** NVDA itself supports Windows 10 and later. The add-on runs on
Windows 10 too: everything it links against has been part of Windows since
version 1903.

**Decision.** Support Windows 11 and later, and say so. Test there only.

**Consequences.** A narrower support surface than NVDA's, chosen so that
testing effort goes where the users are rather than into an older Windows
nobody has verified this on. Nothing blocks installation on Windows 10, since
it works and blocking would take away something that functions; the driver
logs a warning naming the Windows build when it starts on anything older than
Windows 11, so a report from an unsupported machine explains itself without
the user having to know.

## The Visual C++ runtime ships inside the add-on

**Context.** Both `piper-helper.exe` and `libespeak-ng.dll` link against
`msvcp140.dll` and `vcruntime140.dll`. Those are not part of Windows; they
come from the Visual C++ redistributable. On a machine that has never had it
installed the helper cannot start, and the failure is a bare missing-DLL
error that says nothing useful. The other Piper add-ons for NVDA document the
redistributable as a prerequisite the user must go and install.

**Decision.** Ship the four runtime DLLs beside `piper-helper.exe`, from the
Build Tools' redistributable directory, and fail the packaging step loudly if
they cannot be found.

**Consequences.** No prerequisites: installing the add-on is enough. The cost
is 768 KB and a build-machine requirement. One copy covers espeak-ng too,
because implicit imports resolve from the *executable's* directory rather than
from the directory of the DLL that needs them. Copies from `System32` are
deliberately not used, since a release should not depend on whatever happens
to be installed on the build machine; `PIPER_CRT_DIR` is the escape hatch.

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
