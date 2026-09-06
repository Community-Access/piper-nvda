//! Probe espeak-ng phonemization of single characters, to find which ones
//! come out as their spoken name and which produce nothing at all. A
//! character that phonemizes to nothing is a character the synthesizer would
//! be silent for.
//! Run: cargo run --example espeak_charmode

use libloading::{Library, Symbol};
use std::ffi::{c_char, c_int, c_void, CStr, CString};

const ESPEAK_CHARS_UTF8: c_int = 1;
const ESPEAK_PHONEMES_IPA: c_int = 0x02;

fn main() {
    let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../assets/espeak-ng/eSpeak NG");
    let dll = base.join("libespeak-ng.dll");
    let lib = unsafe { Library::new(&dll) }.expect("load dll");
    unsafe {
        let init: Symbol<unsafe extern "C" fn(c_int, c_int, *const c_char, c_int) -> c_int> =
            lib.get(b"espeak_Initialize\0").unwrap();
        let set_voice: Symbol<unsafe extern "C" fn(*const c_char) -> c_int> =
            lib.get(b"espeak_SetVoiceByName\0").unwrap();
        let to_phonemes: Symbol<
            unsafe extern "C" fn(*mut *const c_void, c_int, c_int) -> *const c_char,
        > = lib.get(b"espeak_TextToPhonemes\0").unwrap();

        let data = CString::new(base.to_string_lossy().as_bytes()).unwrap();
        init(1, 0, data.as_ptr(), 0);
        set_voice(CString::new("en-us").unwrap().as_ptr());

        let phon = |text: &str| -> String {
            let Ok(c) = CString::new(text) else {
                return String::new();
            };
            let mut ptr: *const c_void = c.as_ptr() as *const c_void;
            let mut out = String::new();
            while !ptr.is_null() {
                let res = to_phonemes(&mut ptr, ESPEAK_CHARS_UTF8, ESPEAK_PHONEMES_IPA);
                if res.is_null() {
                    break;
                }
                out.push_str(CStr::from_ptr(res).to_string_lossy().trim());
            }
            out
        };

        let mut silent = Vec::new();
        println!("char  bare            in a carrier");
        for code in 32u8..127 {
            let ch = code as char;
            let bare = phon(&ch.to_string());
            // A carrier stops espeak from treating the character as clause
            // punctuation and throwing it away.
            let carried = phon(&format!("\u{2068}{ch}\u{2069}"));
            let name = match ch {
                ' ' => "sp".to_string(),
                _ => ch.to_string(),
            };
            println!("{name:>4}  {bare:<15} {carried}");
            if bare.is_empty() {
                silent.push(ch);
            }
        }
        println!("\nsilent when sent bare: {silent:?}");
    }
}
