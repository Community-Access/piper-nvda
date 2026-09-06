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
- Windows 11 or later, 64-bit. Windows 10 and earlier are not supported: the
  add-on may well run on Windows 10, but it is not tested there and problems
  that only appear there will not be fixed.
- Nothing else. The add-on brings the Visual C++ runtime it needs with it, so
  there is no separate redistributable to install.
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
- **Pause between sentences**: how much silence follows a sentence. Commas,
  semicolons, and colons get a shorter pause automatically. Pauses shorten
  with the rate, so fast speech does not become mostly silence. Set it to 0
  for the tightest possible delivery.
- **Prepare audio in the background for instant echo**: on by default. Piper
  prepares the alphabet, the digits, every punctuation mark and symbol along
  with the names NVDA gives them, the numbers, and the words NVDA says most
  often, and it remembers what it has already said. Those then speak with no
  delay at all. Turn it off to save disk and memory at the cost of that
  instant echo.
- **Show advanced voice parameters**: replaces Expressiveness with the three
  parameters the voice model actually uses. See below.

### Advanced voice parameters

Turn on "Show advanced voice parameters" to set Piper's own inference
parameters individually. They keep the names Piper uses, so anything written
about Piper voices elsewhere applies. Each is a percentage of what the voice
was trained with, where **50 means exactly as trained** and 100 means twice
that value:

- **Noise scale (variability)**: how much the voice varies in pitch and
  timbre. Lower is steadier and more monotone; higher is more varied.
- **Noise W (phoneme length variation)**: how much the length of individual
  sounds varies. Lower is more metronomic; higher is more natural but less
  predictable.
- **Length scale (model pace)**: how long the model makes each sound.
  **Higher is slower.** This is not the Rate setting: Rate speeds up the audio
  after it is produced and costs nothing, while this changes what the model
  produces. Leave it at 50 unless a voice sounds rushed or dragged to you.

Turning advanced parameters on or off changes which settings exist, so NVDA
may need the Speech settings dialog reopened before the change is visible. The
defaults are equivalent to Expressiveness at 50, so switching modes without
changing anything does not change how the voice sounds.

Each of these changes what the model produces, so the prepared audio for the
alphabet and common words is rebuilt in the background after a change. Echo
may be briefly slower until that finishes.

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

## Preparing your own words

The words Piper prepares in advance are the ones every NVDA user hears:
control types, states, punctuation names, the alphabet. What it cannot know is
your vocabulary: the app you live in, a colleague's name, a status message
your tools repeat all day.

In the voice manager, press "Prepared audio" to add your own. Press "Add",
type a word or short phrase, and press Save. Your phrases are prepared before
the built-in list, so they are ready first.

A phrase can be up to 40 characters. Beyond that, Piper splits an utterance up
to start speaking sooner, so a longer phrase would never be looked up as a
whole and preparing it would not make anything faster.

The same dialog shows how much space the prepared audio is using and has a
"Rebuild prepared audio" button, which throws it all away and prepares it
again. That is worth doing if a voice ever sounds wrong in a way that
re-selecting it does not fix, or simply to reclaim the space.

Preparing everything for one voice takes around 25 seconds of idle time and
about 12 MB, measured on a mid-range laptop. It happens in the background and
stops the moment there is real speech to say, so it is not a delay you wait
through. Across several voices the total is capped at 64 MB; past that the
least recently used audio is dropped.

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

NVDA can also send a pronunciation of its own, from its speech dictionaries.
Piper speaks those phonemes as given, and falls back to the original word if
the voice has no sound for one of them.

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
- `warmup.json` - the phrases you asked to have prepared.
- `language_voices.json` - your per-language voice assignments.

## Troubleshooting

- **The voice list is empty or will not load.** Check your internet
  connection and try reopening the voice manager. The catalog is downloaded
  once and then cached.
- **A character or symbol is not spoken when I arrow onto it or type it.**
  Fixed in 0.6.1. Punctuation is spoken by name, in your language, including
  the space character. If a symbol is still silent, check NVDA's punctuation
  and symbol level in Speech settings, and report it with the character.
- **A demo does not play.** Some voices may not have a hosted sample. Try
  downloading the voice and selecting it as your synthesizer to hear it.
- **A voice says it cannot be used.** Six of the published voices (Hebrew,
  Japanese, Thai, Ukrainian, and two Chinese voices) were built with a
  language-specific text processor that this add-on does not include. They are
  refused before their model is downloaded, because speaking them anyway would
  produce confident nonsense rather than an error. Other voices in those same
  languages work normally.
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
