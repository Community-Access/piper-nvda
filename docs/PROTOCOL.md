# Driver-to-helper protocol (v2)

The NVDA driver and `piper-helper.exe` communicate over the helper's standard
input (driver to helper) and standard output (helper to driver). Standard
error carries nothing the protocol depends on. The format is deliberately
tiny and has no external dependencies on either side.

## Framing

Every message is one frame:

```
+--------------------+--------+-------------------------+
| length (u32 LE)    | type   | payload                 |
| = 1 + payload size | (u8)   | (length - 1 bytes)      |
+--------------------+--------+-------------------------+
```

- `length` is little-endian and counts the type byte plus the payload.
- A frame larger than 32 MiB is rejected, so a corrupt length cannot cause a
  huge allocation.
- Control payloads are UTF-8 JSON. The audio payload is binary (below).

## Message types

Driver to helper:

| Value | Name         | Payload |
|-------|--------------|---------|
| 0x01  | HELLO        | `{version, role, modelLoaded}` (handshake) |
| 0x02  | SPEAK        | a Speak job (below) |
| 0x03  | CANCEL       | `{}` - drop all queued and in-flight work |
| 0x04  | LOAD_VOICE   | `{voice, scales}` - voice = absolute model path; triggers idle warmup at those scales |
| 0x05  | PING         | `{}` |
| 0x06  | SHUTDOWN     | `{}` |
| 0x07  | PLAY_SAMPLE  | `{path}` - decode and play an mp3 demo |
| 0x08  | SET_LEXICON  | `{rev, entries}` - replace the pronunciation lexicon |

Helper to driver:

| Value | Name   | Payload |
|-------|--------|---------|
| 0x81  | AUDIO  | binary: header length (u16 LE), JSON `{utteranceId, seq}`, raw i16 LE PCM |
| 0x82  | MARKER | `{utteranceId, index}` - emitted in-stream at an index position |
| 0x83  | DONE   | `{utteranceId}` |
| 0x84  | ERROR  | `{code, message}`; `code` is `unsupportedVoice` when the voice needs a phonemizer the helper does not include |
| 0x85  | PONG   | `{}` |
| 0x86  | LOG    | `{level, message}` |

## The Speak job

```json
{
  "utteranceId": 42,
  "segments": [
    {
      "text": "Hello world",
      "modelPath": "C:/Users/.../piper/voices/en_US-lessac-medium.onnx",
      "sid": 0,
      "stretch": 1.0,
      "pitchSemis": 0.0,
      "volume": 0.9,
      "breakMsBefore": 0,
      "indexesBefore": [7],
      "charMode": false,
      "scales": {"noiseScale": 1.0, "lengthScale": 1.0, "noiseW": 1.0},
      "ipa": false,
      "fallbackText": "",
      "sentencePauseMs": 100
    }
  ],
  "indexesAfter": [8]
}
```

- `modelPath` names the voice; the helper reads the sibling `.onnx.json` for
  the espeak language, sample rate, and phoneme map (loading is cached).
- `sid` is the speaker id for multi-speaker voices (0 otherwise).
- `stretch` carries the entire rate setting as a time-stretch factor
  (`> 1` faster). The model always runs at its default speed.
- `pitchSemis` and `volume` are applied as DSP after the audio cache, so they
  never reduce the cache hit rate.
- `breakMsBefore` inserts that many milliseconds of silence before the
  segment.
- `indexesBefore` are index values whose markers must fire once the audio up
  to this segment has played. `indexesAfter` fire after the whole utterance.
- `charMode` true means "spell": the text is spoken as a single unit
  (letter/character), not split into clauses.
- `scales` multiplies the voice's trained inference parameters (1.0 = as
  trained, and any omitted field defaults to 1.0). Unlike the other prosody
  fields these change model output, so they are part of the cache key. Note
  that `lengthScale` is not the rate setting: rate is carried entirely by
  `stretch`.
- `ipa` true means `text` is already phonemes and must not be phonemized,
  which is how NVDA's PhonemeCommand is carried. Such a segment is never
  split into clauses and never has lexicon overrides applied to it.
- `fallbackText` is spoken instead when an `ipa` segment produced no phonemes
  the voice knows, so an unknown phoneme degrades to the word rather than to
  silence.
- `sentencePauseMs` is the silence inserted after a sentence, before the rate
  stretch is applied; clause endings get two fifths of it. It is not part of
  the cache key, because the pause goes between cached chunks rather than
  inside one.

## The lexicon

SET_LEXICON replaces the helper's pronunciation lexicon wholesale:

```json
{"rev": 3, "entries": {"nvda": "ɛnviːdiːˈeɪ"}}
```

- Keys are whole words, already lowercased by the driver; matching is
  case-insensitive and never matches inside a longer word.
- Values are IPA phonemes, used verbatim in place of what espeak-ng would
  have produced for that word. The text around an overridden word is still
  phonemized normally and the results are joined.
- `rev` increases on every user edit. It is folded into the cache key of
  chunks that contain an override, and only those, so editing the lexicon
  does not throw away the rest of the warmed cache.
- The message is applied ahead of any queued speech, and is not dropped by a
  CANCEL, so an edit takes effect on the next utterance.

## Semantics and guarantees

- **Ordering.** Speak jobs are processed first-in first-out on one worker
  thread. A single utterance's AUDIO frames arrive in `seq` order, with MARKER
  frames interleaved at their exact positions.
- **Cancel.** CANCEL increments a generation counter and clears the queue. The
  worker checks the counter between segments and between audio chunks, so no
  stale AUDIO, MARKER, or DONE for a cancelled utterance is emitted after the
  cancel point. Playback stops on the driver side immediately.
- **Done always fires.** A non-cancelled utterance always ends with a DONE,
  even if it produced no audio (for example, whitespace-only text). Any
  `indexesBefore`/`indexesAfter` still fire. This is what prevents say-all
  from stalling.
- **Notifications may cross threads.** The helper emits from its worker thread;
  the driver marshals index/done notifications onto NVDA's main thread.

## Versioning

Both sides send HELLO with a protocol version on startup. The helper's HELLO
also reports `modelLoaded`. A version mismatch is a hard error surfaced in the
log; bump `PROTOCOL_VERSION` on any incompatible change and update both the
Rust (`protocol.rs`) and Python (`_protocol.py`) sides together.
