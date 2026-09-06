# Piper Neural Voices for NVDA

Fast neural text-to-speech for NVDA using the Piper voices. Runs fully
offline. Inference happens in a bundled 64-bit helper process, so it works on
both 32-bit NVDA (2025.x) and 64-bit NVDA (2026.1+), and a crash in the model
can never take down NVDA.

## First use

1. Open NVDA menu, Tools, "Piper voice manager".
2. Pick a language, select a voice, and press "Play demo" to hear it before
   downloading.
3. Press "Download" to install the voice.
4. Open NVDA menu, Preferences, Settings, Speech and choose "Piper Neural
   Voices" as the synthesizer, then pick your downloaded voice.

The voice manager can be reopened any time from the Tools menu to add or
remove voices.

## Settings

- Voice: any installed Piper voice, across all downloaded languages.
- Variant: for multi-speaker voices, selects the speaker.
- Rate and Rate boost: rate boost extends the top speed for fast-speech users
  by time-stretching without changing pitch.
- Pitch and Volume.
- Expressiveness: how much the voice varies its delivery. 50 is the voice as
  trained; lower is flatter and steadier, higher is more animated.

## Performance

Piper is very fast: on a mid-range CPU a phrase begins in a fraction of the
time a heavier neural model needs, and cancel is effectively instant.
Character echo and common navigation words are additionally cached and
warmed, so typing and navigation speak with no perceptible delay, at any
rate. The cache is saved between sessions.

## Voices

Voices come from the Piper voices project and cover dozens of languages at
several quality levels (x_low, low, medium, high). Downloaded voices are
stored in your NVDA user configuration folder, so they survive addon updates.

The voice manager can also reuse voices you already have. "Import voices"
finds voices installed by the Sonata and Dengjen add-ons and copies them in,
and "Install from file" installs a voice from a .tar.gz archive or a .onnx
model with its .onnx.json beside it, for computers with no internet access.

## Pronunciations

Voices take their phonemes from espeak-ng, which regularly mispronounces
names, acronyms, and loan words. "Pronunciations" in the voice manager gives a
word the exact IPA phonemes it should be spoken with, with a Preview button to
hear the entry before saving it. Entries match whole words, ignore
capitalization, and apply to every voice.

## Language voices

With several voices for one language, "Language voices" in the voice manager
says which one automatic language switching should use.
