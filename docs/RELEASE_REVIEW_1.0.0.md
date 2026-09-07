# Release review: 1.0.0 store submission

Date: 2026-09-06. Scope: the full add-on (`addon/`), the helper crate as it
affects the shipped binary, the build and packaging pipeline, and the NVDA
Add-on Store requirements in [STORE_SUBMISSION.md](STORE_SUBMISSION.md).
The review ran against tag `v1.0.0` (commit `2102f96`); the fixes it
prompted, and the NVDA 2026.1+ requirement, were then applied and every
check re-run on the updated tree.

## Verdict

**GO for submission on the beta channel.** Every code finding from the
review (F1-F8 below) has been fixed, tested, and verified; the add-on now
requires NVDA 2026.1+ by decision (`minimumNVDAVersion = 2026.1.0`), which
removes the 32-bit test burden entirely. One manual condition remains:

1. A keyboard pass over the UI added after the accessibility sign-off: the
   Built-in prepared items dialog, and the checkable lists in Download
   several and Import voices (now NVDA's CustomCheckListBox).

**NO-GO for the stable channel** until NVDA 2026.1 loses its
`experimental` flag in nvdaAPIVersions.json - the store rejects a stable
submission whose last-tested version is experimental. Submit on `beta`
now; resubmit on `stable` when the flag drops.

## Automated checks, with results

| Check | Command | Result |
|-------|---------|--------|
| Rust unit tests | `cargo test --release` | 57 passed |
| Rust asset-backed tests | `cargo test --release -- --ignored --test-threads=1` | 2 passed |
| Python suite, full stack included | `python -m pytest tests/python` | 207 passed (11 new tests cover the F3/F4/F5 fixes) |
| Helper binary freshness | part of `test_full_stack.py` | binary newer than `helper/src` |
| Translation template current | `test_i18n.py` | passes; 141 messages |
| `.po` compilation | `python tools/i18n.py compile` | no `.po` files yet, none unreadable |
| Package build | `python tools/build.py` | 19.2 MB, 468 entries |
| Package hygiene | inspection of the zip | no `.pyc`/`__pycache__`, no `.po`/`.pot`, no `_data`; manifest, `doc/en/readme.html`, helper, CRT, espeak all present |
| Helper import surface | `python tools/pe_imports.py helper/target/release/piper-helper.exe` | see below |
| Dialog accessibility (mechanical) | `test_dialog_accessibility.py` | all nine dialogs: titles, focus, labels, unique accelerators |

### Helper import surface

Beyond `api-ms-win-*` apisets and the bundled Visual C++ runtime, the helper
imports: `ADVAPI32`, `bcryptprimitives`, `d3d12`, `dbghelp`, `DirectML`,
`dxgi`, `KERNEL32`, `ntdll`, `SETUPAPI`. All ship with Windows on every
version NVDA 2026.1+ supports (DirectML has been an inbox component since
Windows 10 1903). onnxruntime is linked statically, so there is no
`onnxruntime.dll` for VirusTotal to flag separately. **No user-installed
prerequisite exists.**

## Code review findings

A two-angle deep review (line-by-line scan plus cross-file interaction
tracing) over `addon/`, with every finding re-verified against the source
by hand. Ordered by severity.

| # | Where | Finding | Verdict | Recommendation |
|---|-------|---------|---------|----------------|
| F1 | every module using `_()` | No module calls `addonHandler.initTranslation()`, so `_()` resolves against NVDA core's catalog and the add-on's own `locale/*.mo` can never load. The whole `nvda.pot` pipeline is dead code, and `_phonemes.unsupported_message` raises `NameError` outside NVDA. | Fixed | `addonHandler.initTranslation()` added to every module using `_()`, with a graceful fallback outside NVDA; test stubs gained `addonHandler`. |
| F2 | `_download.py:50`, `_catalog.py:131` | `urlopen`/`read` have no timeout. The catalogue fetch runs inside `SynthDriver.__init__` on first run (via `prompt_first_run`), so a stalled connection hangs synth init - NVDA with no speech. During a voice download, Cancel is only checked between reads, so a stalled read makes the modal progress loop spin forever. | Fixed | Every `urlopen` (downloader, catalogue, demo fetch) now uses a 30 s socket timeout, which also bounds each read. |
| F3 | `_helperProc.py:163` | `_handle_death` is unlocked: the watchdog's kill wakes the reader thread, which re-enters it - double spawn, two readers on one pipe, restart budget burned at double rate. And the give-up branch returns *before* `proc.kill()`, so a hung helper stays alive with `_proc` set; `send()` then writes into a full pipe and can block NVDA's main thread. | Fixed | `_handle_death` is serialized by a lock and keyed to the process that died, so the second reporter is a no-op; the dead or hung process is always killed, and giving up clears `_proc` so `send()` fails fast. Covered by `test_helper_proc.py`. |
| F4 | `_manager_ui.py:492` | Removing (or downloading) a voice never tells the live Piper synth: there is no reload-installed-voices hook. Removing the voice that is speaking leaves the synth pointing at deleted files - ERROR frames and silence until the synth is reloaded. | Fixed | `reload_installed_voices()` added to the driver (moves off a removed voice) and notified after remove, download, download-several, import, and install-from-file. Covered by `test_reload_voices.py`. |
| F5 | `_audio.py:58` + `_helperProc` | `cancel()` races in-flight frames: audio already in the pipe when CANCEL is sent is enqueued after the drain and plays as a burst at the start of the next utterance; a stale MARKER/DONE can fire late. Frames carry no utterance id to filter by. | Fixed | The driver drops AUDIO/MARKER/DONE frames from cancelled utterance ids, and the pump's generation counter makes the feeder discard items that raced the cancel drain. Covered by `test_cancel_races.py`. |
| F6 | `_manager_ui.py:595` | Toggling a favourite saves the per-voice settings snapshot taken when the browser opened, then `reload_voice_settings` pushes that stale data into the live synth - settings tuned while the dialog was open snap back and are lost on disk. | Fixed | Favourites now save against the per-voice settings freshly read from disk. |
| F7 | `_manager_ui.py:1165` | Prepared-audio add/edit shows the "too long" error for any phrase that `clean()` normalized (double spaces, case-duplicate), because the check is `text.strip() not in cleaned`. The entry is dropped with an unrelated explanation. | Fixed | The dialog now judges the normalized phrase: a real length problem gets the length message, a duplicate is announced as already listed and selected. |
| F8 | `_manager_ui.py:184` | The demo player's private helper shares `--cache-dir` with the live synth's helper. The cache is written atomically (write temp, replace), so this cannot corrupt - but last-writer-wins can discard the other process's prepared entries, and a rebuild while a demo helper lives may be a no-op behind a "Rebuilding" announcement. | Fixed | The demo helper no longer receives a cache dir. |

## Review by area

### Security posture: acceptable, no blockers

- **Network:** every URL is `https://` (Hugging Face for the catalogue,
  models, and demos). Nothing is fetched and executed; downloads are data
  files.
- **Download integrity:** models and configs verify against the md5 the
  upstream `voices.json` publishes, before the file is moved into place.
  md5 here is an integrity check against truncation and corruption, not an
  authenticity proof; authenticity rests on TLS to huggingface.co. That is
  the same trust model every Piper add-on uses. Recommendation: accept;
  revisit only if upstream ever publishes SHA-256.
- **Archive handling:** voice import rejects path traversal (tested);
  settings restore extracts only an allowlist of known file names, each
  written by name into the data directory, so an archive cannot place a
  file elsewhere.
- **Process handling:** the helper is spawned with an argument list (no
  shell), a hidden window, and stdio pipes; a watchdog restarts it and
  gives up after repeated crashes rather than looping.
- **Privacy:** no telemetry, no accounts, no data leaves the machine except
  the requests to Hugging Face that the user initiates by browsing or
  downloading voices. Speech text never touches the network.

### Robustness: one accepted trade-off

- Helper `stderr` goes to `DEVNULL`, so a native-side panic message is lost;
  the watchdog restart and the "crashed too often" giving-up path are the
  containment. Recommendation: accept for 1.0.0; a debug flag that tees
  stderr to a log file is a good 1.0.x item for diagnosing field reports.
- The config-spec loader bug (the `KeyError: 'sentencePause'` failure) is
  fixed and regression-tested against a faithful model of NVDA's config
  caching; this was the one defect that made 1.0.0 unusable for upgraders,
  and it is in the tagged build.

### Accessibility: strong, one unaudited corner

- Mechanical checks cover all nine dialogs; empty lists announce "No
  entries" instead of "unknown"; checkable voice lists announce checked
  state via NVDA's own control; symbol names are prepared in the user's
  language. The manual pass covered eight dialogs on 2026.x. The Built-in
  items dialog and the swapped checkable-list control postdate that pass -
  manual condition 4 in the verdict.

### Store requirements: all field-level checks pass

- `name = piperNeural` (valid characters, unique as far as the store search
  shows), `version = 1.0.0` matching the Cargo crate and the changelog,
  `summary`/`url` present and consistent, `minimumNVDAVersion = 2026.1.0`,
  `lastTestedNVDAVersion = 2026.1.0`, `docFileName = readme.html` present
  in the package, GPL v2 `LICENSE` at the repo root,
  `THIRD_PARTY_LICENSES.md` enumerating the bundled components - the
  document to cite if VirusTotal flags onnxruntime or espeak-ng.
- The tag `v1.0.0` exists on GitHub; the release asset (the `.nvda-addon`
  built above) still needs to be attached and its direct URL used in the
  submission form.

## What was explicitly left out, and why

- **Signing the helper.** NVDA add-ons are unsigned as a rule and the
  store's VirusTotal step is the real gate; revisit on the first SmartScreen
  report.
- **Translations.** English-only is acceptable for a first submission;
  translators tend to arrive from the store's user pool.
- **Benchmarks.** No performance-affecting change since they were last
  recorded.

## Submission runbook (condensed)

1. Complete the keyboard pass (condition 1) and re-run the manual matrix
   on NVDA 2026.1+; rebuild and retag.
2. Attach `dist/piper-neural-1.0.0.nvda-addon` to the v1.0.0 GitHub
   release; copy the direct asset URL.
3. Open the store registration issue form: beta channel, publisher and
   URLs as in [STORE_SUBMISSION.md](STORE_SUBMISSION.md) step 4.
4. If VirusTotal flags the native DLLs, reply on the PR citing
   `THIRD_PARTY_LICENSES.md` and the open-source build recipe.
5. When 2026.1 leaves experimental, resubmit the same version on stable.
