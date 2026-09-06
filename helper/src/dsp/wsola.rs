//! Waveform-similarity overlap-add time stretching.
//!
//! Changes duration without changing pitch. `speed` > 1 shortens (faster
//! speech), `speed` < 1 lengthens. Quality target is speech at rate-boost
//! factors up to about 3x, which simple correlation-guided OLA handles well.

/// Synthesis hop: 10 ms at 24 kHz.
const HOP: usize = 240;
/// Analysis window: 20 ms.
const WIN: usize = 480;
/// Correlation search radius: 5 ms.
const SEARCH: usize = 120;

pub fn stretch(input: &[f32], speed: f32) -> Vec<f32> {
    if input.is_empty() {
        return Vec::new();
    }
    if (speed - 1.0).abs() < 0.01 {
        return input.to_vec();
    }
    let speed = speed.clamp(0.25, 4.0);
    if input.len() < WIN + SEARCH + 1 {
        // Too short to stretch well; approximate with resampling-free copy.
        return input.to_vec();
    }
    let out_len_target = (input.len() as f32 / speed) as usize;
    let mut out: Vec<f32> = Vec::with_capacity(out_len_target + WIN);
    out.extend_from_slice(&input[..WIN]);

    let overlap = WIN - HOP;
    let mut k: usize = 1;
    loop {
        let out_pos = k * HOP; // where the new window's start overlaps `out`
        if out_pos + WIN >= out_len_target + WIN {
            break;
        }
        // Natural analysis position for this synthesis frame.
        let ideal = (out_pos as f32 * speed) as usize;
        if ideal + WIN + SEARCH >= input.len() {
            break;
        }
        let lo = ideal.saturating_sub(SEARCH);
        let hi = (ideal + SEARCH).min(input.len() - WIN - 1);
        // The tail of `out` that the new frame will overlap.
        let tail_start = out.len() - overlap;
        let tail: &[f32] = &out[tail_start..];
        let mut best = lo;
        let mut best_score = f32::MIN;
        let mut pos = lo;
        while pos <= hi {
            let cand = &input[pos..pos + overlap];
            let mut score = 0.0f32;
            // Correlate at 1/4 resolution: plenty for speech, 4x cheaper.
            let mut i = 0;
            while i < overlap {
                score += tail[i] * cand[i];
                i += 4;
            }
            if score > best_score {
                best_score = score;
                best = pos;
            }
            pos += 4;
        }
        // Cross-fade `overlap` samples, then append the rest of the window.
        let frame = &input[best..best + WIN];
        for i in 0..overlap {
            let t = i as f32 / overlap as f32;
            out[tail_start + i] = out[tail_start + i] * (1.0 - t) + frame[i] * t;
        }
        out.extend_from_slice(&frame[overlap..]);
        k += 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(len: usize, freq: f32) -> Vec<f32> {
        (0..len)
            .map(|i| (i as f32 * freq * std::f32::consts::TAU / 24000.0).sin() * 0.5)
            .collect()
    }

    #[test]
    fn shortens_at_double_speed() {
        let input = tone(24000, 220.0);
        let out = stretch(&input, 2.0);
        let ratio = out.len() as f32 / input.len() as f32;
        assert!((ratio - 0.5).abs() < 0.05, "ratio {ratio}");
    }

    #[test]
    fn lengthens_at_half_speed() {
        let input = tone(24000, 220.0);
        let out = stretch(&input, 0.5);
        let ratio = out.len() as f32 / input.len() as f32;
        assert!((ratio - 2.0).abs() < 0.1, "ratio {ratio}");
    }

    #[test]
    fn preserves_energy_roughly() {
        let input = tone(24000, 220.0);
        let out = stretch(&input, 1.5);
        let rms = |s: &[f32]| (s.iter().map(|x| x * x).sum::<f32>() / s.len() as f32).sqrt();
        let (ri, ro) = (rms(&input), rms(&out));
        assert!((ri - ro).abs() / ri < 0.25, "rms in {ri} out {ro}");
    }

    #[test]
    fn passthrough_near_unity() {
        let input = tone(4800, 220.0);
        assert_eq!(stretch(&input, 1.0).len(), input.len());
    }

    #[test]
    fn short_input_survives() {
        let input = tone(200, 220.0);
        assert!(!stretch(&input, 2.0).is_empty());
    }
}
