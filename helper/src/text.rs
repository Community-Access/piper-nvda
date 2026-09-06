//! Text chunking. Long inputs are split into clause-sized pieces so the
//! first audio arrives quickly and cancel has fine granularity, while
//! punctuation is kept attached to its clause (the model uses it for prosody).

/// Hard cap per chunk in characters; far below the 510-phoneme model limit
/// for any real language.
pub const MAX_CHUNK_CHARS: usize = 300;
/// Chunks shorter than this are merged with the following clause to avoid
/// choppy prosody on fragments like "Dr." or "1.".
const MIN_CHUNK_CHARS: usize = 4;

const CLAUSE_ENDINGS: &[char] = &['.', '!', '?', ';', ':', ',', '\u{2026}', '\n'];

pub fn split_clauses(text: &str) -> Vec<String> {
    let mut clauses: Vec<String> = Vec::new();
    let mut current = String::new();
    for ch in text.chars() {
        current.push(ch);
        if CLAUSE_ENDINGS.contains(&ch) {
            push_clause(&mut clauses, &mut current);
        }
    }
    push_clause(&mut clauses, &mut current);

    // Merge undersized fragments forward.
    let mut merged: Vec<String> = Vec::new();
    for clause in clauses {
        match merged.last_mut() {
            Some(last) if last.chars().count() < MIN_CHUNK_CHARS
                || clause.chars().count() < MIN_CHUNK_CHARS =>
            {
                last.push(' ');
                last.push_str(&clause);
            }
            _ => merged.push(clause),
        }
    }

    // Hard-split anything still too long on whitespace.
    let mut out = Vec::new();
    for clause in merged {
        if clause.chars().count() <= MAX_CHUNK_CHARS {
            out.push(clause);
            continue;
        }
        let mut piece = String::new();
        for word in clause.split_whitespace() {
            if !piece.is_empty()
                && piece.chars().count() + word.chars().count() + 1 > MAX_CHUNK_CHARS
            {
                out.push(std::mem::take(&mut piece));
            }
            if !piece.is_empty() {
                piece.push(' ');
            }
            piece.push_str(word);
        }
        if !piece.is_empty() {
            out.push(piece);
        }
    }
    out
}

/// Target size for the very first chunk of an utterance. Keeping it short
/// gets first audio to the player sooner (helps typing echo and say-all
/// start latency); later chunks synthesize while it plays.
const FIRST_CHUNK_TARGET_CHARS: usize = 40;

/// Like `split_clauses`, but additionally splits the first clause at a word
/// boundary near FIRST_CHUNK_TARGET_CHARS so streaming begins quickly.
pub fn split_streaming(text: &str) -> Vec<String> {
    let clauses = split_clauses(text);
    if clauses.is_empty() {
        return clauses;
    }
    let first = &clauses[0];
    if first.chars().count() <= FIRST_CHUNK_TARGET_CHARS {
        return clauses;
    }
    // Split the first clause once, at the last word boundary before the target.
    let mut head = String::new();
    let mut tail = String::new();
    for word in first.split_whitespace() {
        if tail.is_empty() && head.chars().count() + word.chars().count() + 1
            <= FIRST_CHUNK_TARGET_CHARS
        {
            if !head.is_empty() {
                head.push(' ');
            }
            head.push_str(word);
        } else {
            if !tail.is_empty() {
                tail.push(' ');
            }
            tail.push_str(word);
        }
    }
    let mut out = Vec::with_capacity(clauses.len() + 1);
    if head.is_empty() {
        return clauses;
    }
    out.push(head);
    if !tail.is_empty() {
        out.push(tail);
    }
    out.extend_from_slice(&clauses[1..]);
    out
}

fn push_clause(clauses: &mut Vec<String>, current: &mut String) {
    let trimmed = current.trim();
    if !trimmed.is_empty() {
        clauses.push(trimmed.to_string());
    }
    current.clear();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_on_sentence_punctuation() {
        let chunks = split_clauses("Hello there. How are you today? Fine, thanks.");
        assert_eq!(
            chunks,
            vec!["Hello there.", "How are you today?", "Fine,", "thanks."]
        );
    }

    #[test]
    fn keeps_punctuation_attached() {
        let chunks = split_clauses("One, two.");
        assert!(chunks.iter().all(|c| c.ends_with([',', '.'])));
    }

    #[test]
    fn empty_and_whitespace() {
        assert!(split_clauses("").is_empty());
        assert!(split_clauses("   \n  ").is_empty());
    }

    #[test]
    fn long_unpunctuated_text_is_split() {
        let long = "word ".repeat(300);
        let chunks = split_clauses(&long);
        assert!(chunks.len() > 1);
        assert!(chunks.iter().all(|c| c.chars().count() <= MAX_CHUNK_CHARS));
    }

    #[test]
    fn merges_tiny_fragments() {
        let chunks = split_clauses("Dr. Smith arrived.");
        assert_eq!(chunks, vec!["Dr. Smith arrived."]);
    }

    #[test]
    fn streaming_splits_long_first_clause() {
        let text = "The quick brown fox jumps over the lazy dog near the \
                    river bank and keeps running for a long time";
        let plain = split_clauses(text);
        assert_eq!(plain.len(), 1);
        let streamed = split_streaming(text);
        assert!(streamed.len() >= 2);
        assert!(streamed[0].chars().count() <= FIRST_CHUNK_TARGET_CHARS);
        // Reassembling preserves the words.
        assert_eq!(streamed.join(" ").split_whitespace().count(),
                   text.split_whitespace().count());
    }

    #[test]
    fn streaming_leaves_short_text_alone() {
        assert_eq!(split_streaming("Edit."), vec!["Edit."]);
        assert!(split_streaming("").is_empty());
    }
}
