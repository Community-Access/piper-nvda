//! Piper (VITS) inference. Each Piper voice is a separate ONNX model, so the
//! engine keeps a small LRU of loaded voice sessions to bound memory while
//! avoiding reloads on the hot path.

use crate::config::VoiceConfig;
use anyhow::{anyhow, Context, Result};
use ort::session::builder::GraphOptimizationLevel;
use ort::session::Session;
use ort::value::Tensor;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// ort's error type is not Send+Sync; stringify it so it flows through anyhow.
fn ort_err<T, R>(r: std::result::Result<T, ort::Error<R>>) -> Result<T> {
    r.map_err(|e| anyhow!("onnxruntime: {e}"))
}

struct Loaded {
    session: Session,
    config: VoiceConfig,
    has_sid: bool,
    used: u64,
}

pub struct Engine {
    voices: HashMap<PathBuf, Loaded>,
    threads: usize,
    clock: u64,
    max_loaded: usize,
}

/// Synthesis result: raw model samples plus the voice's native sample rate.
pub struct Synth {
    pub samples: Vec<f32>,
    pub sample_rate: u32,
}

impl Engine {
    pub fn new(threads: usize) -> Self {
        Self {
            voices: HashMap::new(),
            threads,
            clock: 0,
            max_loaded: 3,
        }
    }

    fn ensure_loaded(&mut self, model_path: &Path) -> Result<()> {
        if self.voices.contains_key(model_path) {
            return Ok(());
        }
        let config_path = config_path_for(model_path);
        let config = VoiceConfig::load(&config_path)?;
        let mut builder = ort_err(ort_err(ort_err(Session::builder())?
            .with_optimization_level(GraphOptimizationLevel::Level3))?
            .with_intra_threads(self.threads.max(1)))?;
        let session = ort_err(builder.commit_from_file(model_path))
            .with_context(|| format!("loading model {}", model_path.display()))?;
        let has_sid = session.inputs().iter().any(|i| i.name() == "sid");

        if self.voices.len() >= self.max_loaded {
            self.evict_lru();
        }
        self.clock += 1;
        self.voices.insert(
            model_path.to_path_buf(),
            Loaded {
                session,
                config,
                has_sid,
                used: self.clock,
            },
        );
        Ok(())
    }

    fn evict_lru(&mut self) {
        if let Some(oldest) = self
            .voices
            .iter()
            .min_by_key(|(_, v)| v.used)
            .map(|(k, _)| k.clone())
        {
            self.voices.remove(&oldest);
        }
    }

    /// The espeak voice tag configured for a model (loads it if needed).
    pub fn espeak_voice(&mut self, model_path: &Path) -> Result<String> {
        self.ensure_loaded(model_path)?;
        Ok(self.voices[model_path].config.espeak_voice.clone())
    }

    /// Synthesize IPA phonemes with the given model. Speed/rate is applied
    /// later as post-cache time-stretch, so length_scale stays at the config
    /// default (keeps cached audio rate-independent). `variance` scales the
    /// model's noise parameters: below 1.0 is flatter and steadier, above 1.0
    /// is more varied.
    pub fn synth(
        &mut self,
        model_path: &Path,
        ipa: &str,
        sid: i64,
        variance: f32,
    ) -> Result<Option<Synth>> {
        self.ensure_loaded(model_path)?;
        self.clock += 1;
        let clock = self.clock;
        let loaded = self.voices.get_mut(model_path).unwrap();
        loaded.used = clock;

        let (ids, matched) = loaded.config.phonemes_to_ids(ipa);
        if matched == 0 {
            return Ok(None);
        }
        let n = ids.len();
        let variance = variance.clamp(0.0, 2.0);
        let scales = vec![
            loaded.config.noise_scale * variance,
            loaded.config.length_scale,
            loaded.config.noise_w * variance,
        ];
        let input = ort_err(Tensor::from_array(([1usize, n], ids)))?;
        let input_lengths = ort_err(Tensor::from_array(([1usize], vec![n as i64])))?;
        let scales_t = ort_err(Tensor::from_array(([3usize], scales)))?;

        let outputs = if loaded.has_sid {
            let sid_t = ort_err(Tensor::from_array(([1usize], vec![sid])))?;
            ort_err(loaded.session.run(ort::inputs![
                "input" => input,
                "input_lengths" => input_lengths,
                "scales" => scales_t,
                "sid" => sid_t,
            ]))?
        } else {
            ort_err(loaded.session.run(ort::inputs![
                "input" => input,
                "input_lengths" => input_lengths,
                "scales" => scales_t,
            ]))?
        };
        let (_, data) = ort_err(outputs[0].try_extract_tensor::<f32>())
            .context("extracting model output")?;
        Ok(Some(Synth {
            samples: data.to_vec(),
            sample_rate: loaded.config.sample_rate,
        }))
    }
}

/// `foo.onnx` -> `foo.onnx.json`.
pub fn config_path_for(model_path: &Path) -> PathBuf {
    let mut s = model_path.as_os_str().to_os_string();
    s.push(".json");
    PathBuf::from(s)
}
