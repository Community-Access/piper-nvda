//! Framing and message types for the driver <-> helper stdio protocol (v1).
//!
//! Frame layout: u32 LE payload length, u8 message type, payload.
//! Control payloads are UTF-8 JSON. AUDIO payload is u16 LE JSON header
//! length, JSON header, then raw i16 LE PCM.

use serde::{Deserialize, Serialize};
use std::io::{self, Read, Write};

pub const PROTOCOL_VERSION: u32 = 1;

pub mod msg_type {
    pub const HELLO: u8 = 0x01;
    pub const SPEAK: u8 = 0x02;
    pub const CANCEL: u8 = 0x03;
    pub const LOAD_VOICE: u8 = 0x04;
    pub const PING: u8 = 0x05;
    pub const SHUTDOWN: u8 = 0x06;
    pub const PLAY_SAMPLE: u8 = 0x07;
    pub const SET_LEXICON: u8 = 0x08;
    pub const AUDIO: u8 = 0x81;
    pub const MARKER: u8 = 0x82;
    pub const DONE: u8 = 0x83;
    pub const ERROR: u8 = 0x84;
    pub const PONG: u8 = 0x85;
    pub const LOG: u8 = 0x86;
}

/// Hard cap so a corrupt length prefix cannot allocate gigabytes.
const MAX_FRAME: u32 = 32 * 1024 * 1024;

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Hello {
    pub version: u32,
    pub role: String,
    pub model_loaded: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Segment {
    pub text: String,
    /// Absolute path to this voice's .onnx model. The espeak language and
    /// sample rate are read from the sibling .onnx.json config.
    pub model_path: String,
    #[serde(default)]
    pub sid: i64,
    /// WSOLA time-stretch speed factor (1.0 = none, >1 = faster). Rate is
    /// applied entirely here so cached audio is rate-independent.
    #[serde(default = "one")]
    pub stretch: f32,
    #[serde(default)]
    pub pitch_semis: f32,
    #[serde(default = "one")]
    pub volume: f32,
    #[serde(default)]
    pub break_ms_before: u32,
    #[serde(default)]
    pub indexes_before: Vec<i64>,
    #[serde(default)]
    pub char_mode: bool,
    /// Expressiveness multiplier applied to the model's noise scales.
    /// 1.0 keeps the voice's trained default.
    #[serde(default = "one")]
    pub variance: f32,
}

fn one() -> f32 {
    1.0
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PlaySample {
    /// Path to an mp3 file to decode and play (used for voice demos).
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Speak {
    pub utterance_id: u64,
    pub segments: Vec<Segment>,
    #[serde(default)]
    pub indexes_after: Vec<i64>,
}

/// A replacement pronunciation lexicon. `rev` changes on every user edit.
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SetLexicon {
    pub rev: u64,
    #[serde(default)]
    pub entries: std::collections::HashMap<String, String>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoadVoice {
    pub voice: String,
    /// Expressiveness the cache should be warmed at (see Segment::variance).
    #[serde(default = "one")]
    pub variance: f32,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Marker {
    pub utterance_id: u64,
    pub index: i64,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Done {
    pub utterance_id: u64,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ErrorMsg {
    pub code: String,
    pub message: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LogMsg {
    pub level: String,
    pub message: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioHeader {
    pub utterance_id: u64,
    pub seq: u64,
}

pub fn read_frame<R: Read>(r: &mut R) -> io::Result<(u8, Vec<u8>)> {
    let mut len_buf = [0u8; 4];
    r.read_exact(&mut len_buf)?;
    let len = u32::from_le_bytes(len_buf);
    if len == 0 || len > MAX_FRAME {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("bad frame length {len}"),
        ));
    }
    let mut ty = [0u8; 1];
    r.read_exact(&mut ty)?;
    let mut payload = vec![0u8; (len - 1) as usize];
    r.read_exact(&mut payload)?;
    Ok((ty[0], payload))
}

pub fn write_frame<W: Write>(w: &mut W, ty: u8, payload: &[u8]) -> io::Result<()> {
    let len = (payload.len() + 1) as u32;
    w.write_all(&len.to_le_bytes())?;
    w.write_all(&[ty])?;
    w.write_all(payload)?;
    w.flush()
}

pub fn write_json<W: Write, T: Serialize>(w: &mut W, ty: u8, value: &T) -> io::Result<()> {
    let payload = serde_json::to_vec(value)?;
    write_frame(w, ty, &payload)
}

pub fn write_audio<W: Write>(
    w: &mut W,
    utterance_id: u64,
    seq: u64,
    pcm: &[i16],
) -> io::Result<()> {
    let header = serde_json::to_vec(&AudioHeader { utterance_id, seq })?;
    let mut payload = Vec::with_capacity(2 + header.len() + pcm.len() * 2);
    payload.extend_from_slice(&(header.len() as u16).to_le_bytes());
    payload.extend_from_slice(&header);
    for s in pcm {
        payload.extend_from_slice(&s.to_le_bytes());
    }
    write_frame(w, msg_type::AUDIO, &payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_roundtrip() {
        let mut buf = Vec::new();
        write_frame(&mut buf, msg_type::PING, b"{}").unwrap();
        let (ty, payload) = read_frame(&mut buf.as_slice()).unwrap();
        assert_eq!(ty, msg_type::PING);
        assert_eq!(payload, b"{}");
    }

    #[test]
    fn frame_roundtrip_large() {
        let big = vec![0xABu8; 1024 * 1024];
        let mut buf = Vec::new();
        write_frame(&mut buf, msg_type::AUDIO, &big).unwrap();
        let (ty, payload) = read_frame(&mut buf.as_slice()).unwrap();
        assert_eq!(ty, msg_type::AUDIO);
        assert_eq!(payload.len(), big.len());
    }

    #[test]
    fn frame_rejects_oversize() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&u32::MAX.to_le_bytes());
        buf.push(0);
        assert!(read_frame(&mut buf.as_slice()).is_err());
    }

    #[test]
    fn speak_json_roundtrip() {
        let json = r#"{
            "utteranceId": 7,
            "segments": [{
                "text": "Hello", "modelPath": "C:/voices/x.onnx",
                "indexesBefore": [3]
            }],
            "indexesAfter": [4]
        }"#;
        let speak: Speak = serde_json::from_str(json).unwrap();
        assert_eq!(speak.utterance_id, 7);
        assert_eq!(speak.segments[0].model_path, "C:/voices/x.onnx");
        assert_eq!(speak.segments[0].indexes_before, vec![3]);
        assert_eq!(speak.segments[0].stretch, 1.0);
        assert_eq!(speak.segments[0].volume, 1.0);
        assert_eq!(speak.segments[0].variance, 1.0);
        assert_eq!(speak.segments[0].sid, 0);
        assert!(!speak.segments[0].char_mode);
        assert_eq!(speak.indexes_after, vec![4]);
    }

    #[test]
    fn audio_frame_layout() {
        let mut buf = Vec::new();
        write_audio(&mut buf, 1, 2, &[100, -100]).unwrap();
        let (ty, payload) = read_frame(&mut buf.as_slice()).unwrap();
        assert_eq!(ty, msg_type::AUDIO);
        let hlen = u16::from_le_bytes([payload[0], payload[1]]) as usize;
        let header: AudioHeader = serde_json::from_slice(&payload[2..2 + hlen]).unwrap();
        assert_eq!(header.utterance_id, 1);
        assert_eq!(header.seq, 2);
        let pcm = &payload[2 + hlen..];
        assert_eq!(pcm.len(), 4);
        assert_eq!(i16::from_le_bytes([pcm[0], pcm[1]]), 100);
    }
}
