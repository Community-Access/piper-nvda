# Piper Neural Voices - User Guide

This guide is written for screen reader users. It uses plain text and clear
headings so you can navigate by heading and read comfortably.

## What this add-on does

It adds a new synthesizer, "Piper Neural Voices", to NVDA. Piper voices sound
natural and run entirely on your computer. You choose which voices to
download from a built-in manager, and you can hear a short demo of each voice
before downloading it.

## System requirements

- NVDA 2025.1 or later (including 64-bit NVDA 2026.1 and later).
- Windows 10 (64-bit) or Windows 11.
- About 60 to 120 MB of disk per voice you download. The add-on itself is
  small; voices are downloaded on demand.
- An internet connection is needed only while downloading voices and demos.

## Installing the add-on

1. Open the NVDA menu with NVDA+N.
2. Go to Tools, then Add-on Store (on older NVDA, "Manage add-ons").
3. Either find "Piper Neural Voices" in the store, or choose "Install from
   external source" and select the `.nvda-addon` file you downloaded.
4. Confirm the installation and restart NVDA when prompted.

## Downloading your first voice

1. Open the NVDA menu (NVDA+N), Tools, "Piper voice manager".
2. The manager loads the list of available voices. This may take a few seconds
   the first time while it downloads the voice catalog.
3. Use the Language combo box to filter by language, then Tab to the Voices
   list and choose a voice with the arrow keys.
4. Press the "Play demo" button to hear a short sample. Press "Stop demo" to
   stop it. Demos work even if Piper is not your current synthesizer.
5. Press "Download" to install the selected voice. A progress dialog reports
   percentage complete and can be cancelled.
6. Repeat for as many voices as you like. Installed voices are marked in the
   list.

You can reopen the voice manager any time from the Tools menu to add or
remove voices.

## Choosing Piper as your synthesizer

1. Open NVDA menu (NVDA+N), Preferences, Settings.
2. Select the Speech category.
3. In the Synthesizer field, choose "Piper Neural Voices". (You can also press
   the "Change" button next to the synthesizer name.)
4. Use the Voice field to pick any voice you have downloaded.

## Settings

All settings are in the Speech settings panel and in the synthesizer settings
ring (NVDA+Control+Left/Right to move between settings, NVDA+Control+Up/Down to
change a value).

- **Voice**: any Piper voice you have downloaded.
- **Variant**: for multi-speaker voices, selects which speaker to use. For
  single-speaker voices this is just "Default".
- **Rate**: speech speed. It is applied by time-stretching, so it never
  changes the pitch.
- **Rate boost**: extends the top speed for people who read very fast.
- **Pitch**: raises or lowers the voice.
- **Volume**: loudness of the voice.
- **Expressiveness**: how much the voice varies its delivery. 50 is the
  voice exactly as it was trained. Lower values are flatter and steadier,
  which many people find easier to follow at high speed; higher values are
  more animated. Changing this re-prepares the cached words in the
  background, so echo stays instant.

## Automatic language switching

If you turn on "Automatic language switching" in NVDA's Speech settings, and a
document marks its language, Piper will use a downloaded voice that matches
that language when one is available. Download at least one voice per language
you want this to work for.

If you have more than one voice for a language, you can say which one to use.
In the voice manager, press "Language voices", choose a language, and press
"Change voice". Choosing "Automatic" goes back to picking the first installed
voice for that language. An assignment for a language without a region (for
example Portuguese) also covers its regional variants (Brazilian Portuguese)
unless you assign those separately.

## Fixing how a word is pronounced

Neural voices work from phonemes, and the phonemes are guessed by espeak-ng.
Names, acronyms, and words borrowed from other languages are the ones it
usually gets wrong, and no amount of retraining on your side can fix that.

In the voice manager, press "Pronunciations" to give a word the exact
phonemes it should be spoken with:

1. Press "Add", type the word, and type its pronunciation as IPA phonemes.
   For example, NVDA is spoken correctly as `ɛnviːdiːˈeɪ`.
2. Press "Preview" to hear the entry before you keep it.
3. Press "Save".

Entries apply to whole words only, so an entry for "read" never changes
"reader". Matching ignores capitalization. This is separate from NVDA's own
speech dictionaries, which replace text before it reaches the synthesizer;
use a dictionary to change what is said, and this to change how it sounds.

Entries take effect immediately, in every voice and language. They are stored
in `lexicon.json` (see "Where files are stored"), so they can be backed up or
shared as an ordinary file.

## Using voices you already have

If you have used another Piper-based add-on, its voices are ordinary Piper
models and this add-on can reuse them instead of downloading them again. In
the voice manager press "Import voices". Voices installed by Sonata Neural
Voices and by Dengjen Neural Voices are found automatically. Check the ones
you want and press "Import"; the files are copied, so the other add-on keeps
working.

"Install from file" installs a voice from a `.tar.gz` voice archive or from a
`.onnx` model that has its `.onnx.json` file beside it. This is the way to
install voices on a computer with no internet connection.

## How responsive it is

Piper is fast. New text you have not heard before starts speaking in a
fraction of a second. On top of that, the add-on remembers audio it has
already produced, and during idle moments it prepares the alphabet and the
words NVDA says most often. As a result, typing echo and moving through menus
and lists are effectively instant. This preparation is saved between sessions,
so it stays fast after the first time. Interrupting speech (for example by
pressing a key) is immediate.

## Where files are stored

Everything the add-on creates lives in your NVDA user configuration folder,
under a "piper" directory, rather than inside the add-on, so that updating the
add-on never deletes it:

- `voices\` - the voices you downloaded or imported.
- `cache\` - the prepared audio that makes echo instant.
- `voices.json` - the catalog of downloadable voices.
- `lexicon.json` - your pronunciation entries.
- `language_voices.json` - your per-language voice assignments.

## Troubleshooting

- **The voice list is empty or will not load.** Check your internet
  connection and try reopening the voice manager. The catalog is downloaded
  once and then cached.
- **A demo does not play.** Some voices may not have a hosted sample. Try
  downloading the voice and selecting it as your synthesizer to hear it.
- **Speech is delayed for new text on an older computer.** This is the neural
  synthesis time. Try a "low" or "x_low" quality voice, which is faster.
  Character echo and repeated words remain instant regardless.
- **NVDA warns the add-on was not tested with your NVDA version.** This
  appears when you run a newer NVDA than the add-on was last verified against.
  It is usually safe; check for an add-on update.
- **Something went wrong.** Open the NVDA log with NVDA+F1 and look for lines
  beginning with "piper". If you report an issue, include those lines.

## Removing voices or the add-on

- To remove a single voice, open the voice manager, select it, and press
  "Remove".
- To uninstall the add-on, use the Add-on Store or Manage add-ons. On
  uninstall you will be asked whether to also delete downloaded voices.

## Privacy

Everything runs locally. The add-on contacts the internet only to download
the voice catalog, voices, and demo samples that you request. It does not send
any of your text or usage anywhere.
