//! Pitch shifting by resample-plus-time-stretch. Duration is preserved.

use super::{linear_resample, wsola};

pub fn pitch_shift(input: &[f32], semitones: f32) -> Vec<f32> {
    if semitones.abs() < 0.05 || input.is_empty() {
        return input.to_vec();
    }
    let semitones = semitones.clamp(-12.0, 12.0);
    let rate = 2f32.powf(semitones / 12.0);
    // Reading faster raises pitch and shortens; stretch restores duration.
    let resampled = linear_resample(input, rate);
    wsola::stretch(&resampled, 1.0 / rate)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(len: usize, freq: f32) -> Vec<f32> {
        (0..len)
            .map(|i| (i as f32 * freq * std::f32::consts::TAU / 24000.0).sin() * 0.5)
            .collect()
    }

    /// Estimate dominant frequency by counting zero crossings.
    fn zero_cross_freq(s: &[f32]) -> f32 {
        let crossings = s.windows(2).filter(|w| w[0] < 0.0 && w[1] >= 0.0).count();
        crossings as f32 * 24000.0 / s.len() as f32
    }

    #[test]
    fn keeps_duration() {
        let input = tone(24000, 220.0);
        let out = pitch_shift(&input, 4.0);
        let ratio = out.len() as f32 / input.len() as f32;
        assert!((ratio - 1.0).abs() < 0.05, "ratio {ratio}");
    }

    #[test]
    fn raises_pitch_one_octave() {
        let input = tone(24000, 220.0);
        let out = pitch_shift(&input, 12.0);
        let f = zero_cross_freq(&out);
        assert!((f - 440.0).abs() < 30.0, "freq {f}");
    }

    #[test]
    fn lowers_pitch() {
        let input = tone(24000, 440.0);
        let out = pitch_shift(&input, -12.0);
        let f = zero_cross_freq(&out);
        assert!((f - 220.0).abs() < 30.0, "freq {f}");
    }

    #[test]
    fn zero_shift_is_identity() {
        let input = tone(1000, 220.0);
        assert_eq!(pitch_shift(&input, 0.0), input);
    }
}
