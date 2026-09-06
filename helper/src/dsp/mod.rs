//! Post-synthesis audio processing: silence trim, time-stretch, pitch shift,
//! volume, and PCM conversion. All samples are mono f32 in [-1, 1] at 24 kHz.

pub mod pitch;
pub mod trim;
pub mod wsola;

pub use pitch::pitch_shift;
pub use trim::trim_leading_silence;
pub use wsola::stretch;

/// Convert to interleaved i16 with a volume multiplier and hard clip.
pub fn to_i16(samples: &[f32], volume: f32) -> Vec<i16> {
    samples
        .iter()
        .map(|&s| {
            let v = (s * volume).clamp(-1.0, 1.0);
            (v * 32767.0) as i16
        })
        .collect()
}

/// Linear-interpolation resampler used by the pitch shifter. `rate` > 1
/// shortens the signal (reads faster).
pub fn linear_resample(input: &[f32], rate: f32) -> Vec<f32> {
    if input.is_empty() || rate <= 0.0 {
        return Vec::new();
    }
    let out_len = ((input.len() as f32 / rate).floor() as usize).max(1);
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let pos = i as f32 * rate;
        let idx = pos as usize;
        let frac = pos - idx as f32;
        let a = input[idx.min(input.len() - 1)];
        let b = input[(idx + 1).min(input.len() - 1)];
        out.push(a + (b - a) * frac);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn to_i16_clips_and_scales() {
        let pcm = to_i16(&[0.0, 1.0, -1.0, 2.0], 1.0);
        assert_eq!(pcm, vec![0, 32767, -32767, 32767]);
        let quiet = to_i16(&[1.0], 0.5);
        assert_eq!(quiet, vec![16383]);
    }

    #[test]
    fn resample_lengths() {
        let input = vec![0.0f32; 1000];
        assert_eq!(linear_resample(&input, 2.0).len(), 500);
        assert_eq!(linear_resample(&input, 0.5).len(), 2000);
    }
}
