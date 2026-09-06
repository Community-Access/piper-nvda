# Piper vs Kokoro: performance comparison

Both addons share the same architecture (Rust helper + ONNX + espeak-ng, NVDA
Python driver, cache with idle warmup). The difference is the model. All
numbers measured on the same machine: AMD Ryzen 5 Surface Edition (Zen 2
mobile, 6 cores), CPU inference, plugged in.

## First-audio latency for NEW (uncached) text

| Case                | Kokoro (fp16) | Piper lessac-medium | Piper ryan-low |
|---------------------|---------------|---------------------|----------------|
| single char / word  | ~370-450 ms   | ~21-34 ms           | ~21 ms         |
| short line          | ~630 ms       | ~55-92 ms           | ~55 ms         |
| full sentence (total synth) | ~2.0-5.5 s (RTF ~1x) | ~200 ms (RTF ~17x) | ~134 ms (RTF ~22x) |

Piper is roughly 10x faster than Kokoro per inference on this CPU, and runs
comfortably faster than real time, so say-all of fresh text never falls
behind. Kokoro on this thermally limited chip hovers around real time.

## Cached text (character echo, common words, re-reads)

Both synths cache raw model output and warm the character set plus common
NVDA words in idle time, so:

| Case                          | Kokoro | Piper |
|-------------------------------|--------|-------|
| warmed char / word / re-read  | 0-13 ms (instant) | 0 ms (instant) |
| cancel-to-silence             | <1 ms  | <1 ms |

## Takeaway

- Kokoro sounds distinctive but is heavy; on a mid-range CPU it is usable
  mainly because of the cache, and new prose is slow.
- Piper is dramatically faster for new text while keeping the same instant
  cached echo, and offers far more voices and languages. For raw
  responsiveness on CPU, Piper wins clearly.
- Both beat the abandoned Sonata/Piper addon on responsiveness because of the
  audio cache and idle warmup, which those addons do not have.

## Extra Piper capabilities

- In-app voice browser (Tools menu) listing the full HuggingFace piper-voices
  catalog (~176 voices, dozens of languages, multiple quality tiers).
- Direct download of any voice with md5 verification and resume.
- Hear a demo of any voice BEFORE downloading, played through NVDA's audio via
  a private helper (works regardless of the active synthesizer).
- Multi-speaker voices exposed through the Variant setting.
