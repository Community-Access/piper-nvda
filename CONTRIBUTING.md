# Contributing and coding standards

Thanks for helping improve Piper Neural Voices for NVDA. This document covers
how to work on the code and the standards it follows.

## Ground rules

- Follow the
  [NVDA code of conduct](https://github.com/nvaccess/nvda/blob/master/CODE_OF_CONDUCT.md).
- Accessibility is non-negotiable. Any GUI you add must be fully keyboard
  operable, have labelled controls, and announce important state changes
  through NVDA. Test it with NVDA before submitting.
- Keep changes small and focused. Add or update tests with behavioral changes.
- Do not add telemetry or network calls beyond downloading voices/demos the
  user explicitly requests.

## Repository setup

See [docs/BUILDING.md](docs/BUILDING.md). In short: install Rust (MSVC) and
Python 3.11+, run `python tools/fetch_assets.py`, then `cd helper && cargo
build --release`.

## Python (the NVDA-side add-on)

- **Target Python 3.11.** NVDA 2025.x embeds Python 3.11 and 2026.1 embeds
  3.13; the add-on must run on both, so do not use syntax newer than 3.11.
- Follow NVDA's conventions: `logHandler.log` for logging (never `print`),
  `ui.message` for speech, `wx.CallAfter` for any GUI work from a background
  thread, and always call `nextHandler()` in event handlers.
- Format with `black` and sort imports with `isort` before committing.
- Prefer clear names and short, single-purpose modules (the driver is already
  split into `_protocol`, `_helperProc`, `_audio`, `_catalog`, `_voices`,
  `_download`, `_manager_ui`, `_paths`). Keep it that way.
- Wrap user-facing strings in `_()` for translation, with a translator comment
  above each, as the existing code does.
- Never block NVDA's main thread. Inference is out-of-process; the driver's
  own work (protocol I/O, downloads) runs on background threads and marshals
  results back with `wx.CallAfter` or NVDA's notification system.

## Rust (the helper)

- Stable Rust, `x86_64-pc-windows-msvc`, `cargo fmt` before committing, and
  keep `cargo build` warning-clean.
- The synthesis worker is single-threaded on purpose (espeak-ng is not thread
  safe). Do not call espeak or the engine from other threads.
- Errors that reach the user should be sent as ERROR/LOG protocol frames, not
  panics. Reserve panics for truly unreachable states.
- Keep the modules aligned with their Python counterparts, especially
  `protocol.rs` and `_protocol.py` (change both together and bump
  `PROTOCOL_VERSION` on any incompatible wire change).

## Tests

- Add Rust unit tests next to the code (`#[cfg(test)]`).
- Add Python tests under `tests/python/`. Pure-logic tests use the NVDA stubs;
  behavior that touches the helper goes in a real-helper integration test that
  skips when the build/assets are absent.
- Run `cargo test`, `cargo test -- --ignored --test-threads=1`, and
  `python -m pytest tests/python` before opening a PR. See
  [docs/TESTING.md](docs/TESTING.md).

## Commits and versions

- Write clear commit messages describing the behavior change.
- Do not bump the version or edit the changelog in feature commits; that
  happens as part of the release (see
  [docs/STORE_SUBMISSION.md](docs/STORE_SUBMISSION.md)).

## Reporting issues

Include your NVDA version, Windows version, the voice in use, and the relevant
lines from the NVDA log (NVDA+F1) beginning with "piper".
