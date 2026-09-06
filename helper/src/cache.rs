//! In-memory LRU cache of raw model output (pre-DSP f32 samples), with
//! optional disk persistence. Character echo and re-read navigation lines hit
//! the cache and skip inference entirely, so first audio is near-instant.
//!
//! The cache stores model output BEFORE stretch/pitch/volume DSP, so a cached
//! entry serves every pitch/volume (capital letters, prosody commands) without
//! reducing the hit rate.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

const MAGIC: &[u8; 4] = b"KCAC";
const VERSION: u32 = 1;
/// Maximum cached entries before least-recently-used eviction.
const MAX_ENTRIES: usize = 4000;
/// Chunks longer than this (in samples, ~4s at 24 kHz) are not cached; long
/// text rarely repeats verbatim and would waste the budget.
const MAX_CACHEABLE_SAMPLES: usize = 24000 * 4;

struct Entry {
    samples: Vec<f32>,
    used: u64,
}

pub struct AudioCache {
    map: HashMap<String, Entry>,
    clock: u64,
    path: Option<PathBuf>,
    dirty: bool,
}

impl AudioCache {
    pub fn new(cache_dir: Option<&Path>) -> Self {
        let path = cache_dir.map(|d| d.join("piper-audio.kcache"));
        let mut cache = Self {
            map: HashMap::new(),
            clock: 0,
            path,
            dirty: false,
        };
        cache.load();
        cache
    }

    /// Build a cache key from the fields that change model output. DSP-only
    /// fields (pitch, volume, stretch) are intentionally excluded so one
    /// entry serves every rate, pitch, and volume. `scales` is the inference
    /// parameter multipliers, already rounded. `lexicon_rev` is 0 unless the
    /// chunk contains a pronunciation override, so editing the lexicon only
    /// invalidates the chunks it actually affects.
    pub fn key(voice: &str, char_mode: bool, scales: &str, lexicon_rev: u64,
               text: &str) -> String {
        format!("{voice}|{}|{scales}|{lexicon_rev}|{text}", char_mode as u8)
    }

    pub fn get(&mut self, key: &str) -> Option<Vec<f32>> {
        self.clock += 1;
        let clock = self.clock;
        if let Some(entry) = self.map.get_mut(key) {
            entry.used = clock;
            Some(entry.samples.clone())
        } else {
            None
        }
    }

    pub fn contains(&self, key: &str) -> bool {
        self.map.contains_key(key)
    }

    pub fn put(&mut self, key: String, samples: Vec<f32>) {
        if samples.is_empty() || samples.len() > MAX_CACHEABLE_SAMPLES {
            return;
        }
        self.clock += 1;
        let clock = self.clock;
        self.map.insert(key, Entry { samples, used: clock });
        self.dirty = true;
        if self.map.len() > MAX_ENTRIES {
            self.evict();
        }
    }

    fn evict(&mut self) {
        // Remove the ~10% least recently used entries in one pass.
        let target = self.map.len() - (MAX_ENTRIES * 9 / 10);
        let mut used: Vec<u64> = self.map.values().map(|e| e.used).collect();
        used.sort_unstable();
        let threshold = used[target.min(used.len() - 1)];
        self.map.retain(|_, e| e.used > threshold);
    }

    // -- persistence -------------------------------------------------------

    fn load(&mut self) {
        let Some(path) = self.path.clone() else { return };
        let Ok(mut f) = std::fs::File::open(&path) else { return };
        let mut buf = Vec::new();
        if f.read_to_end(&mut buf).is_err() {
            return;
        }
        if buf.len() < 12 || &buf[0..4] != MAGIC {
            return;
        }
        if u32::from_le_bytes([buf[4], buf[5], buf[6], buf[7]]) != VERSION {
            return;
        }
        let count = u32::from_le_bytes([buf[8], buf[9], buf[10], buf[11]]) as usize;
        let mut pos = 12;
        for _ in 0..count {
            if pos + 4 > buf.len() {
                break;
            }
            let klen = read_u32(&buf, &mut pos) as usize;
            if pos + klen + 4 > buf.len() {
                break;
            }
            let key = match std::str::from_utf8(&buf[pos..pos + klen]) {
                Ok(s) => s.to_string(),
                Err(_) => break,
            };
            pos += klen;
            let slen = read_u32(&buf, &mut pos) as usize;
            if pos + slen * 4 > buf.len() {
                break;
            }
            let mut samples = Vec::with_capacity(slen);
            for _ in 0..slen {
                samples.push(f32::from_le_bytes([
                    buf[pos], buf[pos + 1], buf[pos + 2], buf[pos + 3],
                ]));
                pos += 4;
            }
            self.clock += 1;
            let clock = self.clock;
            self.map.insert(key, Entry { samples, used: clock });
        }
    }

    pub fn save(&mut self) {
        if !self.dirty {
            return;
        }
        let Some(path) = self.path.clone() else { return };
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let tmp = path.with_extension("kcache.tmp");
        let Ok(mut f) = std::fs::File::create(&tmp) else { return };
        let mut ok = true;
        ok &= f.write_all(MAGIC).is_ok();
        ok &= f.write_all(&VERSION.to_le_bytes()).is_ok();
        ok &= f.write_all(&(self.map.len() as u32).to_le_bytes()).is_ok();
        for (key, entry) in &self.map {
            ok &= f.write_all(&(key.len() as u32).to_le_bytes()).is_ok();
            ok &= f.write_all(key.as_bytes()).is_ok();
            ok &= f.write_all(&(entry.samples.len() as u32).to_le_bytes()).is_ok();
            for s in &entry.samples {
                if f.write_all(&s.to_le_bytes()).is_err() {
                    ok = false;
                    break;
                }
            }
        }
        drop(f);
        if ok {
            let _ = std::fs::rename(&tmp, &path);
            self.dirty = false;
        } else {
            let _ = std::fs::remove_file(&tmp);
        }
    }
}

fn read_u32(buf: &[u8], pos: &mut usize) -> u32 {
    let v = u32::from_le_bytes([buf[*pos], buf[*pos + 1], buf[*pos + 2], buf[*pos + 3]]);
    *pos += 4;
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn put_get_roundtrip() {
        let mut c = AudioCache::new(None);
        let k = AudioCache::key("lessac", false, "1.00,1.00,1.00", 0, "a");
        assert!(c.get(&k).is_none());
        c.put(k.clone(), vec![0.1, 0.2, 0.3]);
        assert_eq!(c.get(&k), Some(vec![0.1, 0.2, 0.3]));
    }

    #[test]
    fn key_ignores_dsp_params() {
        // pitch/volume/rate are not part of the key; they are applied as DSP
        // after the cache, so the same text+voice collides on purpose.
        let plain = "1.00,1.00,1.00";
        let a = AudioCache::key("v", false, plain, 0, "a");
        let b = AudioCache::key("v", false, plain, 0, "a");
        assert_eq!(a, b);
        assert_ne!(a, AudioCache::key("v", true, plain, 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, "1.30,1.00,1.00", 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, "1.00,1.20,1.00", 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, plain, 9, "a"));
    }

    #[test]
    fn does_not_cache_oversize() {
        let mut c = AudioCache::new(None);
        let k = "big".to_string();
        c.put(k.clone(), vec![0.0; MAX_CACHEABLE_SAMPLES + 1]);
        assert!(c.get(&k).is_none());
    }

    #[test]
    fn eviction_keeps_recent() {
        let mut c = AudioCache::new(None);
        for i in 0..(MAX_ENTRIES + 100) {
            c.put(format!("k{i}"), vec![i as f32]);
        }
        assert!(c.map.len() <= MAX_ENTRIES);
        // The most recent key must still be present.
        let last = format!("k{}", MAX_ENTRIES + 99);
        assert!(c.contains(&last));
    }

    #[test]
    fn disk_persistence_roundtrip() {
        let dir = std::env::temp_dir().join("piper_cache_test");
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::remove_file(dir.join("piper-audio.kcache"));
        {
            let mut c = AudioCache::new(Some(&dir));
            c.put("hello".to_string(), vec![0.5, -0.5]);
            c.save();
        }
        let mut c2 = AudioCache::new(Some(&dir));
        assert_eq!(c2.get("hello"), Some(vec![0.5, -0.5]));
    }
}
