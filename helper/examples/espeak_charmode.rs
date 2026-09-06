//! Probe espeak-ng phonemization of single characters as plain text vs. via
//! SSML <say-as interpret-as="characters">, to find how to pronounce letters
//! and symbols as their spoken names in character mode.
//! Run: cargo run --example espeak_charmode

use libloading::{Library, Symbol};
use std::ffi::{c_char, c_int, c_void, CStr, CString};

const ESPEAK_CHARS_UTF8: c_int = 1;
const ESPEAK_SSML: c_int = 0x10;
const ESPEAK_PHONEMES_IPA: c_int = 0x02;

fn main() {
    let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../assets/espeak-ng/eSpeak NG");
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

        let phon = |text: &str, ssml: bool| -> String {
            let c = CString::new(text).unwrap();
            let mut ptr: *const c_void = c.as_ptr() as *const c_void;
            let mode = if ssml { ESPEAK_CHARS_UTF8 | ESPEAK_SSML } else { ESPEAK_CHARS_UTF8 };
            let mut out = String::new();
            while !ptr.is_null() {
                let res = to_phonemes(&mut ptr, mode, ESPEAK_PHONEMES_IPA);
                if res.is_null() {
                    break;
                }
                out.push_str(&CStr::from_ptr(res).to_string_lossy());
            }
            out
        };

        for ch in ["a", "b", "z", "5", "!", ".", "@", "#"] {
            let plain = phon(ch, false);
            let ssml_text = format!(
                "<say-as interpret-as=\"characters\">{}</say-as>",
                ch.replace('&', "&amp;").replace('<', "&lt;")
            );
            let ssml = phon(&ssml_text, true);
            println!("{ch:>3} | plain: {plain:<12} | ssml-chars: {ssml}");
        }
    }
}
