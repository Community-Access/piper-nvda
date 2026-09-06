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
- Prefer clear names and short, single-purpose modules (the driver is already
  split into `_protocol`, `_helperProc`, `_audio`, `_catalog`, `_voices`,
  `_download`, `_manager_ui`, `_paths`). Keep it that way.
- Wrap user-facing strings in `_()` for translation, with a `# Translators:`
  comment above each describing its purpose, as the existing code does.
- After changing any user-visible string run `python tools/i18n.py extract`
  to refresh `addon/locale/nvda.pot`. A test fails when it is stale, since
  translators work from that template. See
  [docs/TRANSLATING.md](docs/TRANSLATING.md).
- Never block NVDA's main thread. Inference is out-of-process; the driver's
  own work (protocol I/O, downloads) runs on background threads and marshals
  results back with `wx.CallAfter` or NVDA's notification system.

### Code style: NV Access standard

NV Access enforces its own style on the NVDA project and the official add-on
template, and matching it is expected for store add-ons. The authoritative
references are the NVDA
[coding standards](https://github.com/nvaccess/nvda/blob/master/projectDocs/dev/codingStandards.md)
and the add-on template
[`pyproject.toml`](https://github.com/nvaccess/addonTemplate/blob/master/pyproject.toml):

- **Ruff** is the mandated linter and formatter: line length 110, **tab**
  indentation (one tab per level), LF line endings, UTF-8. Import sorting is
  Ruff's `I001`.
- **Type annotations** on all variables, attributes, and function arguments
  and returns (except `self`/`cls`); prefer `X | None` over `Optional[X]`.
- **Pyright** in strict mode.
- Naming: functions/variables `lowerCamelCase`; classes `UpperCamelCase`;
  constants `UPPER_SNAKE`; scripts `script_name`; event handlers
  `event_name`.

Heads-up for this repository: the existing Python was written in the common
PEP 8 / 4-space style, not NV Access tabs. Before a first store submission,
run Ruff with the NVDA template's config to reformat to tabs/line-110 and add
any missing type annotations, and add the add-on template `pyproject.toml` so
CI enforces it. Do not mix styles within a file.

## Rust (the helper)

- Stable Rust, `x86_64-pc-windows-msvc`, rustfmt style for new code, and
  keep `cargo build` warning-clean.
- Do not run `cargo fmt` across the crate. Several files lay data out by
  hand (the warmup word list, for one) and reformatting them buries real
  changes in noise. Write new code in rustfmt style instead; see
  [docs/DECISIONS.md](docs/DECISIONS.md).
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
