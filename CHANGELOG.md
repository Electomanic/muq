# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Dynamics** (spec §8.4): note events accept `dyn` (`ppp`–`fff`, `sfz`)
  as a musician-friendly alternative to `vel`. Mutually exclusive with
  `vel`; new error classes `INVALID_DYNAMIC` and `DYN_VEL_CONFLICT`.
- **Sixteenth-note swing** (spec §6.3): patterns accept `swing_unit: 8|16`
  (default 8). `16` swings off-sixteenths (MPC/hip-hop feel); swing now
  also explicitly applies to automation and text events.
- **Section key override** (spec §7): arrangement sections accept `key`
  for modulations. Scale validation uses the active key per section.
- **Section markers** (spec §C.2.1): section names are exported as MIDI
  Marker meta-events (FF 06) on track 0.
- New example `spec/examples/dynamics.muq`.
- `muq --version` flag.
- `muq validate --strict` to treat warnings as errors.
- `muq fmt --check` for CI-friendly format checking without writing.
- JSON Schema is now bundled inside the `muq` package so installed wheels
  work without the repository checkout.
- Ruff lint configuration and GitHub Actions CI.

### Changed
- **Legato articulation** (spec §8.3) gate changed from ×1.0 to ×1.05 so
  legato notes overlap slightly, triggering legato/mono transitions on
  synths. Same-pitch overlap clamping still applies.
- **Linear interpolation without a previous event** (spec §14.5) now
  degrades to `step` instead of ramping from 0.
- Spec clarifications: beat positions are always quarter-note based
  regardless of meter (§11), unbound tracks are silent in a section (§7),
  pattern looping under meter changes uses the meter at the absolute bar
  position (§7.1), fractional tempos are allowed (§4).
- Schema validation errors now include the JSON path of the offending value.
- `muq export` without a sub-command now prints a clear error and exits with
  code 2 instead of re-invoking the argument parser.

### Fixed
- `spec_version` schema pattern was missing an end anchor, accepting values
  like `1.2.3.4`.
- Unknown drum names now emit an `UNKNOWN_DRUM_NAME` warning during
  resolution instead of being silently skipped.

## [0.1.0]

### Added
- Initial release: parser, validator, resolver, MIDI exporter, canonical
  formatter, and CLI (`validate`, `info`, `fmt`, `export`).
