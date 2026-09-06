//! Spoken names for characters, for the last case where espeak-ng gives us
//! nothing.
//!
//! Sent a punctuation character on its own, espeak-ng treats it as clause
//! punctuation and produces no phonemes at all: a full stop, a comma, a
//! bracket, a quote, a space and fifteen others all phonemize to nothing, so
//! the synthesizer would simply be silent for them. Letters and digits are
//! fine, and so are symbols espeak has a word for, such as "%" and "@".
//!
//! NVDA normally substitutes its own name for a symbol before the text
//! reaches a synthesizer, and the driver asks it to do exactly that for
//! single characters. This table is what stands behind that: if a character
//! still arrives with no pronunciation, it is spoken rather than dropped.
//!
//! The names are NVDA's own, from `source/locale/en/symbols.dic`, so they
//! match what other synthesizers say. They are English, which is the cost of
//! being a fallback rather than the main path.

/// The spoken name for a chunk that is exactly one character, if there is one.
pub fn name_of(text: &str) -> Option<&'static str> {
    let mut chars = text.chars();
    let (first, rest) = (chars.next()?, chars.next());
    if rest.is_some() {
        return None;
    }
    match first {
        ' ' => Some("space"),
        '!' => Some("bang"),
        '"' => Some("quote"),
        '$' => Some("dollar"),
        '%' => Some("percent"),
        '&' => Some("and"),
        '\'' => Some("tick"),
        '(' => Some("left paren"),
        ')' => Some("right paren"),
        '*' => Some("star"),
        '+' => Some("plus"),
        ',' => Some("comma"),
        '-' => Some("dash"),
        '.' => Some("dot"),
        '/' => Some("slash"),
        ':' => Some("colon"),
        ';' => Some("semi"),
        '<' => Some("less"),
        '=' => Some("equals"),
        '>' => Some("greater"),
        '?' => Some("question"),
        '@' => Some("at"),
        '[' => Some("left bracket"),
        ']' => Some("right bracket"),
        '^' => Some("caret"),
        '_' => Some("line"),
        '`' => Some("graav"),
        '{' => Some("left brace"),
        '|' => Some("bar"),
        '}' => Some("right brace"),
        '~' => Some("tilda"),
        '–' => Some("en dash"),
        '—' => Some("em dash"),
        '‘' => Some("left tick"),
        '’' => Some("right tick"),
        '“' => Some("left quote"),
        '”' => Some("right quote"),
        '…' => Some("dot dot dot"),
        '•' => Some("bullet"),
        '°' => Some("degrees"),
        '©' => Some("copyright"),
        '®' => Some("registered"),
        '™' => Some("trademark"),
        '€' => Some("euro"),
        '£' => Some("pound"),
        '¥' => Some("yen"),
        '¢' => Some("cents"),
        '§' => Some("section"),
        '¶' => Some("paragraph marker"),
        '×' => Some("times"),
        '÷' => Some("divide by"),
        '±' => Some("plus or Minus"),
        '≠' => Some("not equal to"),
        '≤' => Some("less- than or equal to"),
        '≥' => Some("greater-than or equal to"),
        '→' => Some("right arrow"),
        '←' => Some("left arrow"),
        '↑' => Some("up arrow"),
        '↓' => Some("down arrow"),
        '½' => Some("one half"),
        '¼' => Some("one quarter"),
        '¾' => Some("three quarters"),
        '«' => Some("double left pointing angle bracket"),
        '»' => Some("double right pointing angle bracket"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_the_characters_espeak_drops() {
        // These phonemize to nothing on their own; see
        // examples/espeak_charmode.rs.
        for ch in [
            " ", "\"", "'", "(", ")", ",", "-", ".", ";", "<", ">", "?", "[",
            "]", "^", "_", "`", "{", "|", "}",
        ] {
            assert!(name_of(ch).is_some(), "no name for {ch:?}");
        }
        assert_eq!(name_of("."), Some("dot"));
        assert_eq!(name_of(" "), Some("space"));
    }

    #[test]
    fn only_single_characters_have_names() {
        assert_eq!(name_of(""), None);
        assert_eq!(name_of(".."), None);
        assert_eq!(name_of("dot"), None);
        // Letters and digits speak for themselves.
        assert_eq!(name_of("a"), None);
        assert_eq!(name_of("7"), None);
    }
}
