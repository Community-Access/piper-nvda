"""Which voices this add-on can actually speak.

A Piper voice config declares how its phonemes were produced. Nearly all
published voices use espeak-ng, which this add-on bundles, and voices trained
before the field existed are espeak voices too. A handful use a phonemizer
this add-on does not include (pinyin, hebrew, japanese, thai); feeding those
models espeak's IPA produces confident nonsense rather than an error, so they
are refused up front instead.

`text` voices need no phonemizer at all: their phonemes are the code points of
the text, which the helper handles directly.

No NVDA or wx dependency, so this is unit tested directly.
"""

import json

#: Values of `phoneme_type` the helper can synthesize.
SUPPORTED = frozenset({"espeak", "text"})

#: What the phonemizers named in unsupported voices are, for error messages.
_NAMES = {
    "pinyin": "Chinese pinyin",
    "hebrew": "Hebrew",
    "japanese": "Japanese",
    "thai": "Thai",
}

DEFAULT = "espeak"


def phoneme_type(config_path):
    """The `phoneme_type` of a voice config file.

    Missing files and damaged JSON read as the default, so a voice is never
    rejected because its config could not be parsed; the helper will report
    the real problem when it tries to load the model.
    """
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        return DEFAULT
    if not isinstance(config, dict):
        return DEFAULT
    value = config.get("phoneme_type")
    return value if isinstance(value, str) and value else DEFAULT


def is_supported(config_path):
    return phoneme_type(config_path) in SUPPORTED


def describe(name):
    """A human name for a phonemizer, for messages shown to the user."""
    return _NAMES.get(name, name)


def unsupported_message(voice_name, name):
    """The explanation shown when a voice cannot be used."""
    # Translators: {voice} is a voice name, {phonemizer} a language-specific
    # text-to-phoneme system this add-on does not include.
    return _("{voice} needs the {phonemizer} text processing that this add-on "
             "does not include, so it cannot be used. Please choose another "
             "voice.").format(voice=voice_name, phonemizer=describe(name))
