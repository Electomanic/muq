# muq

A YAML-based music format designed to be human-readable, AI-friendly, DAW-interoperable, and diffable.

## What is muq?

muq (`.muq`) files describe music as structured YAML — notes, chords, rests, drum patterns, automation, tempo changes, and arrangement — in a format that's easy to write by hand, process with tools, and convert to MIDI.

```yaml
song:
  title: "Hello muq"
  tempo: 120
  time: "4/4"

tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1

patterns:
  melody:
    bars:
      - - {note: C4, dur: q}
        - {note: E4, dur: q}
        - {note: G4, dur: q}
        - {note: C5, dur: q}

arrangement:
  - name: intro
    patterns:
      piano: melody
```

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Electomanic/muq.git
cd muq
uv sync
```

## Usage

### Command line

```bash
# Validate a .muq file
uv run muq validate song.muq

# Export to MIDI
uv run muq midi song.muq -o song.mid

# Format to canonical form
uv run muq fmt song.muq
```

### Python API

```python
from muq.parser import parse
from muq.validate import validate
from muq.resolve import resolve
from muq.midi import save_midi

doc = parse("song.muq")
errors = validate(doc)
song = resolve(doc)
save_midi(song, "song.mid")
```

### Running tests

```bash
uv run pytest
```

## Features

- **Human-readable** — one event per line, YAML flow mappings, clean diffs
- **Full GM support** — 128 instruments, percussion, drum maps
- **Beat-addressed or sequential** — place notes at explicit beats or let them flow
- **Automation** — CC, pitch bend, aftertouch with step or linear interpolation
- **Arrangement** — sections, repeats, tempo/meter changes, pickup bars
- **Ties and articulations** — cross-bar ties, staccato, legato, accent, etc.
- **Scale validation** — optional pitch checking against declared key/mode
- **Canonical formatter** — deterministic output for version control

## Specification

The full format specification is in [spec/muq-spec.md](spec/muq-spec.md). The JSON Schema is at [spec/muq.schema.json](spec/muq.schema.json).

## License

- **Code** (everything except `spec/`): [Apache License 2.0](LICENSE)
- **Specification** (`spec/`): [Creative Commons Attribution 4.0 International](LICENSE-SPEC)
