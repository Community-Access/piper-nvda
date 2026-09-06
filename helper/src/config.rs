//! Parser for a Piper voice's `.onnx.json` config.

use anyhow::{Context, Result};
use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Deserialize)]
struct AudioCfg {
    sample_rate: u32,
}

#[derive(Debug, Deserialize)]
struct EspeakCfg {
    voice: String,
}

#[derive(Debug, Deserialize)]
struct InferenceCfg {
    #[serde(default = "def_noise_scale")]
    noise_scale: f32,
    #[serde(default = "def_length_scale")]
    length_scale: f32,
    #[serde(default = "def_noise_w")]
    noise_w: f32,
}

fn def_noise_scale() -> f32 {
    0.667
}
fn def_length_scale() -> f32 {
    1.0
}
fn def_noise_w() -> f32 {
    0.8
}

#[derive(Debug, Deserialize)]
struct RawConfig {
    audio: AudioCfg,
    espeak: EspeakCfg,
    #[serde(default = "default_inference")]
    inference: InferenceCfg,
    phoneme_id_map: HashMap<String, Vec<i64>>,
    #[serde(default = "one")]
    num_speakers: usize,
}

fn default_inference() -> InferenceCfg {
    InferenceCfg {
        noise_scale: def_noise_scale(),
        length_scale: def_length_scale(),
        noise_w: def_noise_w(),
    }
}
fn one() -> usize {
    1
}

/// A parsed voice config with the phoneme map keyed by the single Unicode
/// character Piper uses as a phoneme (its keys are code points).
pub struct VoiceConfig {
    pub sample_rate: u32,
    pub espeak_voice: String,
    pub noise_scale: f32,
    pub length_scale: f32,
    pub noise_w: f32,
    pub num_speakers: usize,
    pub phoneme_ids: HashMap<char, Vec<i64>>,
    pub bos: Vec<i64>,
    pub eos: Vec<i64>,
    pub pad: Vec<i64>,
}

impl VoiceConfig {
    pub fn load(path: &Path) -> Result<Self> {
        let text = std::fs::read_to_string(path)
            .with_context(|| format!("reading config {}", path.display()))?;
        let raw: RawConfig =
            serde_json::from_str(&text).context("parsing voice config json")?;

        let mut phoneme_ids = HashMap::new();
        let mut bos = Vec::new();
        let mut eos = Vec::new();
        let mut pad = Vec::new();
        for (key, ids) in &raw.phoneme_id_map {
            match key.as_str() {
                "^" => bos = ids.clone(),
                "$" => eos = ids.clone(),
                "_" => pad = ids.clone(),
                _ => {
                    // Keys are single code points; store the first char.
                    if let Some(c) = key.chars().next() {
                        if key.chars().count() == 1 {
                            phoneme_ids.insert(c, ids.clone());
                        }
                    }
                }
            }
        }
        Ok(Self {
            sample_rate: raw.audio.sample_rate,
            espeak_voice: raw.espeak.voice,
            noise_scale: raw.inference.noise_scale,
            length_scale: raw.inference.length_scale,
            noise_w: raw.inference.noise_w,
            num_speakers: raw.num_speakers,
            phoneme_ids,
            bos,
            eos,
            pad,
        })
    }

    /// Build the model input id sequence from an IPA phoneme string, matching
    /// the C++ piper-phonemize `interspersePad` convention the released ONNX
    /// models were built with: BOS, PAD, p1, PAD, p2, PAD, ..., pN, PAD, EOS.
    /// Returns the ids and the number of real phonemes that mapped.
    pub fn phonemes_to_ids(&self, ipa: &str) -> (Vec<i64>, usize) {
        let mut ids = Vec::with_capacity(ipa.len() * 2 + 4);
        ids.extend_from_slice(&self.bos);
        let mut matched = 0;
        for ch in ipa.chars() {
            if let Some(pid) = self.phoneme_ids.get(&ch) {
                ids.extend_from_slice(&self.pad);
                ids.extend_from_slice(pid);
                matched += 1;
            }
        }
        ids.extend_from_slice(&self.pad);
        ids.extend_from_slice(&self.eos);
        (ids, matched)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "requires assets/lessac-medium.onnx.json"]
    fn parses_real_config() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../assets/lessac-medium.onnx.json");
        let cfg = VoiceConfig::load(&path).unwrap();
        assert_eq!(cfg.sample_rate, 22050);
        assert_eq!(cfg.espeak_voice, "en-us");
        assert_eq!(cfg.num_speakers, 1);
        assert_eq!(cfg.bos, vec![1]);
        assert_eq!(cfg.eos, vec![2]);
        assert_eq!(cfg.pad, vec![0]);
        // 'a' maps to [14] per the config.
        assert_eq!(cfg.phoneme_ids.get(&'a'), Some(&vec![14]));
        let (ids, matched) = cfg.phonemes_to_ids("a");
        // interspersePad: BOS, PAD, a, PAD, EOS = [1, 0, 14, 0, 2]
        assert_eq!(ids, vec![1, 0, 14, 0, 2]);
        assert_eq!(matched, 1);
        let (_, none) = cfg.phonemes_to_ids("\u{1F600}");
        assert_eq!(none, 0);
    }
}
