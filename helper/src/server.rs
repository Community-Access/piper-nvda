//! The stdio server: reads protocol frames, synthesizes on a worker thread
//! using per-voice Piper models, and streams audio/marker/done frames back.
//! Also decodes and plays voice demo samples.

use crate::cache::AudioCache;
use crate::dsp;
use crate::espeak::Phonemizer;
use crate::lexicon::{self, Lexicon, Piece};
use crate::mp3;
use crate::protocol::{self as p, msg_type};
use crate::synth::Engine;
use crate::text;
use anyhow::Result;
use serde::Serialize;
use std::collections::VecDeque;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex};

/// All voices are resampled to this rate so the NVDA WavePlayer stays fixed.
pub const OUTPUT_SR: usize = 22050;
const CHUNK_SAMPLES: usize = OUTPUT_SR / 5;

const WARMUP_CHARS: &str = "abcdefghijklmnopqrstuvwxyz0123456789";
const WARMUP_WORDS: &[&str] = &[
    "button", "checkbox", "check box", "radio button", "menu", "menu item",
    "menu bar", "list", "list item", "tree view", "tab", "edit", "combo box",
    "slider", "spin button", "progress bar", "link", "heading", "graphic",
    "table", "row", "column", "cell", "dialog", "window", "pane", "document",
    "toolbar", "status bar", "separator", "grouping", "region", "banner",
    "navigation", "article", "section", "form", "text", "password", "search",
    "toggle button", "split button", "scroll bar", "header", "footer",
    "selected", "not selected", "checked", "not checked", "half checked",
    "pressed", "not pressed", "expanded", "collapsed", "unavailable",
    "read only", "required", "invalid entry", "busy", "clickable", "editable",
    "multi line", "has pop up", "current", "modal", "on", "off",
    "blank", "empty", "space", "tab", "enter", "delete", "back space",
    "capital", "cap", "yes", "no", "okay", "cancel", "close", "open", "more",
    "less", "of", "level", "with", "contains", "out of", "new line", "line",
    "warning", "error", "alert",
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten",
    "dot", "comma", "star", "dash", "slash", "colon", "semicolon", "quote",
    "left paren", "right paren", "percent", "dollar", "at", "number",
    "ampersand", "plus", "minus", "equals", "greater", "less than",
];

pub struct Paths {
    pub espeak_dll: std::path::PathBuf,
    pub espeak_data: std::path::PathBuf,
    pub threads: usize,
    pub cache_dir: Option<std::path::PathBuf>,
}

enum Job {
    Speak(p::Speak),
    Sample(u64, String),
}

#[derive(Default)]
struct Work {
    jobs: VecDeque<(u64, Job)>,
    warmup: VecDeque<WarmupItem>,
    /// Pending lexicon replacement. Kept out of `jobs` so a cancel cannot
    /// drop it.
    lexicon: Option<p::SetLexicon>,
}

struct WarmupItem {
    model_path: String,
    text: String,
    char_mode: bool,
    scales: p::Scales,
}

struct Shared {
    work: Mutex<Work>,
    cv: Condvar,
    generation: AtomicU64,
    running: AtomicBool,
    out: Mutex<Box<dyn Write + Send>>,
}

impl Shared {
    fn send<T: Serialize>(&self, ty: u8, value: &T) {
        let mut out = self.out.lock().unwrap();
        let _ = p::write_json(&mut *out, ty, value);
    }
    fn send_audio(&self, utterance_id: u64, seq: u64, pcm: &[i16]) {
        let mut out = self.out.lock().unwrap();
        let _ = p::write_audio(&mut *out, utterance_id, seq, pcm);
    }
    fn log(&self, level: &str, message: String) {
        self.send(msg_type::LOG, &p::LogMsg { level: level.to_string(), message });
    }
    fn error(&self, code: &str, message: String) {
        self.send(msg_type::ERROR, &p::ErrorMsg { code: code.to_string(), message });
    }
}

pub fn run(paths: &Paths) -> Result<()> {
    let engine = Engine::new(paths.threads);
    let phonemizer = Phonemizer::new(&paths.espeak_dll, &paths.espeak_data)?;

    let stdout: Box<dyn Write + Send> = Box::new(BufWriter::new(std::io::stdout()));
    let shared = Arc::new(Shared {
        work: Mutex::new(Work::default()),
        cv: Condvar::new(),
        generation: AtomicU64::new(0),
        running: AtomicBool::new(true),
        out: Mutex::new(stdout),
    });

    shared.send(msg_type::HELLO, &p::Hello {
        version: p::PROTOCOL_VERSION,
        role: "helper".to_string(),
        model_loaded: true,
    });

    let worker_shared = Arc::clone(&shared);
    let cache_dir = paths.cache_dir.clone();
    let worker = std::thread::spawn(move || {
        worker_loop(worker_shared, engine, phonemizer, cache_dir);
    });

    let mut stdin = std::io::stdin().lock();
    let mut sample_uid: u64 = 1 << 32; // demo ids kept away from utterance ids
    while shared.running.load(Ordering::SeqCst) {
        let (ty, payload) = match p::read_frame(&mut stdin) {
            Ok(f) => f,
            Err(_) => break,
        };
        match ty {
            msg_type::SPEAK => match serde_json::from_slice::<p::Speak>(&payload) {
                Ok(speak) => {
                    let g = shared.generation.load(Ordering::SeqCst);
                    shared.work.lock().unwrap().jobs.push_back((g, Job::Speak(speak)));
                    shared.cv.notify_one();
                }
                Err(e) => shared.error("badSpeak", e.to_string()),
            },
            msg_type::PLAY_SAMPLE => match serde_json::from_slice::<p::PlaySample>(&payload) {
                Ok(ps) => {
                    sample_uid += 1;
                    let g = shared.generation.load(Ordering::SeqCst);
                    shared.work.lock().unwrap()
                        .jobs.push_back((g, Job::Sample(sample_uid, ps.path)));
                    shared.cv.notify_one();
                }
                Err(e) => shared.error("badSample", e.to_string()),
            },
            msg_type::CANCEL => {
                shared.generation.fetch_add(1, Ordering::SeqCst);
                shared.work.lock().unwrap().jobs.clear();
            }
            msg_type::PING => shared.send(msg_type::PONG, &serde_json::json!({})),
            msg_type::LOAD_VOICE => {
                if let Ok(lv) = serde_json::from_slice::<p::LoadVoice>(&payload) {
                    enqueue_warmup(&shared, &lv.voice, lv.scales);
                }
            }
            msg_type::SET_LEXICON => match serde_json::from_slice::<p::SetLexicon>(&payload) {
                Ok(sl) => {
                    shared.work.lock().unwrap().lexicon = Some(sl);
                    shared.cv.notify_one();
                }
                Err(e) => shared.error("badLexicon", e.to_string()),
            },
            msg_type::HELLO => {}
            msg_type::SHUTDOWN => break,
            other => shared.log("warning", format!("unknown frame type {other}")),
        }
    }
    shared.running.store(false, Ordering::SeqCst);
    shared.cv.notify_all();
    let _ = worker.join();
    Ok(())
}

enum Task {
    Job(u64, Job),
    Warmup(WarmupItem),
    Lexicon(p::SetLexicon),
    Shutdown,
}

fn next_task(shared: &Shared) -> Task {
    let mut work = shared.work.lock().unwrap();
    loop {
        if !shared.running.load(Ordering::SeqCst) {
            return Task::Shutdown;
        }
        // Lexicon edits apply before queued speech so a correction the user
        // just made is audible on the next utterance.
        if let Some(sl) = work.lexicon.take() {
            return Task::Lexicon(sl);
        }
        if let Some((g, job)) = work.jobs.pop_front() {
            return Task::Job(g, job);
        }
        if let Some(item) = work.warmup.pop_front() {
            return Task::Warmup(item);
        }
        work = shared.cv.wait(work).unwrap();
    }
}

fn worker_loop(
    shared: Arc<Shared>,
    mut engine: Engine,
    mut phonemizer: Phonemizer,
    cache_dir: Option<std::path::PathBuf>,
) {
    let mut cache = AudioCache::new(cache_dir.as_deref());
    let mut lex = Lexicon::new();
    loop {
        match next_task(&shared) {
            Task::Job(g, Job::Speak(speak)) => {
                speak_job(&shared, &mut engine, &mut phonemizer, &mut cache, &lex, g, &speak);
            }
            Task::Job(g, Job::Sample(uid, path)) => {
                play_sample(&shared, g, uid, &path);
            }
            Task::Lexicon(sl) => {
                lex.set(sl.rev, sl.entries);
            }
            Task::Warmup(item) => {
                warm_one(&mut engine, &mut phonemizer, &mut cache, &lex, &item);
                if shared.work.lock().unwrap().warmup.is_empty() {
                    cache.save();
                }
            }
            Task::Shutdown => {
                cache.save();
                return;
            }
        }
    }
}

fn enqueue_warmup(shared: &Shared, model_path: &str, scales: p::Scales) {
    let mut work = shared.work.lock().unwrap();
    // Re-warming for a new voice or variance makes queued items pointless.
    work.warmup.clear();
    for ch in WARMUP_CHARS.chars() {
        work.warmup.push_back(WarmupItem {
            model_path: model_path.to_string(),
            text: ch.to_string(),
            char_mode: true,
            scales,
        });
    }
    for word in WARMUP_WORDS {
        work.warmup.push_back(WarmupItem {
            model_path: model_path.to_string(),
            text: (*word).to_string(),
            char_mode: false,
            scales,
        });
    }
    drop(work);
    shared.cv.notify_one();
}

fn cache_key(
    model_path: &str,
    char_mode: bool,
    scales: &p::Scales,
    lexicon_rev: u64,
    text: &str,
) -> String {
    AudioCache::key(model_path, char_mode, &scales.key_part(), lexicon_rev, text)
}

/// IPA for one chunk, with lexicon overrides spliced in around the runs of
/// text espeak still handles.
fn chunk_to_ipa(phonemizer: &mut Phonemizer, pieces: &[Piece]) -> Option<String> {
    let mut ipa = String::new();
    for piece in pieces {
        let part = match piece {
            Piece::Plain(text) => phonemizer.to_ipa(text).ok()?,
            Piece::Ipa(text) => (*text).to_string(),
        };
        if part.is_empty() {
            continue;
        }
        if !ipa.is_empty() && !ipa.ends_with(' ') {
            ipa.push(' ');
        }
        ipa.push_str(&part);
    }
    Some(ipa)
}

/// Phonemize + infer one chunk, resampled to OUTPUT_SR. None if no phonemes.
fn synth_chunk(
    engine: &mut Engine,
    phonemizer: &mut Phonemizer,
    model_path: &str,
    sid: i64,
    scales: p::Scales,
    pieces: &[Piece],
) -> Option<Vec<f32>> {
    let ipa = chunk_to_ipa(phonemizer, pieces)?;
    let synth = engine
        .synth(Path::new(model_path), &ipa, sid, scales)
        .ok()??;
    Some(resample(synth.samples, synth.sample_rate))
}

fn resample(samples: Vec<f32>, src_sr: u32) -> Vec<f32> {
    if src_sr as usize == OUTPUT_SR {
        return samples;
    }
    dsp::linear_resample(&samples, src_sr as f32 / OUTPUT_SR as f32)
}

fn warm_one(
    engine: &mut Engine,
    phonemizer: &mut Phonemizer,
    cache: &mut AudioCache,
    lex: &Lexicon,
    item: &WarmupItem,
) {
    let pieces = lex.split(&item.text);
    let rev = if lexicon::has_override(&pieces) { lex.rev() } else { 0 };
    let key = cache_key(&item.model_path, item.char_mode, &item.scales, rev, &item.text);
    if cache.contains(&key) {
        return;
    }
    let voice = match engine.espeak_voice(Path::new(&item.model_path)) {
        Ok(v) => v,
        Err(_) => return,
    };
    if phonemizer.set_language(&voice).is_err() {
        return;
    }
    if let Some(samples) =
        synth_chunk(engine, phonemizer, &item.model_path, 0, item.scales, &pieces)
    {
        cache.put(key, samples);
    }
}

fn canceled(shared: &Shared, g: u64) -> bool {
    shared.generation.load(Ordering::SeqCst) != g
}

fn speak_job(
    shared: &Shared,
    engine: &mut Engine,
    phonemizer: &mut Phonemizer,
    cache: &mut AudioCache,
    lex: &Lexicon,
    g: u64,
    speak: &p::Speak,
) {
    let uid = speak.utterance_id;
    let mut seq: u64 = 0;
    let mut first_audio = true;

    for seg in &speak.segments {
        if canceled(shared, g) {
            return;
        }
        for &index in &seg.indexes_before {
            shared.send(msg_type::MARKER, &p::Marker { utterance_id: uid, index });
        }
        if seg.break_ms_before > 0 {
            let n = OUTPUT_SR * (seg.break_ms_before as usize) / 1000;
            emit_pcm(shared, uid, &mut seq, &vec![0i16; n]);
        }
        let trimmed = seg.text.trim();
        if trimmed.is_empty() {
            continue;
        }
        // Set espeak language from the voice config.
        match engine.espeak_voice(Path::new(&seg.model_path)) {
            Ok(voice) => {
                if let Err(e) = phonemizer.set_language(&voice) {
                    shared.log("warning", format!("espeak voice {voice}: {e}"));
                }
            }
            Err(e) => {
                shared.error("loadModel", format!("{}: {e}", seg.model_path));
                continue;
            }
        }
        let chunks: Vec<String> = if seg.char_mode {
            vec![trimmed.to_string()]
        } else {
            text::split_streaming(trimmed)
        };
        for chunk in &chunks {
            if canceled(shared, g) {
                return;
            }
            let pieces = lex.split(chunk);
            let rev = if lexicon::has_override(&pieces) { lex.rev() } else { 0 };
            let key = cache_key(&seg.model_path, seg.char_mode, &seg.scales, rev, chunk);
            let mut audio = match cache.get(&key) {
                Some(a) => a,
                None => match synth_chunk(
                    engine, phonemizer, &seg.model_path, seg.sid, seg.scales, &pieces,
                ) {
                    Some(a) => {
                        cache.put(key, a.clone());
                        a
                    }
                    None => continue,
                },
            };
            if canceled(shared, g) {
                return;
            }
            if first_audio {
                dsp::trim_leading_silence(&mut audio);
                first_audio = false;
            }
            if (seg.stretch - 1.0).abs() > 0.01 {
                audio = dsp::stretch(&audio, seg.stretch);
            }
            if seg.pitch_semis.abs() > 0.05 {
                audio = dsp::pitch_shift(&audio, seg.pitch_semis);
            }
            let pcm = dsp::to_i16(&audio, seg.volume);
            if canceled(shared, g) {
                return;
            }
            emit_pcm(shared, uid, &mut seq, &pcm);
        }
    }
    if canceled(shared, g) {
        return;
    }
    for &index in &speak.indexes_after {
        shared.send(msg_type::MARKER, &p::Marker { utterance_id: uid, index });
    }
    shared.send(msg_type::DONE, &p::Done { utterance_id: uid });
}

fn play_sample(shared: &Shared, g: u64, uid: u64, path: &str) {
    let (samples, sr) = match mp3::decode_file(Path::new(path)) {
        Ok(r) => r,
        Err(e) => {
            shared.error("sampleDecode", e.to_string());
            shared.send(msg_type::DONE, &p::Done { utterance_id: uid });
            return;
        }
    };
    let audio = resample(samples, sr);
    let pcm = dsp::to_i16(&audio, 1.0);
    let mut seq = 0u64;
    // Emit in chunks so cancel is responsive during a long demo.
    for chunk in pcm.chunks(CHUNK_SAMPLES) {
        if canceled(shared, g) {
            return;
        }
        shared.send_audio(uid, seq, chunk);
        seq += 1;
    }
    shared.send(msg_type::DONE, &p::Done { utterance_id: uid });
}

fn emit_pcm(shared: &Shared, uid: u64, seq: &mut u64, pcm: &[i16]) {
    for chunk in pcm.chunks(CHUNK_SAMPLES) {
        shared.send_audio(uid, *seq, chunk);
        *seq += 1;
    }
}
