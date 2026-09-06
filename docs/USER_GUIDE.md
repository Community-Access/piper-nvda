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
- **Use GPU acceleration (DirectML)**: optional. If your graphics hardware
  supports it, this can lower the delay for new text. If it is not supported,
  the add-on falls back to the processor automatically.

## Automatic language switching

If you turn on "Automatic language switching" in NVDA's Speech settings, and a
document marks its language, Piper will use a downloaded voice that matches
that language when one is available. Download at least one voice per language
you want this to work for.

## How responsive it is

Piper is fast. New text you have not heard before starts speaking in a
fraction of a second. On top of that, the add-on remembers audio it has
already produced, and during idle moments it prepares the alphabet and the
words NVDA says most often. As a result, typing echo and moving through menus
and lists are effectively instant. This preparation is saved between sessions,
so it stays fast after the first time. Interrupting speech (for example by
pressing a key) is immediate.

## Where files are stored

Downloaded voices and the audio cache are stored in your NVDA user
configuration folder, under a "piper" directory. They are kept there rather
than inside the add-on so that updating the add-on never deletes your voices.

## Troubleshooting

- **The voice list is empty or will not load.** Check your internet
  connection and try reopening the voice manager. The catalog is downloaded
  once and then cached.
- **A demo does not play.** Some voices may not have a hosted sample. Try
  downloading the voice and selecting it as your synthesizer to hear it.
- **Speech is delayed for new text on an older computer.** This is the neural
  synthesis time. Try a "low" or "x_low" quality voice, which is faster, or
  enable GPU acceleration if your hardware supports it. Character echo and
  repeated words remain instant regardless.
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
