//! espeak-ng phonemization via runtime-loaded libespeak-ng.dll.
//!
//! espeak-ng is not thread safe; a `Phonemizer` must only be used from one
//! thread (the synthesis worker owns it).

use anyhow::{bail, Context, Result};
use libloading::{Library, Symbol};
use std::ffi::{c_char, c_int, c_void, CStr, CString};
use std::path::Path;

const AUDIO_OUTPUT_RETRIEVAL: c_int = 1;
const ESPEAK_CHARS_UTF8: c_int = 1;
/// bit 1 set = IPA output as UTF-8.
const ESPEAK_PHONEMES_IPA: c_int = 0x02;

type InitializeFn = unsafe extern "C" fn(c_int, c_int, *const c_char, c_int) -> c_int;
type SetVoiceByNameFn = unsafe extern "C" fn(*const c_char) -> c_int;
type TextToPhonemesFn =
    unsafe extern "C" fn(*mut *const c_void, c_int, c_int) -> *const c_char;

pub struct Phonemizer {
    // Field order matters: symbols borrow from the library, so keep raw fn
    // pointers only (obtained once) and hold the library to keep them valid.
    set_voice: SetVoiceByNameFn,
    to_phonemes: TextToPhonemesFn,
    _lib: Library,
    current_voice: String,
}

impl Phonemizer {
    /// `dll_path` is the full path to libespeak-ng.dll; `data_dir` is the
    /// directory CONTAINING the espeak-ng-data folder.
    pub fn new(dll_path: &Path, data_dir: &Path) -> Result<Self> {
        let lib = unsafe { Library::new(dll_path) }
            .with_context(|| format!("loading {}", dll_path.display()))?;
        let (init, set_voice, to_phonemes) = unsafe {
            let init: Symbol<InitializeFn> = lib
                .get(b"espeak_Initialize\0")
                .context("espeak_Initialize not found")?;
            let set_voice: Symbol<SetVoiceByNameFn> = lib
                .get(b"espeak_SetVoiceByName\0")
                .context("espeak_SetVoiceByName not found")?;
            let to_phonemes: Symbol<TextToPhonemesFn> = lib
                .get(b"espeak_TextToPhonemes\0")
                .context("espeak_TextToPhonemes not found")?;
            (*init, *set_voice, *to_phonemes)
        };
        let data = CString::new(data_dir.to_string_lossy().as_bytes())?;
        let rate = unsafe { init(AUDIO_OUTPUT_RETRIEVAL, 0, data.as_ptr(), 0) };
        if rate <= 0 {
            bail!(
                "espeak_Initialize failed (rc {rate}); is espeak-ng-data present in {}?",
                data_dir.display()
            );
        }
        Ok(Self {
            set_voice,
            to_phonemes,
            _lib: lib,
            current_voice: String::new(),
        })
    }

    /// Map a driver language tag (lowercase, hyphenated) to an espeak voice
    /// and select it. Falls back to the primary subtag, then en-us.
    pub fn set_language(&mut self, lang: &str) -> Result<()> {
        if self.current_voice == lang {
            return Ok(());
        }
        let mut candidates: Vec<String> = vec![lang.to_string()];
        if let Some((primary, _)) = lang.split_once('-') {
            candidates.push(primary.to_string());
        }
        // espeak names Mandarin "cmn".
        if lang == "zh" || lang.starts_with("zh-") {
            candidates.insert(0, "cmn".to_string());
        }
        candidates.push("en-us".to_string());
        for cand in &candidates {
            let c = CString::new(cand.as_bytes())?;
            if unsafe { (self.set_voice)(c.as_ptr()) } == 0 {
                self.current_voice = lang.to_string();
                return Ok(());
            }
        }
        bail!("espeak has no voice for language {lang}");
    }

    /// Phonemize one clause-or-less chunk of text to IPA.
    /// espeak_TextToPhonemes consumes one clause per call; we loop and join.
    pub fn to_ipa(&mut self, text: &str) -> Result<String> {
        let c_text = CString::new(text.replace('\0', " "))?;
        let mut ptr: *const c_void = c_text.as_ptr() as *const c_void;
        let mut out = String::new();
        while !ptr.is_null() {
            let res = unsafe {
                (self.to_phonemes)(&mut ptr, ESPEAK_CHARS_UTF8, ESPEAK_PHONEMES_IPA)
            };
            if res.is_null() {
                break;
            }
            let clause = unsafe { CStr::from_ptr(res) }.to_string_lossy();
            let clause = clause.trim();
            if !clause.is_empty() {
                if !out.is_empty() {
                    out.push(' ');
                }
                out.push_str(clause);
            }
        }
        // espeak marks embedded language switches like "(en)"; Kokoro's vocab
        // has no parens for them mid-stream, and the tokenizer would keep the
        // paren chars, so strip those markers.
        Ok(strip_lang_switches(&out))
    }
}

fn strip_lang_switches(ipa: &str) -> String {
    let mut out = String::with_capacity(ipa.len());
    let mut chars = ipa.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '(' {
            // Consume through the matching ')', but only if it looks like a
            // short ascii language tag; otherwise keep literally.
            let mut tag = String::new();
            let mut closed = false;
            for c2 in chars.by_ref() {
                if c2 == ')' {
                    closed = true;
                    break;
                }
                tag.push(c2);
                if tag.len() > 8 {
                    break;
                }
            }
            let is_tag = closed
                && !tag.is_empty()
                && tag.chars().all(|t| t.is_ascii_alphanumeric() || t == '-');
            if !is_tag {
                out.push('(');
                out.push_str(&tag);
                if closed {
                    out.push(')');
                }
            }
        } else {
            out.push(c);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_language_switch_markers() {
        assert_eq!(strip_lang_switches("h(en)ello"), "hello");
        assert_eq!(strip_lang_switches("plain"), "plain");
    }

    fn assets() -> Option<(std::path::PathBuf, std::path::PathBuf)> {
        let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../assets/espeak-ng/eSpeak NG");
        let dll = base.join("libespeak-ng.dll");
        if dll.exists() {
            Some((dll, base))
        } else {
            None
        }
    }

    // One combined test: espeak-ng is not thread safe and cargo runs tests
    // in parallel threads within one process, so all espeak work must stay
    // in a single test.
    #[test]
    #[ignore = "requires assets/espeak-ng (run tools/fetch_assets.py)"]
    fn phonemizes_all_supported_languages() {
        let (dll, data) = assets().expect("espeak assets missing");
        let mut p = Phonemizer::new(&dll, &data).unwrap();
        p.set_language("en-us").unwrap();
        let ipa = p.to_ipa("hello world").unwrap();
        assert!(!ipa.is_empty());
        assert!(ipa.contains('l'), "unexpected ipa: {ipa}");
        // Single letters should come out as letter names for spelling.
        let b = p.to_ipa("b").unwrap();
        assert!(b.len() > 1, "single letter ipa too short: {b}");
        for lang in ["en-gb", "es", "fr", "hi", "it", "pt-br", "ja", "zh"] {
            p.set_language(lang).unwrap();
            let ipa = p.to_ipa("2 words").unwrap();
            assert!(!ipa.is_empty(), "empty ipa for {lang}");
        }
    }
}
