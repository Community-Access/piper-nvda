# Driver-to-helper protocol (v1)

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
| 0x04  | LOAD_VOICE   | `{voice}` - voice = absolute model path; triggers idle warmup |
| 0x05  | PING         | `{}` |
| 0x06  | SHUTDOWN     | `{}` |
| 0x07  | PLAY_SAMPLE  | `{path}` - decode and play an mp3 demo |

Helper to driver:

| Value | Name   | Payload |
|-------|--------|---------|
| 0x81  | AUDIO  | binary: header length (u16 LE), JSON `{utteranceId, seq}`, raw i16 LE PCM |
| 0x82  | MARKER | `{utteranceId, index}` - emitted in-stream at an index position |
| 0x83  | DONE   | `{utteranceId}` |
| 0x84  | ERROR  | `{code, message}` |
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
      "charMode": false
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
