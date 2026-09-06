# Architecture

This document explains how the Piper add-on is put together and why. It is
the map to read before changing the code.

## Two processes

The add-on is split into an NVDA-side driver (Python) and a separate
inference helper (a native executable). They talk over a small binary
protocol on the helper's standard input and output.

```
NVDA process (32- or 64-bit Python)        piper-helper.exe (always x64)
-----------------------------------        ------------------------------
synthDrivers/piper/__init__.py             espeak-ng phonemization
  SynthDriver: settings, speech commands   ONNX Runtime (VITS inference)
  builds a SPEAK job  ------------------->  per-voice model, resampled to 22050 Hz
  nvwave.WavePlayer   <------------------   PCM audio frames + index markers
  fires index/done notifications           audio cache + idle warmup
```

### Why a separate process

- **Crash isolation.** If a model or the runtime faults, only the helper
  dies. The driver detects the closed pipe, restarts the helper, and NVDA
  keeps talking. In-process inference would take the whole screen reader down.
- **Bitness.** NVDA 2025.x is a 32-bit process; ONNX Runtime ships 64-bit
  binaries. A 64-bit helper works for both 32-bit NVDA and 64-bit NVDA
  (2026.1+) with one build. The driver contains no native code.
- **The cost is negligible.** The inter-process round trip is about 0.06 ms
  (measured); the audio stream is a one-way bulk transfer that overlaps
  playback. Neither is on the critical path next to inference.

## The NVDA-side driver

Package `addon/synthDrivers/piper/`.

- `__init__.py` - the `SynthDriver`. Declares supported settings (voice,
  variant/speaker, rate, rate boost, pitch, volume, expressiveness), the set of
  speech commands it honors, and the notifications it fires. Its main job is
  `_build_job`, which turns an NVDA speech sequence (text interleaved with
  command objects) into a single SPEAK job of segments. Each segment records
  which voice model to use, the speaker id, and the prosody for that span.
- `_helperProc.py` - starts and supervises `piper-helper.exe`. A reader thread
  dispatches inbound frames; a ping watchdog detects a hung helper; a crash
  triggers a restart with backoff.
- `_audio.py` - the audio pump. It receives AUDIO, MARKER, and DONE frames and
  feeds PCM into `nvwave.WavePlayer`. Markers are turned into
  `synthIndexReached` notifications that fire exactly when the audio before
  them has played, which is what keeps say-all, braille tethering, and
  spelling in sync. DONE fires `synthDoneSpeaking`.
- `_catalog.py` - parses the HuggingFace `voices.json` index into Voice
  records and builds the download and demo-sample URLs.
- `_voices.py` - the installed-voice list for the driver, cross-referencing
  installed files against the catalog (or each voice's local config).
- `_download.py` - resumable, md5-verified downloading of a voice's model and
  config.
- `_manager_ui.py` - the voice browser dialog and a private `DemoPlayer` that
  can play demos through its own helper regardless of the active synth.
- `_protocol.py` - framing and message constants shared by the driver and the
  tests.
- `_paths.py` - all filesystem locations.

`addon/globalPlugins/piperManager/` adds the Tools-menu entry that opens the
voice manager.

## The helper

Rust crate in `helper/`, built as `piper-helper.exe`.

- `main.rs` - argument parsing and three modes: the stdio server (default),
  `--say` (write a WAV), and `--bench` (print timings).
- `server.rs` - the server loop. One worker thread does all synthesis so
  espeak-ng (which is not thread safe) is only ever touched from one place.
  A single work queue holds speech jobs, demo-playback jobs, and idle warmup
  tasks; real work always preempts warmup. A cancel bumps an atomic
  generation counter that the worker checks between segments and chunks, so
  stale audio is dropped immediately.
- `config.rs` - parses a voice's `.onnx.json` (sample rate, espeak voice,
  inference scales, `phoneme_id_map`, speaker count) and builds the model
  input id sequence using Piper's `interspersePad` convention
  (BOS, PAD, phoneme, PAD, ..., EOS).
- `synth.rs` - the inference engine. It keeps a small LRU of loaded voice
  models (each Piper voice is a separate ONNX file), assembles the VITS
  inputs (`input`, `input_lengths`, `scales`, optional `sid`), runs the
  session, and returns raw samples plus the model's native sample rate.
- `espeak.rs` - loads `libespeak-ng.dll` at runtime and converts text to IPA
  phonemes.
- `dsp/` - leading-silence trim, WSOLA time-stretch (for rate), pitch shift,
  volume, float-to-int16, and linear resampling (used to bring every voice to
  the fixed 22050 Hz output rate).
- `cache.rs` - the audio cache (see below).
- `mp3.rs` - decodes demo sample mp3 files for playback.
- `text.rs` - splits text into clause-sized chunks and keeps the first chunk
  short so streaming starts quickly.
- `protocol.rs` - the wire format.

## The audio cache

Synthesizing the same short text repeatedly is wasteful, and for a screen
reader the same characters and words are spoken constantly. The helper keeps
an LRU cache of raw model output, keyed on the voice model, character-mode
flag, the inference-parameter multipliers, lexicon revision, and text, but
**not** on pitch,
volume, or rate. Pitch and volume are applied as cheap DSP after the cache,
and rate is applied entirely as post-cache time-stretch (the model always runs
at its default speed). Because rate is not in the key, one cached entry is
reused at every speech rate.

The inputs that do change model output are in the key for correctness, and
scoped so they cost as little cache as possible. The inference parameters are
settings the user rarely moves, and moving one re-warms in the background. The
lexicon revision is folded in only for chunks that actually contain an
overridden word, so adding one pronunciation entry invalidates the handful of
chunks that use it rather than the whole cache.

On startup and voice change the driver sends a LOAD_VOICE message. The helper
then warms the alphabet and a curated list of common NVDA words for that voice
during idle time only, yielding to any real speech. The cache is persisted to
disk, so after the first session character echo and common announcements are
instant immediately.

## The pronunciation lexicon

Piper voices are driven by phonemes, and the phonemes come from espeak-ng,
which mispronounces names, acronyms, and loan words often enough to matter.
Retraining a voice is not an option for a user, so the helper accepts a word
to IPA map (`lexicon.rs`).

Before a chunk is phonemized it is split into runs: overridden words become
their IPA verbatim, and everything between them still goes through espeak-ng.
The results are joined with spaces, which is how espeak already separates
words in its own output, so prosody around the substitution is unaffected.
The driver owns the file (`lexicon.json`) and pushes the whole map to the
helper on connect, on helper restart, and whenever the user saves an edit.

## Per-language voices

Automatic language switching picks a voice for the language NVDA announces.
`language_voices.json` maps a language to an explicit voice key, which the
driver consults before falling back to the first installed voice for that
language. Lookups fall back from `pt_br` to `pt`, and an assignment naming a
voice that is no longer installed is ignored rather than failing to speak.

## Rate, pitch, and volume

- **Rate**: NVDA rate 0-100 maps to a WSOLA time-stretch factor (about 0.6x at
  0, natural at 50, 2.0x at 100), multiplied further by rate boost. The model
  is not asked to change speed, which keeps the cache rate-independent.
- **Pitch**: NVDA pitch 0-100 maps to plus or minus four semitones, applied by
  the DSP pitch shifter. This is also what makes NVDA's capital-letter pitch
  change work.
- **Volume**: scales the PCM.
- **Expressiveness / advanced parameters**: the only prosody controls that
  have to run through the model, so all of them are in the cache key. In
  simple mode one Expressiveness setting maps 0-100 onto a 0.4x-1.6x
  multiplier applied to the voice's trained `noise_scale` and `noise_w`, and
  `length_scale` is left alone. In advanced mode each of the three is set
  directly as a percentage of the trained value (50 = 1.0x, 100 = 2.0x). The
  driver sends multipliers rather than absolute numbers so that one setting
  means the same thing across voices trained with different values.
  `supportedSettings` is computed per instance, which is how the advanced
  parameters replace the simple control.

## Sample rate

Piper voices ship at different native sample rates (commonly 16000 or 22050
Hz). The helper resamples every voice to a single 22050 Hz output so the
NVDA-side `WavePlayer` can be created once and never has to change.
