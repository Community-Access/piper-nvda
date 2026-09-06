# What this add-on is

A product description: who it is for, what it promises, what it deliberately
does not do, and how to tell whether it is working. The technical companions
are [ARCHITECTURE.md](ARCHITECTURE.md) for how it is built and
[DECISIONS.md](DECISIONS.md) for why.

## The problem

NVDA users who want a natural-sounding voice have had to choose between two
unhappy options. The classic synthesizers (eSpeak, SAPI voices) are instant
but robotic. Neural voices sound human but are slow, and slowness in a screen
reader is not a minor irritation: every character you type, every item you
arrow past, every state change is a separate utterance. A synthesizer that
takes 400 ms to start speaking makes a computer feel broken, however good it
sounds once it starts.

Piper's voices are small and fast enough to close that gap. The existing
Piper add-ons for NVDA proved the idea and then stopped being maintained or
stopped short of the responsiveness a daily driver needs.

## Who it is for

- Someone who uses NVDA all day and wants a voice they can stand to listen to
  for eight hours.
- Someone who reads fast, and needs speech that keeps up rather than one that
  merely sounds nice at 150 words per minute.
- Someone whose language has a Piper voice but no good commercial one.
- Someone switching from Sonata or Dengjen who does not want to re-download
  gigabytes of models.

It is not aimed at people producing audio files, or at developers wanting a
TTS library. Both are better served by Piper directly.

## What it promises

1. **Instant echo.** Typing, spelling, and moving through menus and lists
   speak with no perceptible delay, at any rate, because that audio was
   prepared during idle time or has been heard before. This is the promise
   the whole design serves.
2. **Fast new text.** A sentence you have never heard starts speaking in a
   fraction of a second on an ordinary CPU.
3. **Nothing leaves the machine.** Voices download once; after that there is
   no network traffic, no account, and no telemetry.
4. **It cannot take NVDA down.** Inference runs in a separate process. A fault
   in a model costs a restart of that process, not of the screen reader.
5. **It is fixable.** A word pronounced wrongly can be corrected by the user,
   permanently, in every voice.
6. **It is configurable without being a maze.** One control by default where
   one will do, and the raw parameters behind a switch for people who want
   them.

## What it deliberately does not do

- **It does not bundle voices.** They are downloaded on demand, which keeps
  the add-on small and lets new upstream voices appear without an update.
- **It does not use the GPU.** Measured, DirectML was six times slower than
  the CPU for a single character, which is the case that matters here.
- **It does not support voices needing a phonemizer it lacks.** Six published
  voices are refused with an explanation rather than spoken as fluent
  nonsense.
- **It does not support Windows 10.** It very likely runs there; it is not
  tested there.
- **It does not replace NVDA's own features.** Speech dictionaries, symbol
  levels, and configuration profiles stay NVDA's job. The pronunciation
  lexicon works at the phoneme level precisely because NVDA's dictionaries
  work at the text level.

## How to tell whether it is working

These are the numbers the design is accountable to, measured on a mid-range
laptop with a medium-quality voice. [COMPARISON.md](../COMPARISON.md) keeps
the details current.

| Behaviour | Target |
|-----------|--------|
| Character echo, common words, anything re-read | No perceptible delay |
| A new short line | Under 100 ms to first audio |
| A new sentence | Faster than real time, so say-all never falls behind |
| Interrupting speech | Effectively instant |
| A character or symbol read or typed | Always spoken; never silence |
| First run with no voices | Working speech in one confirmation |

## The competition, honestly

[Sonata Neural Voices](https://github.com/mush42/sonata-nvda) brought Piper to
NVDA first, and its maintained fork
[Dengjen](https://github.com/OnjLouis/dengjen-nvda) keeps it working. They are
the reason this add-on can assume users already know what a Piper voice is.

Where this add-on is ahead: the audio cache and idle preparation, rate as a
post-cache time-stretch, the live voice catalogue, the pronunciation lexicon,
per-language and per-voice settings, and needing no prerequisites. Where it is
behind: they have years of use and many translations; this has neither yet.
See [COMPARISON.md](../COMPARISON.md), which separates what was measured from
what was reasoned.

## What would make this better

In rough order of value:

1. **Translations.** The pipeline and template exist and no language has been
   done. A screen reader add-on with no translations reaches a fraction of
   its potential users.
2. **A manual accessibility pass** over the eight dialogs, inside NVDA, by
   someone using a screen reader.
3. **Add-on Store submission.** This should come before translations rather
   than after: translators arrive from the pool of users, and there are none
   yet.
4. **Signing the helper binary.** Lower than it first appeared: NVDA add-ons
   are unsigned as a rule, the helper is launched by NVDA rather than from
   Explorer, and the store's own VirusTotal step is the real gate on native
   binaries. Worth revisiting only if someone reports a SmartScreen problem.
