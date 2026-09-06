//! The stdio server: reads protocol frames, synthesizes on a worker thread
//! using per-voice Piper models, and streams audio/marker/done frames back.
//! Also decodes and plays voice demo samples.

use crate::cache::AudioCache;
use crate::charnames;
use crate::config::PhonemeType;
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

/// Punctuation and symbols. Reading by character or spelling a word is
/// exactly where a delay is felt, and these are as common there as letters.
const WARMUP_SYMBOLS: &[&str] = &[
    "!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", "-", ".",
    "/", ":", ";", "<", "=", ">", "?", "@", "[", "\\", "]", "^", "_", "`",
    "{", "|", "}", "~", "–", "—", "‘", "’", "“", "”", "…", "•", "°", "©",
    "®", "™", "€", "£", "¥", "¢", "§", "¶", "×", "÷", "±", "≠", "≤", "≥",
    "→", "←", "↑", "↓", "½", "¼", "¾", "«", "»",
];

/// What NVDA calls those symbols when it speaks one, taken from its own
/// English symbol dictionary rather than guessed: NVDA says "bang" for "!"
/// and "graav" for "`", which no amount of intuition would produce. These are
/// prepared in both character and text mode, because a symbol reaches the
/// synthesizer as its name either way depending on how it was reached.
const WARMUP_SYMBOL_NAMES: &[&str] = &[
    "bang", "quote", "dollar", "percent", "and", "tick", "left paren",
    "right paren", "star", "plus", "comma", "dash", "dot", "slash", "colon",
    "semi", "less", "equals", "greater", "question", "at", "left bracket",
    "right bracket", "caret", "line", "graav", "left brace", "bar",
    "right brace", "tilda", "en dash", "em dash", "left tick", "right tick",
    "left quote", "right quote", "dot dot dot", "bullet", "degrees",
    "copyright", "registered", "trademark", "euro", "pound", "yen", "cents",
    "section", "paragraph marker", "times", "divide by", "plus or Minus",
    "not equal to", "less- than or equal to", "greater-than or equal to",
    "right arrow", "left arrow", "up arrow", "down arrow", "one half",
    "one quarter", "three quarters", "double left pointing angle bracket",
    "double right pointing angle bracket",
];

/// Numbers, as digits and as the words a voice says them with. Line numbers,
/// page numbers, times, and list positions are read constantly.
const WARMUP_NUMBERS: &[&str] = &[
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty", "thirty", "forty",
    "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
    "million", "billion",
];
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
    /// Set when the user has asked for the prepared audio to be rebuilt.
    clear_cache: bool,
}

struct WarmupItem {
    model_path: String,
    text: String,
    scales: p::Scales,
}

struct Shared {
    work: Mutex<Work>,
    cv: Condvar,
    generation: AtomicU64,
    running: AtomicBool,
    /// Whether to prepare and reuse audio. Read from both threads, so it is
    /// an atomic rather than a field of the work queue.
    cache_enabled: AtomicBool,
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
        cache_enabled: AtomicBool::new(true),
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
                    if shared.cache_enabled.load(Ordering::SeqCst) {
                        enqueue_warmup(
                            &shared,
                            &lv.voice,
                            lv.scales,
                            &lv.extra_words,
                            lv.skip_builtin_symbols,
                        );
                    }
                }
            }
            msg_type::SET_CACHE => match serde_json::from_slice::<p::SetCache>(&payload) {
                Ok(sc) => {
                    shared.cache_enabled.store(sc.enabled, Ordering::SeqCst);
                    if !sc.enabled {
                        // Stop preparing immediately; anything already queued
                        // would only fill a cache nobody is going to read.
                        shared.work.lock().unwrap().warmup.clear();
                    }
                }
                Err(e) => shared.error("badSetCache", e.to_string()),
            },
            msg_type::CLEAR_CACHE => {
                shared.work.lock().unwrap().clear_cache = true;
                shared.cv.notify_one();
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
    ClearCache,
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
        if std::mem::take(&mut work.clear_cache) {
            return Task::ClearCache;
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
            Task::ClearCache => {
                cache.clear();
            }
            Task::Warmup(item) => {
                // Switching the cache off clears the queue, so this only
                // catches an item already taken off it.
                if shared.cache_enabled.load(Ordering::SeqCst) {
                    warm_one(&mut engine, &mut phonemizer, &mut cache, &lex, &item);
                    if shared.work.lock().unwrap().warmup.is_empty() {
                        cache.save();
                    }
                }
            }
            Task::Shutdown => {
                cache.save();
                return;
            }
        }
    }
}

fn enqueue_warmup(
    shared: &Shared,
    model_path: &str,
    scales: p::Scales,
    extra_words: &[String],
    skip_builtin_symbols: bool,
) {
    let items = warmup_items(model_path, scales, extra_words, skip_builtin_symbols);
    let mut work = shared.work.lock().unwrap();
    // Re-warming for a new voice or variance makes queued items pointless.
    work.warmup.clear();
    work.warmup.extend(items);
    drop(work);
    shared.cv.notify_one();
}

/// Everything worth preparing for a voice, in the order it is prepared.
fn warmup_items(
    model_path: &str,
    scales: p::Scales,
    extra_words: &[String],
    skip_builtin_symbols: bool,
) -> Vec<WarmupItem> {
    let mut items = Vec::new();
    let mut push = |text: &str| {
        items.push(WarmupItem {
            model_path: model_path.to_string(),
            text: text.to_string(),
            scales,
        });
    };
    // The user's own phrases go first: they asked for these specifically, and
    // preparation is idle-time work that any burst of speech interrupts.
    for word in extra_words {
        push(word);
    }
    for ch in WARMUP_CHARS.chars() {
        push(&ch.to_string());
    }
    for symbol in WARMUP_SYMBOLS {
        push(symbol);
    }
    // The driver sends these in the user's own language when it can, and
    // then the English ones would only be prepared to be never asked for.
    if !skip_builtin_symbols {
        for name in WARMUP_SYMBOL_NAMES {
            push(name);
        }
    }
    for number in WARMUP_NUMBERS {
        push(number);
    }
    for word in WARMUP_WORDS {
        push(word);
    }
    // Anything already prepared is skipped when it comes off the queue, so
    // overlap between these lists costs nothing.
    items
}

fn cache_key(
    model_path: &str,
    ipa: bool,
    scales: &p::Scales,
    lexicon_rev: u64,
    text: &str,
) -> String {
    AudioCache::key(model_path, ipa, &scales.key_part(), lexicon_rev, text)
}

/// How a chunk of a segment becomes phonemes.
enum Mode<'a> {
    /// Already phonemes: a PhonemeCommand, or a voice whose "phonemes" are
    /// the code points of its own text.
    Ready(String),
    /// espeak-ng, with pronunciation overrides spliced in.
    Espeak(Vec<Piece<'a>>),
}

/// Silence to insert after a chunk, in milliseconds, from the punctuation it
/// ends with. Model output is trimmed at both ends, so these pauses are the
/// only thing separating clauses, which makes the rhythm consistent instead
/// of dependent on how much silence the model happened to generate.
fn pause_after(chunk: &str, sentence_pause_ms: u32) -> u32 {
    if sentence_pause_ms == 0 {
        return 0;
    }
    match chunk.trim_end().chars().next_back() {
        Some('.') | Some('!') | Some('?') | Some('\u{2026}') => sentence_pause_ms,
        Some(',') | Some(';') | Some(':') => sentence_pause_ms * 2 / 5,
        _ => 0,
    }
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
    mode: &Mode,
    text: &str,
) -> Option<Vec<f32>> {
    let mut ipa = match mode {
        Mode::Ready(text) => text.clone(),
        Mode::Espeak(pieces) => chunk_to_ipa(phonemizer, pieces)?,
    };
    if ipa.trim().is_empty() {
        // espeak-ng gives nothing for a punctuation character on its own: it
        // reads it as clause punctuation and drops it. Say its name instead
        // of saying nothing.
        let name = charnames::name_of(text)?;
        ipa = phonemizer.to_ipa(name).ok()?;
    }
    let synth = engine
        .synth(Path::new(model_path), &ipa, sid, scales)
        .ok()??;
    let mut samples = resample(synth.samples, synth.sample_rate);
    // Trim before caching: the entry is then the sound alone, and the caller
    // decides how much silence goes around it.
    dsp::trim_leading_silence(&mut samples);
    dsp::trim_trailing_silence(&mut samples);
    Some(samples)
}

fn resample(samples: Vec<f32>, src_sr: u32) -> Vec<f32> {
    if src_sr as usize == OUTPUT_SR {
        return samples;
    }
    dsp::resample(&samples, src_sr as f32 / OUTPUT_SR as f32)
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
    let key = cache_key(&item.model_path, false, &item.scales, rev, &item.text);
    if cache.contains(&key) {
        return;
    }
    match engine.phoneme_type(Path::new(&item.model_path)) {
        Ok(PhonemeType::Espeak) => {}
        // Warming is best effort; voices that need no phonemizer, or one we
        // do not have, are left to the speak path to handle or report.
        _ => return,
    }
    let voice = match engine.espeak_voice(Path::new(&item.model_path)) {
        Ok(v) => v,
        Err(_) => return,
    };
    if phonemizer.set_language(&voice).is_err() {
        return;
    }
    let mode = Mode::Espeak(pieces);
    if let Some(samples) = synth_chunk(
        engine,
        phonemizer,
        &item.model_path,
        0,
        item.scales,
        &mode,
        &item.text,
    ) {
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
    // Silence owed to the punctuation of the previous chunk. Held over and
    // emitted before the next chunk so an utterance never ends on a pause.
    let mut pending_pause: u32 = 0;

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
        // A character being read or typed is sent on its own, and it can be
        // a space, which trimming would turn into nothing to say.
        let trimmed = if seg.char_mode {
            seg.text.as_str()
        } else {
            seg.text.trim()
        };
        if trimmed.is_empty() {
            continue;
        }
        let phoneme_type = match engine.phoneme_type(Path::new(&seg.model_path)) {
            Ok(t) => t,
            Err(e) => {
                shared.error("loadModel", format!("{}: {e}", seg.model_path));
                continue;
            }
        };
        if let PhonemeType::Unsupported(name) = &phoneme_type {
            // Feeding espeak's IPA to a voice trained on other phonemes
            // produces confident nonsense, so say nothing and report it.
            shared.error(
                "unsupportedVoice",
                format!(
                    "{} needs the {name} phonemizer, which this helper does not include",
                    seg.model_path
                ),
            );
            continue;
        }
        if phoneme_type == PhonemeType::Espeak {
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
        }
        // A pronunciation given as phonemes is one unit; so is a spelled
        // character. Everything else streams clause by clause.
        let chunks: Vec<String> = if seg.char_mode || seg.ipa {
            vec![trimmed.to_string()]
        } else {
            text::split_streaming(trimmed)
        };
        for chunk in &chunks {
            if canceled(shared, g) {
                return;
            }
            // Pronunciation overrides only apply to text a phonemizer
            // would otherwise have guessed at.
            let (mode, rev) = if seg.ipa {
                (Mode::Ready(chunk.clone()), 0)
            } else if phoneme_type == PhonemeType::Text {
                (Mode::Ready(chunk.to_lowercase()), 0)
            } else {
                let pieces = lex.split(chunk);
                let rev = if lexicon::has_override(&pieces) { lex.rev() } else { 0 };
                (Mode::Espeak(pieces), rev)
            };
            let key = cache_key(&seg.model_path, seg.ipa, &seg.scales, rev, chunk);
            let cache_enabled = shared.cache_enabled.load(Ordering::SeqCst);
            let mut audio = match cache.get(&key).filter(|_| cache_enabled) {
                Some(a) => a,
                None => {
                    let mut produced = synth_chunk(
                        engine, phonemizer, &seg.model_path, seg.sid, seg.scales, &mode,
                        chunk,
                    );
                    // Phonemes this voice does not know would come out as
                    // silence. Speak the word they stood for instead.
                    if produced.is_none() && seg.ipa && !seg.fallback_text.trim().is_empty() {
                        let fallback = Mode::Espeak(lex.split(&seg.fallback_text));
                        produced = synth_chunk(
                            engine, phonemizer, &seg.model_path, seg.sid, seg.scales,
                            &fallback, &seg.fallback_text,
                        );
                    }
                    match produced {
                        Some(a) => {
                            if cache_enabled {
                                cache.put(key, a.clone());
                            }
                            a
                        }
                        None => continue,
                    }
                }
            };
            if canceled(shared, g) {
                return;
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
            if pending_pause > 0 {
                emit_silence(shared, uid, &mut seq, pending_pause, seg.stretch);
            }
            emit_pcm(shared, uid, &mut seq, &pcm);
            pending_pause = pause_after(chunk, seg.sentence_pause_ms);
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

/// Emit a pause. Pauses shorten with the rate, the way the speech around
/// them does, so fast speech does not end up mostly silence.
fn emit_silence(shared: &Shared, uid: u64, seq: &mut u64, ms: u32, stretch: f32) {
    let scale = if stretch > 0.05 { stretch } else { 1.0 };
    let count = (OUTPUT_SR as f32 * (ms as f32 / 1000.0) / scale) as usize;
    if count > 0 {
        emit_pcm(shared, uid, seq, &vec![0i16; count]);
    }
}

fn emit_pcm(shared: &Shared, uid: u64, seq: &mut u64, pcm: &[i16]) {
    for chunk in pcm.chunks(CHUNK_SAMPLES) {
        shared.send_audio(uid, *seq, chunk);
        *seq += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn items(extra: &[String]) -> Vec<WarmupItem> {
        warmup_items("voice.onnx", p::Scales::default(), extra, false)
    }

    #[test]
    fn warmup_covers_letters_digits_symbols_and_numbers() {
        let prepared = items(&[]);
        let texts: Vec<&str> = prepared.iter().map(|i| i.text.as_str()).collect();

        // Letters and digits.
        assert!(texts.contains(&"a") && texts.contains(&"7"));
        // Punctuation, and what NVDA calls it when it speaks one.
        assert!(texts.contains(&"!") && texts.contains(&"?"));
        assert!(texts.contains(&"bang"));
        // Numbers, as digits and as words.
        assert!(texts.contains(&"seventeen"));
        // And the roles and states NVDA says constantly.
        assert!(texts.contains(&"button"));
    }

    #[test]
    fn the_driver_can_supply_the_symbol_names_itself() {
        // A French user should prepare "point", not "dot".
        let localized = vec!["point".to_string(), "virgule".to_string()];
        let prepared = warmup_items(
            "voice.onnx", p::Scales::default(), &localized, true);
        let texts: Vec<&str> = prepared.iter().map(|i| i.text.as_str()).collect();
        assert!(texts.contains(&"point"));
        assert!(!texts.contains(&"bang"), "English names were prepared anyway");
        // The characters and everything else are still prepared.
        assert!(texts.contains(&"!") && texts.contains(&"a"));
        assert!(texts.contains(&"button"));
    }

    #[test]
    fn the_users_own_phrases_are_prepared_first() {
        let prepared = items(&["Inbox".to_string()]);
        assert_eq!(prepared[0].text, "Inbox");
    }

    #[test]
    fn pauses_follow_the_punctuation() {
        assert_eq!(pause_after("Hello.", 100), 100);
        assert_eq!(pause_after("Hello!", 100), 100);
        assert_eq!(pause_after("Hello?", 100), 100);
        // Clause endings get a shorter pause than sentence endings.
        assert_eq!(pause_after("Hello,", 100), 40);
        assert_eq!(pause_after("Hello;", 100), 40);
        // No punctuation, no pause: the clause was split for streaming.
        assert_eq!(pause_after("Hello", 100), 0);
        // Trailing whitespace does not hide the punctuation.
        assert_eq!(pause_after("Hello. ", 100), 100);
    }

    #[test]
    fn zero_setting_means_no_pauses_at_all() {
        assert_eq!(pause_after("Hello.", 0), 0);
        assert_eq!(pause_after("Hello,", 0), 0);
    }
}
