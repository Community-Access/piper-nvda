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
    /// Seconds of silence to insert after particular phonemes. Used by a few
    /// voices whose training data needs it to sound right.
    #[serde(default)]
    phoneme_silence: HashMap<String, f32>,
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
    /// Voice-level phoneme substitutions applied before id lookup.
    #[serde(default)]
    phoneme_map: HashMap<String, Vec<String>>,
    /// How the voice's phonemes are produced. Absent on voices trained
    /// before the field existed, all of which use espeak.
    phoneme_type: Option<String>,
}

fn default_inference() -> InferenceCfg {
    InferenceCfg {
        noise_scale: def_noise_scale(),
        length_scale: def_length_scale(),
        noise_w: def_noise_w(),
        phoneme_silence: HashMap::new(),
    }
}

/// How a voice's phonemes are produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PhonemeType {
    /// espeak-ng turns text into IPA. The default, and all but a handful of
    /// the published voices.
    Espeak,
    /// The text's own code points are the phonemes; no phonemizer runs.
    Text,
    /// A phonemizer this helper does not bundle (pinyin, hebrew, japanese,
    /// thai). Such a voice cannot be spoken correctly, so it is refused
    /// rather than fed espeak's IPA, which would be noise.
    Unsupported(String),
}

impl PhonemeType {
    fn parse(raw: Option<&str>) -> Self {
        match raw {
            None | Some("espeak") => PhonemeType::Espeak,
            Some("text") => PhonemeType::Text,
            Some(other) => PhonemeType::Unsupported(other.to_string()),
        }
    }
}
/// A parsed voice config with the phoneme map keyed by the single Unicode
/// character Piper uses as a phoneme (its keys are code points).
pub struct VoiceConfig {
    pub sample_rate: u32,
    pub espeak_voice: String,
    pub noise_scale: f32,
    pub length_scale: f32,
    pub noise_w: f32,
    pub phoneme_type: PhonemeType,
    pub phoneme_ids: HashMap<char, Vec<i64>>,
    /// Substitutions applied to a phoneme before its id is looked up.
    pub phoneme_map: HashMap<char, Vec<char>>,
    /// Seconds of silence to insert after a phoneme.
    pub phoneme_silence: HashMap<char, f32>,
    pub bos: Vec<i64>,
    pub eos: Vec<i64>,
    pub pad: Vec<i64>,
}

/// Read only `phoneme_type` from a voice configuration.
///
/// A voice this helper cannot speak should be refused without paying to load
/// its model, which is tens of megabytes.
pub fn phoneme_type_of(path: &Path) -> Result<PhonemeType> {
    #[derive(Deserialize)]
    struct TypeOnly {
        phoneme_type: Option<String>,
    }
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("reading config {}", path.display()))?;
    let raw: TypeOnly = serde_json::from_str(&text).context("parsing voice config json")?;
    Ok(PhonemeType::parse(raw.phoneme_type.as_deref()))
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
            phoneme_type: PhonemeType::parse(raw.phoneme_type.as_deref()),
            phoneme_ids,
            phoneme_map: single_char_keys(raw.phoneme_map, |v| {
                v.iter().flat_map(|s| s.chars()).collect()
            }),
            phoneme_silence: single_char_keys(raw.inference.phoneme_silence, |v| *v),
            bos,
            eos,
            pad,
        })
    }

    /// Build the model input id sequence from an IPA phoneme string, matching
    /// the C++ piper-phonemize `interspersePad` convention the released ONNX
    /// models were built with: BOS, PAD, p1, PAD, p2, PAD, ..., pN, PAD, EOS.
    /// Voice-level `phoneme_map` substitutions are applied first, as Piper
    /// does. Returns the ids and the number of real phonemes that mapped.
    pub fn phonemes_to_ids(&self, ipa: &str) -> (Vec<i64>, usize) {
        let mut ids = Vec::with_capacity(ipa.len() * 2 + 4);
        ids.extend_from_slice(&self.bos);
        let mut matched = 0;
        for ch in ipa.chars() {
            match self.phoneme_map.get(&ch) {
                Some(replacement) => {
                    for &sub in replacement {
                        matched += self.push_phoneme(&mut ids, sub);
                    }
                }
                None => matched += self.push_phoneme(&mut ids, ch),
            }
        }
        ids.extend_from_slice(&self.pad);
        ids.extend_from_slice(&self.eos);
        (ids, matched)
    }

    fn push_phoneme(&self, ids: &mut Vec<i64>, phoneme: char) -> usize {
        match self.phoneme_ids.get(&phoneme) {
            Some(pid) => {
                ids.extend_from_slice(&self.pad);
                ids.extend_from_slice(pid);
                1
            }
            None => 0,
        }
    }

    /// Split an IPA string after every phoneme the voice wants silence after.
    /// Returns (phonemes, seconds of silence to follow) pairs; a voice with
    /// no `phoneme_silence` yields the whole string and no silence.
    pub fn split_on_silence(&self, ipa: &str) -> Vec<(String, f32)> {
        if self.phoneme_silence.is_empty() {
            return vec![(ipa.to_string(), 0.0)];
        }
        let mut parts = Vec::new();
        let mut current = String::new();
        for ch in ipa.chars() {
            current.push(ch);
            if let Some(&seconds) = self.phoneme_silence.get(&ch) {
                parts.push((std::mem::take(&mut current), seconds));
            }
        }
        if !current.is_empty() {
            parts.push((current, 0.0));
        }
        if parts.is_empty() {
            parts.push((String::new(), 0.0));
        }
        parts
    }
}

/// Convert a JSON map whose keys are single-code-point phonemes, dropping
/// any key that is not exactly one character (Piper writes one per key).
fn single_char_keys<T, U>(
    raw: HashMap<String, T>,
    convert: impl Fn(&T) -> U,
) -> HashMap<char, U> {
    raw.iter()
        .filter_map(|(key, value)| {
            let mut chars = key.chars();
            match (chars.next(), chars.next()) {
                (Some(c), None) => Some((c, convert(value))),
                _ => None,
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_config(name: &str, json: &str) -> std::path::PathBuf {
        let path = std::env::temp_dir().join(name);
        std::fs::write(&path, json).unwrap();
        path
    }

    const MINIMAL: &str = r#"{
        "audio": {"sample_rate": 22050},
        "espeak": {"voice": "en-us"},
        "phoneme_id_map": {"^": [1], "$": [2], "_": [0], "a": [14], "b": [15]}
    }"#;

    #[test]
    fn absent_phoneme_type_means_espeak() {
        // 47 of the published voices predate the field; Piper treats them as
        // espeak voices and so must we.
        let cfg = VoiceConfig::load(&write_config("piper_cfg_absent.json", MINIMAL)).unwrap();
        assert_eq!(cfg.phoneme_type, PhonemeType::Espeak);
    }

    #[test]
    fn known_and_unknown_phoneme_types() {
        for (raw, want) in [
            ("espeak", PhonemeType::Espeak),
            ("text", PhonemeType::Text),
            ("pinyin", PhonemeType::Unsupported("pinyin".into())),
            ("hebrew", PhonemeType::Unsupported("hebrew".into())),
        ] {
            let json = MINIMAL.replace(
                "\"phoneme_id_map\"",
                &format!("\"phoneme_type\": \"{raw}\", \"phoneme_id_map\""),
            );
            let cfg =
                VoiceConfig::load(&write_config(&format!("piper_cfg_{raw}.json"), &json)).unwrap();
            assert_eq!(cfg.phoneme_type, want, "for {raw}");
        }
    }

    #[test]
    fn phoneme_map_substitutes_before_id_lookup() {
        let json = MINIMAL.replace(
            "\"phoneme_id_map\"",
            "\"phoneme_map\": {\"c\": [\"a\", \"b\"]}, \"phoneme_id_map\"",
        );
        let cfg = VoiceConfig::load(&write_config("piper_cfg_map.json", &json)).unwrap();
        let (ids, matched) = cfg.phonemes_to_ids("c");
        assert_eq!(matched, 2);
        assert_eq!(ids, vec![1, 0, 14, 0, 15, 0, 2]);
        // An unmapped phoneme is unaffected.
        assert_eq!(cfg.phonemes_to_ids("a").1, 1);
    }

    #[test]
    fn phoneme_silence_splits_the_sequence() {
        let json = MINIMAL.replace(
            "\"phoneme_id_map\"",
            "\"inference\": {\"phoneme_silence\": {\"b\": 0.5}}, \"phoneme_id_map\"",
        );
        let cfg = VoiceConfig::load(&write_config("piper_cfg_sil.json", &json)).unwrap();
        assert_eq!(
            cfg.split_on_silence("aba"),
            vec![("ab".to_string(), 0.5), ("a".to_string(), 0.0)]
        );
        // Voices without the field synthesize in one piece, as before.
        let plain = VoiceConfig::load(&write_config("piper_cfg_nosil.json", MINIMAL)).unwrap();
        assert_eq!(plain.split_on_silence("aba"), vec![("aba".to_string(), 0.0)]);
    }

    #[test]
    #[ignore = "requires assets/lessac-medium.onnx.json"]
    fn parses_real_config() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../assets/lessac-medium.onnx.json");
        let cfg = VoiceConfig::load(&path).unwrap();
        assert_eq!(cfg.sample_rate, 22050);
        assert_eq!(cfg.espeak_voice, "en-us");
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
