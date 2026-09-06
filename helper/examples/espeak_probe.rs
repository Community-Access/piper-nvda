//! Diagnostic: probe espeak-ng initialization, data path, and voice names.
//! Run: cargo run --example espeak_probe

use libloading::{Library, Symbol};
use std::ffi::{c_char, c_int, CStr, CString};

fn main() {
    let base = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../assets/espeak-ng/eSpeak NG");
    let dll = base.join("libespeak-ng.dll");
    let lib = unsafe { Library::new(&dll) }.expect("load dll");
    unsafe {
        let init: Symbol<unsafe extern "C" fn(c_int, c_int, *const c_char, c_int) -> c_int> =
            lib.get(b"espeak_Initialize\0").unwrap();
        let info: Symbol<unsafe extern "C" fn(*mut *const c_char) -> *const c_char> =
            lib.get(b"espeak_Info\0").unwrap();
        let set_voice: Symbol<unsafe extern "C" fn(*const c_char) -> c_int> =
            lib.get(b"espeak_SetVoiceByName\0").unwrap();

        let data = CString::new(base.to_string_lossy().as_bytes()).unwrap();
        let rate = init(1, 0, data.as_ptr(), 0);
        println!("init rate: {rate}");
        let mut path_ptr: *const c_char = std::ptr::null();
        let ver = info(&mut path_ptr);
        println!("version: {}", CStr::from_ptr(ver).to_string_lossy());
        if !path_ptr.is_null() {
            println!("data path: {}", CStr::from_ptr(path_ptr).to_string_lossy());
        }
        for name in ["en-us", "en-US", "en", "English (America)", "gmw/en-US", "en-gb"] {
            let c = CString::new(name).unwrap();
            let rc = set_voice(c.as_ptr());
            println!("SetVoiceByName({name}) -> {rc}");
        }
    }
}
