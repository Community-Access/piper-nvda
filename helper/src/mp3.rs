//! Minimal mp3 decoding for playing voice demo samples. Returns mono f32
//! samples plus the source sample rate.

use anyhow::{Context, Result};
use std::path::Path;

pub fn decode_file(path: &Path) -> Result<(Vec<f32>, u32)> {
    let file = std::fs::File::open(path)
        .with_context(|| format!("opening sample {}", path.display()))?;
    let mut decoder = minimp3::Decoder::new(file);
    let mut samples: Vec<f32> = Vec::new();
    let mut sample_rate = 22050u32;
    loop {
        match decoder.next_frame() {
            Ok(frame) => {
                sample_rate = frame.sample_rate as u32;
                let ch = frame.channels.max(1);
                if ch == 1 {
                    samples.extend(frame.data.iter().map(|&s| s as f32 / 32768.0));
                } else {
                    // Downmix interleaved channels to mono.
                    for chunk in frame.data.chunks(ch) {
                        let sum: i32 = chunk.iter().map(|&s| s as i32).sum();
                        samples.push(sum as f32 / (ch as f32 * 32768.0));
                    }
                }
            }
            Err(minimp3::Error::Eof) => break,
            Err(e) => return Err(anyhow::anyhow!("mp3 decode: {e}")),
        }
    }
    Ok((samples, sample_rate))
}
