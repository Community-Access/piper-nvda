//! User pronunciation lexicon: whole-word IPA overrides applied before
//! phonemization.
//!
//! Neural voices inherit espeak-ng's guesses for names, acronyms, and loan
//! words, and there is no way to retrain a voice to fix one. The driver sends
//! a word -> IPA map; text is split into runs so overridden words bypass
//! espeak while the surrounding text is phonemized normally.

use std::collections::HashMap;

/// One run of a chunk: text to phonemize, or IPA to use verbatim.
pub enum Piece<'a> {
    Plain(&'a str),
    Ipa(&'a str),
}

#[derive(Default)]
pub struct Lexicon {
    rev: u64,
    map: HashMap<String, String>,
}

/// Characters that can appear inside a lexicon word. Hyphens and apostrophes
/// are included so entries like "e-mail" or "o'clock" can be overridden.
fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '\'' || c == '\u{2019}' || c == '-'
}

impl Lexicon {
    pub fn new() -> Self {
        Self::default()
    }

    /// Replace the whole lexicon. `rev` changes whenever the user edits it,
    /// and is folded into cache keys of affected chunks.
    pub fn set(&mut self, rev: u64, entries: HashMap<String, String>) {
        self.map = entries
            .into_iter()
            .filter(|(word, ipa)| !word.trim().is_empty() && !ipa.trim().is_empty())
            .map(|(word, ipa)| (word.trim().to_lowercase(), ipa.trim().to_string()))
            .collect();
        self.rev = rev;
    }

    pub fn rev(&self) -> u64 {
        self.rev
    }

    /// Split `text` into plain and overridden runs. Returns a single Plain
    /// piece when nothing matches, so the common path stays allocation-light.
    pub fn split<'a>(&'a self, text: &'a str) -> Vec<Piece<'a>> {
        if self.map.is_empty() {
            return vec![Piece::Plain(text)];
        }
        let mut pieces = Vec::new();
        let mut plain_start = 0;
        let mut word_start = None;
        // Push a byte range as a Plain piece if it is non-empty.
        let push_plain = |pieces: &mut Vec<Piece<'a>>, from: usize, to: usize| {
            if to > from {
                pieces.push(Piece::Plain(&text[from..to]));
            }
        };
        for (idx, ch) in text.char_indices() {
            if is_word_char(ch) {
                if word_start.is_none() {
                    word_start = Some(idx);
                }
                continue;
            }
            if let Some(start) = word_start.take() {
                if let Some(ipa) = self.lookup(&text[start..idx]) {
                    push_plain(&mut pieces, plain_start, start);
                    pieces.push(Piece::Ipa(ipa));
                    plain_start = idx;
                }
            }
        }
        if let Some(start) = word_start {
            if let Some(ipa) = self.lookup(&text[start..]) {
                push_plain(&mut pieces, plain_start, start);
                pieces.push(Piece::Ipa(ipa));
                plain_start = text.len();
            }
        }
        push_plain(&mut pieces, plain_start, text.len());
        pieces
    }

    fn lookup(&self, word: &str) -> Option<&str> {
        self.map.get(&word.to_lowercase()).map(|s| s.as_str())
    }
}

/// True if any piece is an override (the chunk's audio depends on the rev).
pub fn has_override(pieces: &[Piece]) -> bool {
    pieces.iter().any(|p| matches!(p, Piece::Ipa(_)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lex(pairs: &[(&str, &str)]) -> Lexicon {
        let mut l = Lexicon::new();
        l.set(
            7,
            pairs
                .iter()
                .map(|(a, b)| (a.to_string(), b.to_string()))
                .collect(),
        );
        l
    }

    fn rendered(l: &Lexicon, text: &str) -> String {
        l.split(text)
            .iter()
            .map(|p| match p {
                Piece::Plain(s) => format!("[{s}]"),
                Piece::Ipa(s) => format!("<{s}>"),
            })
            .collect()
    }

    #[test]
    fn empty_lexicon_is_one_plain_piece() {
        let l = Lexicon::new();
        assert_eq!(rendered(&l, "hello there"), "[hello there]");
        assert!(!has_override(&l.split("hello there")));
    }

    #[test]
    fn replaces_whole_words_only() {
        let l = lex(&[("nvda", "ɛnviːdiːˈeɪ")]);
        assert_eq!(rendered(&l, "use NVDA now"), "[use ]<ɛnviːdiːˈeɪ>[ now]");
        // A substring inside a longer word must not match.
        assert_eq!(rendered(&l, "nvdaish"), "[nvdaish]");
    }

    #[test]
    fn matches_case_insensitively_and_at_string_edges() {
        let l = lex(&[("piper", "ˈpaɪpɚ")]);
        assert_eq!(rendered(&l, "Piper"), "<ˈpaɪpɚ>");
        assert_eq!(rendered(&l, "piper, hi"), "<ˈpaɪpɚ>[, hi]");
        assert!(has_override(&l.split("Piper")));
    }

    #[test]
    fn keeps_punctuation_with_surrounding_text() {
        let l = lex(&[("b", "biː")]);
        assert_eq!(rendered(&l, "a, b. c"), "[a, ]<biː>[. c]");
    }

    #[test]
    fn ignores_blank_entries() {
        let l = lex(&[("  ", "x"), ("word", "   ")]);
        assert_eq!(rendered(&l, "word here"), "[word here]");
    }

    #[test]
    fn handles_multibyte_text() {
        let l = lex(&[("café", "kaˈfeɪ")]);
        assert_eq!(rendered(&l, "un café ici"), "[un ]<kaˈfeɪ>[ ici]");
    }
}
