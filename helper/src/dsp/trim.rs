//! Leading-silence trimming. Neural vocoders emit 20-80 ms of near-silence
//! before the first phone; removing it directly reduces perceived latency.

/// Amplitude below this is treated as silence (about -46 dBFS).
const THRESHOLD: f32 = 0.005;
/// Samples of silence retained before the first audible sample (10 ms).
const KEEP: usize = 240;

pub fn trim_leading_silence(samples: &mut Vec<f32>) {
    if let Some(first) = samples.iter().position(|s| s.abs() > THRESHOLD) {
        let start = first.saturating_sub(KEEP);
        if start > 0 {
            samples.drain(..start);
        }
    }
    // All-silence audio is left alone; it may be an intentional break.
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trims_leading_silence_keeps_margin() {
        let mut s = vec![0.0f32; 2400];
        s.extend_from_slice(&[0.5f32; 100]);
        trim_leading_silence(&mut s);
        assert_eq!(s.len(), KEEP + 100);
        assert_eq!(s[KEEP], 0.5);
    }

    #[test]
    fn leaves_pure_silence() {
        let mut s = vec![0.0f32; 1000];
        trim_leading_silence(&mut s);
        assert_eq!(s.len(), 1000);
    }

    #[test]
    fn leaves_immediate_audio() {
        let mut s = vec![0.9f32; 100];
        trim_leading_silence(&mut s);
        assert_eq!(s.len(), 100);
    }
}
