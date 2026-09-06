//! Post-synthesis audio processing: silence trim, resampling, time-stretch,
//! pitch shift, volume, and PCM conversion. Samples are mono f32 in [-1, 1],
//! at the voice's native rate until `resample` converts them to the output
//! rate.

pub mod pitch;
pub mod trim;
pub mod wsola;

pub use pitch::pitch_shift;
pub use trim::{trim_leading_silence, trim_trailing_silence};
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

/// Half-width of the Lanczos window, in output samples. Three lobes is the
/// usual quality/cost compromise for audio.
const LANCZOS_A: f32 = 3.0;

fn sinc(x: f32) -> f32 {
    if x.abs() < 1e-6 {
        1.0
    } else {
        let pix = std::f32::consts::PI * x;
        pix.sin() / pix
    }
}

/// Windowed-sinc (Lanczos) resampler. `rate` > 1 shortens the signal.
///
/// Used for sample-rate conversion, where linear interpolation is audible:
/// 40 of the published voices are not at the output rate (39 at 16 kHz, one
/// at 44.1 kHz), and linear interpolation gives them imaging and aliasing
/// artefacts that sound like a slight harshness. The window widens when
/// downsampling so the filter also acts as the anti-alias filter.
pub fn resample(input: &[f32], rate: f32) -> Vec<f32> {
    if input.is_empty() || rate <= 0.0 {
        return Vec::new();
    }
    if (rate - 1.0).abs() < 1e-6 {
        return input.to_vec();
    }
    let out_len = ((input.len() as f32 / rate).floor() as usize).max(1);
    let scale = rate.max(1.0);
    let half = (LANCZOS_A * scale).ceil() as isize;
    let last = input.len() as isize - 1;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let center = i as f32 * rate;
        let nearest = center.round() as isize;
        let mut acc = 0.0;
        let mut norm = 0.0;
        for j in (nearest - half)..=(nearest + half) {
            let x = (j as f32 - center) / scale;
            if x.abs() >= LANCZOS_A {
                continue;
            }
            let weight = sinc(x) * sinc(x / LANCZOS_A);
            acc += input[j.clamp(0, last) as usize] * weight;
            norm += weight;
        }
        out.push(if norm.abs() > 1e-6 { acc / norm } else { 0.0 });
    }
    out
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
        assert_eq!(resample(&input, 2.0).len(), 500);
        assert_eq!(resample(&input, 0.5).len(), 2000);
    }

    /// A sine well below the Nyquist limit of both rates must survive
    /// resampling with its shape intact; this is what linear interpolation
    /// does badly.
    #[test]
    fn resample_preserves_a_low_tone() {
        let src_sr = 16000.0f32;
        let out_sr = 22050.0f32;
        let freq = 440.0f32;
        let input: Vec<f32> = (0..4000)
            .map(|i| (2.0 * std::f32::consts::PI * freq * i as f32 / src_sr).sin())
            .collect();
        let out = resample(&input, src_sr / out_sr);
        // Skip the edges, where the window is clamped.
        let start = 200;
        let end = out.len() - 200;
        let mut worst = 0.0f32;
        for (i, &got) in out[start..end].iter().enumerate() {
            let t = (start + i) as f32 / out_sr;
            let want = (2.0 * std::f32::consts::PI * freq * t).sin();
            worst = worst.max((got - want).abs());
        }
        assert!(worst < 0.05, "worst error {worst}");
    }

    #[test]
    fn resample_passes_through_at_unit_rate() {
        let input = vec![0.1, -0.2, 0.3];
        assert_eq!(resample(&input, 1.0), input);
    }
}
