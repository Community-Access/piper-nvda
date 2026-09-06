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
// 2: entries are stored with leading and trailing silence trimmed.
// 3: character mode dropped from the key; entries are keyed per chunk.
const VERSION: u32 = 3;
/// Maximum cached entries before least-recently-used eviction.
const MAX_ENTRIES: usize = 4000;
/// Maximum audio held, in samples. Entries average about half a second, so
/// the entry count alone is a poor bound on disk: a full warm is a few
/// hundred entries per voice, and someone with several voices would otherwise
/// accumulate hundreds of megabytes in their NVDA configuration directory.
/// 16M samples is about 64 MB, or twelve minutes of speech.
const MAX_TOTAL_SAMPLES: usize = 16 * 1024 * 1024;
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
    total_samples: usize,
}

impl AudioCache {
    pub fn new(cache_dir: Option<&Path>) -> Self {
        let path = cache_dir.map(|d| d.join("piper-audio.kcache"));
        let mut cache = Self {
            map: HashMap::new(),
            clock: 0,
            path,
            dirty: false,
            total_samples: 0,
        };
        cache.load();
        cache
    }

    /// Build a cache key from the fields that change model output.
    ///
    /// DSP-only fields (pitch, volume, stretch) are excluded so one entry
    /// serves every rate, pitch, and volume. So is character mode: it decides
    /// how an utterance is split into chunks, and the key is built per chunk,
    /// so by this point it can no longer change the audio. Leaving it out
    /// means a letter spelled and the same letter spoken share one entry.
    /// `scales` is the inference parameter multipliers, already rounded, and
    /// `lexicon_rev` is 0 unless the chunk contains a pronunciation override,
    /// so editing the lexicon only invalidates the chunks it affects.
    pub fn key(voice: &str, ipa: bool, scales: &str, lexicon_rev: u64,
               text: &str) -> String {
        format!("{voice}|{}|{scales}|{lexicon_rev}|{text}", ipa as u8)
    }

    /// Drop everything, in memory and on disk. Used when the user asks for
    /// the prepared audio to be rebuilt.
    pub fn clear(&mut self) {
        self.map.clear();
        self.total_samples = 0;
        self.dirty = false;
        if let Some(path) = &self.path {
            let _ = std::fs::remove_file(path);
        }
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
        let added = samples.len();
        if let Some(previous) = self.map.insert(key, Entry { samples, used: clock }) {
            self.total_samples -= previous.samples.len();
        }
        self.total_samples += added;
        self.dirty = true;
        if self.map.len() > MAX_ENTRIES || self.total_samples > MAX_TOTAL_SAMPLES {
            self.evict();
        }
    }

    fn evict(&mut self) {
        // Drop least-recently-used entries until both budgets are back under
        // 90%, so eviction runs in batches rather than on every insert.
        let entry_target = MAX_ENTRIES / 10 * 9;
        let sample_target = MAX_TOTAL_SAMPLES / 10 * 9;
        let mut by_use: Vec<(u64, String)> = self
            .map
            .iter()
            .map(|(key, entry)| (entry.used, key.clone()))
            .collect();
        by_use.sort_unstable_by_key(|(used, _)| *used);
        for (_, key) in by_use {
            if self.map.len() <= entry_target && self.total_samples <= sample_target {
                break;
            }
            if let Some(entry) = self.map.remove(&key) {
                self.total_samples -= entry.samples.len();
            }
        }
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
            self.total_samples += samples.len();
            self.map.insert(key, Entry { samples, used: clock });
        }
        // A file written by a build with larger budgets must not blow past
        // this one's.
        if self.map.len() > MAX_ENTRIES || self.total_samples > MAX_TOTAL_SAMPLES {
            self.evict();
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
        // The same string spoken as text and as IPA are different sounds.
        assert_ne!(a, AudioCache::key("v", true, plain, 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, "1.30,1.00,1.00", 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, "1.00,1.20,1.00", 0, "a"));
        assert_ne!(a, AudioCache::key("v", false, plain, 9, "a"));
    }

    #[test]
    fn clear_empties_memory_and_disk() {
        let dir = std::env::temp_dir().join("piper_cache_clear_test");
        let _ = std::fs::create_dir_all(&dir);
        let file = dir.join("piper-audio.kcache");
        let _ = std::fs::remove_file(&file);
        let mut c = AudioCache::new(Some(&dir));
        c.put("hello".to_string(), vec![0.5]);
        c.save();
        assert!(file.exists());
        c.clear();
        assert!(c.get("hello").is_none());
        assert!(!file.exists());
        // A cleared cache saves nothing rather than rewriting what it had.
        c.save();
        assert!(!file.exists());
    }

    #[test]
    fn does_not_cache_oversize() {
        let mut c = AudioCache::new(None);
        let k = "big".to_string();
        c.put(k.clone(), vec![0.0; MAX_CACHEABLE_SAMPLES + 1]);
        assert!(c.get(&k).is_none());
    }

    #[test]
    fn eviction_respects_the_audio_budget() {
        let mut c = AudioCache::new(None);
        // Entries far too large to all fit; the count budget alone would
        // never notice.
        let big = vec![0.0f32; MAX_CACHEABLE_SAMPLES];
        let needed = MAX_TOTAL_SAMPLES / MAX_CACHEABLE_SAMPLES + 5;
        for i in 0..needed {
            c.put(format!("k{i}"), big.clone());
        }
        assert!(c.map.len() < needed, "nothing was evicted");
        assert!(c.total_samples <= MAX_TOTAL_SAMPLES, "over the audio budget");
        // The most recent entry survives.
        assert!(c.contains(&format!("k{}", needed - 1)));
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
