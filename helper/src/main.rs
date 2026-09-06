mod cache;
mod config;
mod dsp;
mod espeak;
mod lexicon;
mod mp3;
mod protocol;
mod server;
mod synth;
mod text;

use anyhow::{bail, Context, Result};
use std::path::PathBuf;
use std::time::Instant;

struct Args {
    espeak_dll: PathBuf,
    espeak_data: PathBuf,
    threads: usize,
    model: Option<PathBuf>,
    say: Option<String>,
    out: PathBuf,
    bench: bool,
    cache_dir: Option<PathBuf>,
}

fn parse_args() -> Result<Args> {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from))
        .unwrap_or_default();
    let assets = ["../../../assets", "../../assets", "assets"]
        .iter()
        .map(|rel| exe_dir.join(rel))
        .find(|p| p.join("espeak-ng/eSpeak NG/libespeak-ng.dll").exists())
        .unwrap_or_else(|| PathBuf::from("assets"));

    let mut args = Args {
        espeak_dll: assets.join("espeak-ng/eSpeak NG/libespeak-ng.dll"),
        espeak_data: assets.join("espeak-ng/eSpeak NG"),
        threads: default_threads(),
        model: None,
        say: None,
        out: PathBuf::from("out.wav"),
        bench: false,
        cache_dir: None,
    };
    let mut it = std::env::args().skip(1);
    while let Some(flag) = it.next() {
        let mut value = |name: &str| -> Result<String> {
            it.next().with_context(|| format!("missing value for {name}"))
        };
        match flag.as_str() {
            "--espeak-dll" => args.espeak_dll = value("--espeak-dll")?.into(),
            "--espeak-data" => args.espeak_data = value("--espeak-data")?.into(),
            "--threads" => args.threads = value("--threads")?.parse()?,
            "--model" => args.model = Some(value("--model")?.into()),
            "--say" => args.say = Some(value("--say")?),
            "--out" => args.out = value("--out")?.into(),
            "--cache-dir" => args.cache_dir = Some(value("--cache-dir")?.into()),
            "--bench" => args.bench = true,
            other => bail!("unknown flag {other}"),
        }
    }
    Ok(args)
}

fn default_threads() -> usize {
    std::thread::available_parallelism()
        .map(|n| (n.get() / 2).max(2))
        .unwrap_or(2)
}

fn main() -> Result<()> {
    let args = parse_args()?;
    if args.bench {
        return bench(&args);
    }
    if args.say.is_some() {
        return say(&args);
    }
    server::run(&server::Paths {
        espeak_dll: args.espeak_dll,
        espeak_data: args.espeak_data,
        threads: args.threads,
        cache_dir: args.cache_dir,
    })
}

fn synth_all(
    engine: &mut synth::Engine,
    phon: &mut espeak::Phonemizer,
    model: &std::path::Path,
    text_in: &str,
) -> Result<Vec<f32>> {
    let voice = engine.espeak_voice(model)?;
    phon.set_language(&voice)?;
    let mut all = Vec::new();
    for chunk in text::split_clauses(text_in) {
        let ipa = phon.to_ipa(&chunk)?;
        if let Some(s) = engine.synth(model, &ipa, 0, 1.0)? {
            let out_sr = server::OUTPUT_SR as u32;
            let resampled = if s.sample_rate == out_sr {
                s.samples
            } else {
                dsp::linear_resample(&s.samples, s.sample_rate as f32 / out_sr as f32)
            };
            all.extend(resampled);
        }
    }
    Ok(all)
}

fn say(args: &Args) -> Result<()> {
    let model = args.model.clone().context("--say requires --model")?;
    let mut engine = synth::Engine::new(args.threads);
    let mut phon = espeak::Phonemizer::new(&args.espeak_dll, &args.espeak_data)?;
    let text_in = args.say.as_deref().unwrap();
    let start = Instant::now();
    let audio = synth_all(&mut engine, &mut phon, &model, text_in)?;
    eprintln!(
        "synthesized {:.2}s of audio in {} ms",
        audio.len() as f32 / server::OUTPUT_SR as f32,
        start.elapsed().as_millis()
    );
    write_wav(&args.out, &dsp::to_i16(&audio, 1.0))?;
    eprintln!("wrote {}", args.out.display());
    Ok(())
}

fn bench(args: &Args) -> Result<()> {
    let model = args.model.clone().context("--bench requires --model")?;
    let mut engine = synth::Engine::new(args.threads);
    let mut phon = espeak::Phonemizer::new(&args.espeak_dll, &args.espeak_data)?;
    let _ = synth_all(&mut engine, &mut phon, &model, "warm up")?;
    for text_in in ["a", "Edit.", "File explorer window.",
                    "The quick brown fox jumps over the lazy dog near the river bank."] {
        let mut times = Vec::new();
        let mut samples = 0;
        for _ in 0..5 {
            let start = Instant::now();
            let a = synth_all(&mut engine, &mut phon, &model, text_in)?;
            times.push(start.elapsed().as_millis());
            samples = a.len();
        }
        times.sort();
        eprintln!("case {:?}: median {} ms, audio {:.2}s", text_in,
                  times[times.len() / 2], samples as f32 / server::OUTPUT_SR as f32);
    }
    Ok(())
}

fn write_wav(path: &std::path::Path, pcm: &[i16]) -> Result<()> {
    use std::io::Write;
    let mut f = std::fs::File::create(path)?;
    let data_len = (pcm.len() * 2) as u32;
    let sr = server::OUTPUT_SR as u32;
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_len).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?;
    f.write_all(&sr.to_le_bytes())?;
    f.write_all(&(sr * 2).to_le_bytes())?;
    f.write_all(&2u16.to_le_bytes())?;
    f.write_all(&16u16.to_le_bytes())?;
    f.write_all(b"data")?;
    f.write_all(&data_len.to_le_bytes())?;
    for s in pcm {
        f.write_all(&s.to_le_bytes())?;
    }
    Ok(())
}
