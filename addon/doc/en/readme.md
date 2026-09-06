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
- Use GPU acceleration (DirectML): optional; falls back to CPU.

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
