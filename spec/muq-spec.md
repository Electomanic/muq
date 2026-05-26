# muq Format Specification

**Version:** 1.0.0-draft
**Date:** 2026-05-26
**License:** [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)

## 1. Overview

muq (`.muq`) is a YAML-based file format for representing music data. It is designed to be:

- **Human-readable and writable** — structured YAML with compact flow-style note events
- **AI-friendly** — structured data (lists/maps), no implicit state, no context-dependent parsing
- **DAW-interoperable** — convertible to/from MIDI and other music formats
- **Validatable** — JSON Schema for structural validation, beat-count validation for musical correctness
- **Diffable** — one event per line produces clean version control diffs

A `.muq` file is a valid YAML 1.2 document. Any conforming YAML parser can load it.

## 2. Terminology

| Term | Definition |
|------|-----------|
| **Beat** | One quarter-note duration. The fundamental time unit. |
| **Bar** (measure) | A grouping of beats defined by the time signature. In 4/4 time, one bar = 4 beats. |
| **Event** | A single note, chord, or rest occupying time within a bar. |
| **Pattern** | A named sequence of bars containing musical events. Patterns are assigned to tracks in the arrangement. |
| **Track** | A named instrument channel with its configuration (instrument, channel, volume, pan). |
| **Section** | A named segment of the arrangement that activates one or more patterns simultaneously. |
| **Sequential mode** | Events without a `beat` key are placed end-to-end in time order. |
| **Beat-addressed mode** | Events with a `beat` key are placed at explicit positions within the bar. |
| **Canonical form** | The normalized representation using full-length keys and consistent formatting. |

## 3. File Format

A `.muq` file MUST be a valid YAML 1.2 document encoded in UTF-8. The file extension MUST be `.muq`.

### 3.1 Top-Level Structure

A `.muq` document is a YAML mapping with the following top-level keys:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `song` | mapping | **yes** | Song metadata |
| `tracks` | mapping | **yes** | Instrument/channel definitions |
| `patterns` | mapping | **yes** | Named note sequences |
| `arrangement` | sequence | **yes** | Ordered list of sections |
| `drum_map` | mapping | no | Custom drum name → MIDI note overrides |

No other top-level keys are permitted.

## 4. `song` Object

The `song` mapping contains metadata about the composition.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `title` | string | no | — | Song title |
| `artist` | string | no | — | Artist/composer name |
| `tempo` | number | **yes** | — | Tempo in QPM (quarter notes per minute). This is the MIDI-standard tempo unit: the number of quarter-note beats per minute. Range: 1–999. |
| `time` | string | **yes** | — | Time signature as `numerator/denominator`, e.g. `4/4`, `3/4`, `7/8`. |
| `key` | string | no | — | Key signature. Format: `<tonic> <mode>` where tonic matches `[A-G](#|b|##|bb)?` and mode is one of: `major`, `minor` (alias for `natural_minor`), `natural_minor`, `harmonic_minor`, `melodic_minor`, `dorian`, `phrygian`, `lydian`, `mixolydian`, `aeolian`, `locrian`, `pentatonic`, `minor_pentatonic`, `blues`, `chromatic`. Examples: `C major`, `F# minor`, `Bb dorian`. Informational only by default; see `scale_mode`. |
| `scale_mode` | string | no | — | Scale validation mode: `"off"` (default), `"warn"`, or `"strict"`. See §4.2. |
| `spec_version` | string | no | `"1.0.0"` | muq spec version this file conforms to. |

### 4.1 Time Signature

The `time` value is a string of the form `N/D` where:
- `N` (numerator) is a positive integer: the number of notated beats per bar.
- `D` (denominator) is a positive integer that is a power of 2 (1, 2, 4, 8, 16, 32): the note value that gets one notated beat.

The time signature denominator defines the notated beat unit, but muq numeric timing fields are always measured in quarter-note units.

- **Notated beats per bar** = N
- **Quarter-note units per bar** = N × (4 / D)

All duration tokens (`w`, `h`, `q`, `e`, `s`) and numeric `dur_beats` / `rest_beats` values are defined relative to a quarter note, regardless of time signature denominator. The formula N × (4 / D) converts from notated beats to the quarter-note units used for bar validation and MIDI tick computation.

In this specification, `beats_per_bar` always refers to the quarter-note units per bar value.

Examples:
- `4/4` → 4 quarter-note units per bar
- `3/4` → 3 quarter-note units per bar
- `6/8` → 3 quarter-note units per bar (6 × 4/8 = 3)
- `7/8` → 3.5 quarter-note units per bar
- `5/4` → 5 quarter-note units per bar

### 4.2 Scale Mode

When `key` is set and `scale_mode` is not `"off"`, validators check whether note pitches belong to the declared scale:

- `"off"` (default): No scale checking. `key` is purely informational.
- `"warn"`: Validators emit warnings for notes outside the declared scale but do not reject the file.
- `"strict"`: Notes outside the declared scale are treated as errors.

Scale validation applies only to pitched note events, not drum events. Since patterns are pure musical data with no track binding, validators MUST resolve the arrangement to determine which patterns are assigned to drum tracks (channel 10) and skip scale validation for those events. Accidentals are evaluated after resolution (e.g. `F#4` in `G major` is in-scale).

Scale validation operates on MIDI pitch classes. Enharmonically equivalent notes (e.g. `F#4` and `Gb4`, both MIDI note 66) are treated identically for scale membership. A note is in-scale if its pitch class (modulo 12) matches any degree of the declared scale, regardless of spelling.

The following table defines the pitch-class intervals (semitones from tonic) for each mode:

| Mode | Pitch-class intervals from tonic |
|------|----------------------------------|
| `major` | [0, 2, 4, 5, 7, 9, 11] |
| `minor` | alias of `natural_minor` |
| `natural_minor` | [0, 2, 3, 5, 7, 8, 10] |
| `harmonic_minor` | [0, 2, 3, 5, 7, 8, 11] |
| `melodic_minor` | [0, 2, 3, 5, 7, 9, 11] |
| `dorian` | [0, 2, 3, 5, 7, 9, 10] |
| `phrygian` | [0, 1, 3, 5, 7, 8, 10] |
| `lydian` | [0, 2, 4, 6, 7, 9, 11] |
| `mixolydian` | [0, 2, 4, 5, 7, 9, 10] |
| `aeolian` | alias of `natural_minor` |
| `locrian` | [0, 1, 3, 5, 6, 8, 10] |
| `pentatonic` | [0, 2, 4, 7, 9] |
| `minor_pentatonic` | [0, 3, 5, 7, 10] |
| `blues` | [0, 3, 5, 6, 7, 10] |
| `chromatic` | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |

## 5. `tracks` Object

The `tracks` mapping defines named instrument channels. Each key is a unique track name (a YAML string matching `[a-zA-Z_][a-zA-Z0-9_]*`). Each value is a track definition mapping.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `instrument` | string | **yes** | — | GM instrument name (see Appendix A) or `"standard"` for drums. |
| `channel` | integer | **yes** | — | MIDI channel 1–16. Channel 10 is the default for drums per GM. |
| `volume` | integer | no | 100 | Track volume 0–127. |
| `pan` | string or integer | no | `"center"` | Pan position: `"left"` (0), `"center"` (64), `"right"` (127), or integer 0–127. |
| `percussion` | boolean | no | (auto) | If true, this track is a percussion track. Defaults to true when `channel` is 10 or `instrument` is `"standard"`, false otherwise. Set explicitly to use drum instruments on non-10 channels. |

### 5.1 Per-Track Drum Map

Drum tracks (percussion tracks) MAY include a `drum_map` field with custom drum name → MIDI note overrides that apply only to that track:

```yaml
tracks:
  kit_a:
    instrument: standard
    channel: 10
    drum_map:
      kick: 36
      snare: 38
  kit_b:
    instrument: standard
    channel: 10
    drum_map:
      kick: 35
      snare: 40
```

Per-track `drum_map` entries override both the default drum map and the global `drum_map` for that track only. Resolution order: per-track `drum_map` > global `drum_map` > default GM drum map.

Validators SHOULD warn if `drum_map` is set on a non-percussion track (it has no effect).

### 5.2 Constraints

- Track names MUST be unique.
- By default, drum tracks SHOULD use channel 10 for GM compatibility.
- When `percussion: true` is set explicitly, drum instruments are allowed on any channel.
- Parsers MUST allow drum tracks on non-10 channels if `percussion: true` and `drum_map` is present.
- Multiple tracks MAY share the same channel (for layering), but this is not recommended.

## 6. `patterns` Object

The `patterns` mapping defines named, reusable sequences of musical events. Each key is a unique pattern name. Each value is a pattern definition mapping.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `bars` | sequence | **yes** | — | Ordered list of bars. Each bar is a sequence of events. |
| `notation` | string | no | `"pitched"` | Pitch notation style: `"pitched"` for note-octave notation (e.g. `C4`) or `"percussion"` for drum name notation (e.g. `kick`). |
| `swing` | integer | no | 50 | Swing percentage (50–75). See §6.3. |

### 6.1 Bar Structure

Each element of `bars` is a YAML sequence (list) of events. Events within a bar are either sequential or beat-addressed (see §11).

An empty bar (empty list `[]`) represents a bar of silence.

### 6.2 Constraints

- Pattern names MUST be unique.
- Patterns are pure musical data. Track binding is specified in the `arrangement` (see §7).
- **Pitch notation consistency**: All note events within a pattern MUST use the notation style declared by the pattern's `notation` field. If `notation` is `"pitched"` (the default), all note events must use note-octave notation (e.g. `C4`, `F#3`). If `notation` is `"percussion"`, all note events must use drum name notation (e.g. `kick`, `snare`). Mixing notation styles is invalid (`MIXED_PITCH_NOTATION`). Events without pitches (rests, CC, pitch bend, aftertouch, text) do not affect this constraint. A pattern with no note events (e.g. pure automation) is valid with either notation value.
- **Notation–track consistency**: When a section binds a pattern to a track, the pattern's `notation` SHOULD match the track's percussion status. Binding a `notation: percussion` pattern to a non-percussion track (or vice versa) produces a warning (`NOTATION_TRACK_MISMATCH`).

### 6.3 Swing

A pattern MAY include a `swing` key to apply swing feel to all events on the eighth-note grid.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `swing` | integer | no | 50 | Swing percentage (50–75). 50 = straight, ~67 = triplet swing. |

The `swing` value indicates where the offbeat eighth note lands within each beat, expressed as a percentage from the beat start:

- **50** — the offbeat lands exactly halfway through the beat (straight eighths).
- **67** — the offbeat lands 2/3 through the beat (triplet swing).
- **75** — the offbeat lands 3/4 through the beat (hard shuffle).

Swing displaces events whose beat position falls on an off-beat eighth (i.e. positions `X.5` where X is an integer). Events on the beat (integer positions) are unaffected. The swung position is calculated as:

$$\text{swung\_position} = \lfloor b \rfloor + \frac{\text{swing}}{100}$$

where $b$ is the original beat position. For a straight event at beat 1.5 with `swing: 67`, the swung position is $1 + 0.67 = 1.67$.

Swing is a separate timing layer from `offset_beats` — it does NOT create `offset_beats` entries.

```yaml
patterns:
  swing_groove:
    swing: 60
    bars:
      - - {note: C4, dur: e}    # beat 1 — unaffected
        - {note: E4, dur: e}    # beat 1.5 — displaced to ~1.6
        - {note: G4, dur: e}    # beat 2 — unaffected
        - {note: C5, dur: e}    # beat 2.5 — displaced to ~2.6
```

## 7. `arrangement` Array

The `arrangement` is an ordered sequence of section mappings. Each section assigns patterns to tracks and activates them simultaneously.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | **yes** | — | Section name (for readability; not required to be unique). |
| `patterns` | mapping | **yes** | — | Mapping of track name → pattern name. Each key MUST be a track defined in `tracks`; each value MUST be a pattern defined in `patterns`. |
| `repeat` | integer | no | 1 | Number of times to repeat this section. Range: 1–9999. |
| `tempo` | number | no | (inherited) | Tempo override for this section. Applies at the start of the section. |
| `time` | string | no | (inherited) | Time signature override for this section (e.g. `"7/8"`). Applies to all bars unless overridden by `meter_events`. |
| `tie_across` | boolean | no | false | If true, tied notes at the end of this section carry into the next section. See §13. |
| `tempo_events` | sequence | no | — | Tempo changes within this section. See §7.3. |
| `meter_events` | sequence | no | — | Time signature changes within this section. See §7.4. |
| `pickup_beats` | number | no | — | Number of beats in the pickup (anacrusis) before the first full bar. See §7.5. |

The `patterns` mapping binds tracks to patterns for the duration of the section:

```yaml
arrangement:
  - name: verse
    patterns:
      piano: piano_verse
      bass: bass_verse
      drums: drums_basic
    repeat: 4
```

The same pattern MAY be assigned to multiple tracks in the same section (pattern reuse):

```yaml
arrangement:
  - name: unison
    patterns:
      piano: melody_a
      strings: melody_a    # same pattern, different instrument
```

### 7.1 Section Length

When multiple patterns are activated in a section, they SHOULD have the same number of bars. If pattern lengths differ, shorter patterns loop from their first bar to fill the section length determined by the longest pattern. For example, a 1-bar drum pattern in a 2-bar section plays its single bar twice.

### 7.2 Arrangement Expansion

The arrangement is expanded linearly: each section is placed sequentially, with its patterns layered simultaneously. The `repeat` value causes the section to be duplicated in sequence. Tied notes carry across repeat iterations within a section (each iteration's last bar can tie into the next iteration's first bar). See §13 for tie behavior across section boundaries.

### 7.3 Tempo Events

The optional `tempo_events` array allows tempo changes within a section, enabling ritardando (slowing down) and accelerando (speeding up).

Each tempo event is a mapping:

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `bar` | integer | **yes** | — | Bar number within the section (1-indexed). |
| `beat` | number | **yes** | — | Beat position within the bar (1-indexed). |
| `tempo` | number | **yes** | — | Target tempo in QPM (1–999). |
| `interp` | string | no | `"step"` | Interpolation from the previous tempo to this value: `"step"` (instant) or `"linear"` (gradual ramp). |

```yaml
arrangement:
  - name: ending
    patterns:
      piano: outro_chords
    tempo: 120
    tempo_events:
      - {bar: 1, beat: 1, tempo: 120}
      - {bar: 4, beat: 1, tempo: 80, interp: linear}   # ritardando over 4 bars
```

The section-level `tempo` field sets the starting tempo for the section. If `tempo_events` is present, it provides finer control. If both `tempo` and `tempo_events` are present, `tempo` sets the initial value and `tempo_events` override from their specified positions.

Tempo events are **global** — they affect all tracks in the section. The `bar` value MUST NOT exceed the section's bar count.

### 7.4 Meter Events

The optional `meter_events` array allows time signature changes within a section, enabling shifting meters (e.g. alternating 4/4 and 7/8).

Each meter event is a mapping:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `bar` | integer | **yes** | Bar number within the section (1-indexed) at which the new meter takes effect. |
| `time` | string | **yes** | New time signature (same format as `song.time`). |

```yaml
arrangement:
  - name: prog_section
    time: 4/4
    meter_events:
      - {bar: 3, time: "7/8"}
      - {bar: 5, time: "4/4"}
    patterns:
      piano: prog_chords
```

The section-level `time` (or inherited `song.time`) sets the initial time signature. `meter_events` override it starting at the specified bar. All bars from that bar onward use the new time signature until the next `meter_event` or the end of the section.

Meter events affect bar validation: `beats_per_bar` (quarter-note units per bar) is recalculated at each meter change. A bar that falls under a 7/8 meter event has `beats_per_bar = 3.5` (7 × (4/8)).

Meter events, like tempo events, are **global** — they affect all tracks in the section. The `bar` value MUST NOT exceed the section's bar count.

### 7.5 Pickup Bars (Anacrusis)

The optional `pickup_beats` key on a section indicates that the first bar of the section is a partial bar (anacrusis / pickup bar). The value specifies the number of beats in the pickup bar.

```yaml
arrangement:
  - name: "Intro"
    pickup_beats: 1          # one-beat pickup in 4/4
    patterns:
      piano: intro_pickup
```

When `pickup_beats` is present:

1. The first bar of each pattern in the section is treated as a partial bar with `beats_per_bar` equal to `pickup_beats`.
2. Sequential events in the first bar MUST NOT exceed `pickup_beats` in total duration.
3. Beat-addressed events in the first bar use the same 1-indexed addressing, but the bar length is `pickup_beats` instead of the full meter.
4. All subsequent bars use the normal time signature.
5. `pickup_beats` MUST be greater than 0 and less than the section's `beats_per_bar`.
6. Only the **first section** of the arrangement SHOULD use `pickup_beats`. Using it on later sections is allowed but unusual.

## 8. Note Events

A note event is a YAML mapping representing a single musical moment — a note, chord, or rest.

### 8.1 Event Keys

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `note` | string or sequence | **yes** (unless rest) | — | Pitch or list of pitches for chords. |
| `dur` | string | **yes** (unless `dur_beats`) | — | Duration token. See §10. |
| `dur_beats` | number | **yes** (unless `dur`) | — | Numeric duration in quarter-note beats. See §10.5. |
| `vel` | integer | no | 80 | Velocity (1–127). Velocity 0 is excluded because MIDI velocity 0 is an alias for note-off; muq uses explicit durations for note-off timing. |
| `beat` | number | no | (sequential) | Beat position within bar. See §11. |
| `tie` | boolean | no | false | If true, this note is tied to the same pitch in the next event. |
| `voice` | integer | no | (none) | Voice number for polyphonic tie disambiguation. See §13.2. |
| `offset_beats` | number | no | 0 | Microtiming offset in quarter-note beats. Displaces the event from its quantized position. See §11.5. Not valid on rest events. |
| `articulation` | string | no | (none) | Articulation marking. See §8.3. |
| `rest` | string | **yes** (if rest, unless `rest_beats`) | — | Duration token for rest. Mutually exclusive with `note` and `rest_beats`. |
| `rest_beats` | number | **yes** (if rest, unless `rest`) | — | Numeric rest duration in quarter-note beats. Mutually exclusive with `note` and `rest`. |

### 8.2 Note Events vs. Rest Events

An event is a **note event** if it contains `note`. It is a **rest event** if it contains `rest` or `rest_beats`. It is a **text event** if it contains `text`. An event MUST NOT contain both `note` and `rest`/`rest_beats`.

Rest events accept only `rest` or `rest_beats`, and optionally `beat`. Other keys (`vel`, `tie`, `voice`, `articulation`, `offset_beats`) are not valid on rest events. A rest event MUST NOT contain both `rest` and `rest_beats` (this mirrors the `dur`/`dur_beats` exclusivity on note events).

### 8.3 Articulations

Note events MAY include an `articulation` key to specify performance markings. Articulations modify gate time (the fraction of the full duration that the note sounds) and/or velocity.

| Value | Gate Modifier | Velocity Modifier | Description |
|-------|--------------|-------------------|-------------|
| `staccato` | ×0.5 | — | Short, detached. |
| `staccatissimo` | ×0.25 | — | Very short, very detached. |
| `legato` | ×1.0 | — | Full duration, smooth connection. |
| `tenuto` | ×1.0 | +10 | Full duration, slightly emphasized. |
| `accent` | — | +20 | Emphasized attack. |
| `marcato` | ×0.85 | +30 | Heavy accent with slight shortening. |
| `portato` | ×0.75 | — | Between legato and staccato. |

Gate modifiers are multiplicative: a quarter note (`q` = 1 beat) with `staccato` sounds for 0.5 beats. The "—" entries mean no change from default behavior (default gate = 1.0, velocity as written or default 80).

Velocity modifiers are additive and applied **after** the event's `vel` value. The result is clamped to 1–127.

Articulations are only valid on note events. Setting `articulation` on a rest or text event is an error (`INVALID_ARTICULATION`).

```yaml
- {note: C4, dur: q, articulation: staccato}       # sounds for 0.5 beats
- {note: E4, dur: q, vel: 100, articulation: accent} # vel = min(120, 127) = 120
```

## 9. Pitch Notation

Pitches are represented as strings with the following structure:

```
<note_name><accidental?><octave>
```

| Component | Values | Description |
|-----------|--------|-------------|
| Note name | `C`, `D`, `E`, `F`, `G`, `A`, `B` | Case-insensitive in input. Canonical form is uppercase. |
| Accidental | `#`, `b`, `##`, `bb` | Sharp, flat, double-sharp, double-flat. Optional. |
| Octave | `-1` to `9` | Integer. C4 = middle C = MIDI note 60. |

### 9.1 MIDI Note Number Calculation

```
semitone = {C:0, D:2, E:4, F:5, G:7, A:9, B:11}[note_name]
accidental_offset = (number of # signs) - (number of b signs)
midi_note = (octave + 1) * 12 + semitone + accidental_offset
```

The resulting MIDI note number MUST be in range 0–127. Values outside this range make the file **invalid**.

### 9.2 Enharmonic Equivalence

`C#4` and `Db4` are different representations of the same pitch (MIDI note 61). Parsers MUST treat them as equivalent for playback. The canonical form preserves the original spelling.

### 9.3 Chords

A chord is represented as a YAML sequence of pitch strings:

```yaml
note: [C4, E4, G4]
```

All pitches in a chord share the same `dur`, `vel`, `beat`, and `tie` values. A single-element list `[C4]` is equivalent to the scalar `C4`.

### 9.4 Drum Pitches

On drum tracks (channel 10), pitches are specified by drum name instead of note name. See §15 and Appendix B.

```yaml
{note: kick, dur: q}
{note: hh, dur: e}
```

Drum names are case-insensitive in input. Canonical form is lowercase.

## 10. Duration System

Duration tokens specify how long a note or rest sounds, measured in **quarter-note beats**.

### 10.1 Base Durations

| Token | Name | Beats |
|-------|------|-------|
| `w` | whole | 4.0 |
| `h` | half | 2.0 |
| `q` | quarter | 1.0 |
| `e` | eighth | 0.5 |
| `s` | sixteenth | 0.25 |
| `x` | thirty-second | 0.125 |

### 10.2 Modifiers

Modifiers are appended directly to the base duration token:

| Modifier | Name | Multiplier | Example | Beats |
|----------|------|------------|---------|-------|
| `d` | dotted | ×1.5 | `qd` | 1.5 |
| `dd` | double-dotted | ×1.75 | `qdd` | 1.75 |
| `t` | triplet | ×(2/3) | `qt` | 0.6667 |

### 10.3 Duration Grammar

```
duration = base_duration modifier?
base_duration = "w" | "h" | "q" | "e" | "s" | "x"
modifier = "dd" | "d" | "t"
```

Note: `dd` (double-dotted) MUST be checked before `d` (dotted) when parsing.

The full set of valid duration strings is:

```
w  wd  wdd  wt
h  hd  hdd  ht
q  qd  qdd  qt
e  ed  edd  et
s  sd  sdd  st
x  xd  xdd  xt
```

Any string not in this set is **invalid** as a token duration.

### 10.4 Complete Duration Table

| Duration | Beats | Duration | Beats | Duration | Beats |
|----------|-------|----------|-------|----------|-------|
| `w` | 4.0 | `wd` | 6.0 | `wdd` | 7.0 |
| `wt` | 2.6667 | | | | |
| `h` | 2.0 | `hd` | 3.0 | `hdd` | 3.5 |
| `ht` | 1.3333 | | | | |
| `q` | 1.0 | `qd` | 1.5 | `qdd` | 1.75 |
| `qt` | 0.6667 | | | | |
| `e` | 0.5 | `ed` | 0.75 | `edd` | 0.875 |
| `et` | 0.3333 | | | | |
| `s` | 0.25 | `sd` | 0.375 | `sdd` | 0.4375 |
| `st` | 0.1667 | | | | |
| `x` | 0.125 | `xd` | 0.1875 | `xdd` | 0.21875 |
| `xt` | 0.0833 | | | | |

### 10.5 Numeric Durations (`dur_beats`)

For durations that cannot be expressed with tokens (64th notes, 128th notes, quintuplets, septuplets, or arbitrary timing), use `dur_beats` with a numeric value in quarter-note beats.

```yaml
{note: C4, dur_beats: 0.0625}  # 64th note
{note: C4, dur_beats: 0.2}     # quintuplet eighth (1/5 of a beat)
{note: C4, dur_beats: 0.4}     # arbitrary duration
```

Rules:
- `dur_beats` MUST be a positive number.
- An event MUST have exactly one of `dur` or `dur_beats`, not both.
- If both are present, the file is **invalid**.
- Rest events use `rest_beats` for numeric durations (see §12).
- Token durations are preferred for standard rhythms. Numeric durations are an escape hatch for values tokens cannot express.

### 10.6 MIDI Tick Conversion

To convert any duration to MIDI ticks: `ticks = duration_in_beats * PPQ` where PPQ is the MIDI file's pulses-per-quarter-note (recommended: 480).

## 11. Beat Positioning

Events within a bar are positioned in time using one of two modes. Both modes can coexist within the same bar.

### 11.1 Sequential Mode

If an event does **not** have a `beat` key, it is in **sequential mode**. Its start position is determined by the end position of the previous event in the bar.

- The first sequential event in a bar starts at beat 1.
- Each subsequent sequential event starts at `previous_start + previous_duration_in_beats`.

```yaml
# Sequential: C4 starts at beat 1, D4 at beat 2, E4 at beat 3
- {note: C4, dur: q}
- {note: D4, dur: q}
- {note: E4, dur: h}
```

### 11.2 Beat-Addressed Mode

If an event **has** a `beat` key, it is in **beat-addressed mode**. It starts at the specified beat position within the bar.

- Beat positions are 1-indexed (beat 1 is the start of the bar).
- Beat positions can be fractional (e.g. `1.5` for the "and" of beat 1 in 4/4).
- Multiple events CAN share the same beat position (they sound simultaneously).

```yaml
# Beat-addressed: explicit positions, kick and hh overlap on beat 1
- {beat: 1, note: kick, dur: q}
- {beat: 1, note: hh, dur: e}
- {beat: 2, note: snare, dur: q}
```

### 11.3 Mixed Mode

Sequential and beat-addressed events **MUST NOT** be mixed for note and rest events within the same bar. A bar containing note or rest events MUST use either sequential positioning (no `beat` key on any note/rest) or beat-addressed positioning (`beat` key on every note/rest).

**Automation and text events are exempt** from this restriction. CC, pitch bend, aftertouch, and text events are always beat-addressed (§14.4) and may appear alongside sequential note/rest events without triggering `MIXED_BAR_POSITIONING`.

```yaml
# VALID: sequential notes with beat-addressed automation
- - {note: C4, dur: q}
  - {note: D4, dur: q}
  - {beat: 1, cc: 64, value: 127}
  - {beat: 3, cc: 64, value: 0}

# VALID: all notes beat-addressed
- - {beat: 1, note: C4, dur: h}
  - {beat: 3, note: E4, dur: h}

# INVALID (MIXED_BAR_POSITIONING): some notes have beat, some don't
- - {beat: 1, note: [C4, E4, G4], dur: h}
  - {note: E4, dur: e}
  - {note: F4, dur: e}
```

### 11.4 Beat Validation

When all events in a bar are beat-addressed, validators SHOULD check that no event extends beyond the bar boundary. An event at beat `B` with duration `D` beats must satisfy:

```
B + D <= beats_per_bar + 1
```

For sequential bars, the total duration of all events SHOULD equal `beats_per_bar`. Validators MAY warn (not error) if the total is less than `beats_per_bar` (implied trailing rest) or error if greater.

Bar-total validation SHOULD use a tolerance of ±0.001 quarter-note units to accommodate floating-point accumulation (e.g. triplet sequences). Token durations SHOULD be evaluated as exact rational values internally before conversion to ticks.

If sequential event totals exceed `beats_per_bar + 0.001`, validators MUST emit `SEQUENTIAL_OVERFLOW`. If the total is within tolerance of `beats_per_bar`, no diagnostic is emitted. If the total is less than `beats_per_bar - 0.001`, validators MAY emit `BAR_DURATION_MISMATCH` as a warning.

### 11.5 Microtiming (Offset Beats)

The optional `offset_beats` field displaces an event from its computed beat position by a fractional number of quarter-note beats. This enables groove, humanization, swing, and drag/push feel without changing the event's quantized position.

- **Positive values** push the event **later** (behind the beat).
- **Negative values** pull the event **earlier** (ahead of the beat).
- The offset does **not** affect sequential cursor advancement. The cursor still advances by the note's full duration from the unmodified position.
- The offset does **not** change bar boundary validation. Validation uses the quantized position.
- `offset_beats` applies to note events, CC, pitch bend, aftertouch, and text events. It is **not valid on rest events** — rests represent silence and have no sounding output to displace.

```yaml
# Pushed hi-hat (slightly late) for groove
- {beat: 1.5, note: hh, dur: s, vel: 61, offset_beats: 0.015625}

# Pulled snare (slightly early) for drag feel
- {beat: 2, note: snare, dur: q, vel: 100, offset_beats: -0.01}

# Sequential note with microtiming
- {note: C4, dur: q, offset_beats: 0.02}
```

### 11.6 Timing Layer Order

When converting to MIDI, the final event time is computed by applying timing layers in this order:

1. **Base position**: beat-addressed position or sequential cursor position (1-indexed).
2. **Swing**: if the pattern has `swing` ≠ 50 and the event is on an off-beat eighth, apply swing displacement (see §6.3).
3. **Offset**: add `offset_beats` to the swung position.
4. **Tick conversion**: convert to absolute MIDI ticks.

```
swung_position = apply_swing(base_position, pattern.swing)
final_position = swung_position + offset_beats
absolute_beats = bar_start_beats + (final_position - 1)
actual_tick    = round(absolute_beats × PPQ)
```

Note the `- 1` in the formula: beat positions are 1-indexed, so beat 1 corresponds to the start of the bar (0 beats offset from bar start).

Negative final positions are allowed across internal bar boundaries — an event with a negative offset may land slightly before its bar. Converters MUST clamp only if the resulting absolute song tick is less than 0 (before the start of the song).

## 12. Rests

A rest event represents silence for a specified duration.

```yaml
{rest: q}             # quarter rest with duration token (canonical)
{rest_beats: 0.125}   # numeric rest: 32nd note duration
{rest_beats: 0.0625}  # numeric rest: 64th note
```

Rests participate in sequential positioning: they advance the cursor by their duration. Rests can also be beat-addressed:

```yaml
{beat: 3, rest: h}           # half rest starting at beat 3
{beat: 2, rest_beats: 0.5}   # numeric rest at beat 2
```

The `rest` key accepts only duration tokens (strings). The `rest_beats` key accepts only numeric values (quarter-note beats). An event MUST NOT contain both forms. This mirrors the `dur`/`dur_beats` split on note events.

## 13. Ties

A tie connects two consecutive notes of the same pitch, combining their durations into a single sustained sound.

```yaml
- {note: C4, dur: h, tie: true}
- {note: C4, dur: q}
```

The tied note and the following note MUST have the same pitch (or be chords with at least one common pitch). Validators SHOULD warn if pitches don't match.

When `tie: true` appears on a chord, tie resolution is performed independently for each pitch in the chord:

1. For each pitch P in the tied chord, if the next tie target contains P, P is sustained into that target.
2. If the next tie target does not contain P, P ends at its written duration and validators SHOULD emit a `TIE_TARGET_MISSING_PITCH` warning.
3. Pitches present only in the target chord start normally.

A chord tie does not require every pitch in both chords to match.

A tie at the end of a bar connects to the first matching event in the next bar of the same pattern.

### 13.1 Ties Across Section Boundaries

By default, ties are **released** at pattern boundaries. A tied note at the end of a pattern's last bar does not carry over when the arrangement moves to the next section.

If a section has `tie_across: true`, tied notes at the end of that section carry into the **next** arrangement section:

- The tie connects to the first matching pitch in the first bar of the next section's pattern for the **same track**.
- If the next section does not assign a pattern to that track, the tie is released.
- If the next section's pattern starts with a different pitch on that track, the tie is released and validators SHOULD warn.

Ties always carry across **repeat iterations** within a section. Each iteration's last bar can tie into the next iteration's first bar. The `tie_across` flag only controls behavior at the boundary between different sections.

### 13.2 Polyphonic Tie Disambiguation (Voice)

In polyphonic passages where multiple notes of the same pitch sound simultaneously or in close succession, the default tie-matching behavior ("first matching pitch in the next event") can be ambiguous.

The optional `voice` key (integer) on note events provides explicit disambiguation:

```yaml
# Two overlapping C4 voices, each tied independently
- - {beat: 1, note: C4, dur: h, tie: true, voice: 1}
  - {beat: 1, note: C4, dur: q, tie: true, voice: 2}
  - {beat: 2, note: C4, dur: q, voice: 2}     # continues voice 2
  - {beat: 3, note: C4, dur: h, voice: 1}      # continues voice 1
```

When `voice` is present on a tied note, the tie resolves to the next note with **both** the same pitch **and** the same `voice` value. If no `voice` is set, the default pitch-matching behavior applies.

In v1.0, `voice` is used **only** for tie disambiguation. It does not create an independent sequential cursor. Per-voice cursor semantics are reserved for a future spec version.

Voice numbers are arbitrary integers. They have no inherent meaning beyond tie disambiguation within the same pattern. Converters MAY use voice numbers to separate polyphonic lines into distinct MIDI tracks or piano-roll lanes.

```yaml
arrangement:
  - name: verse
    patterns:
      piano: piano_verse     # last note is tied
    tie_across: true          # carry into chorus
    repeat: 2

  - name: chorus
    patterns:
      piano: piano_chorus     # first note matches tied pitch
```

## 14. Control Change and Automation Events

In addition to note and rest events, bars may contain **control change (CC)** events for MIDI automation. These represent continuous controller messages, pitch bend, and channel aftertouch.

### 14.1 CC Events

A CC event sets a MIDI continuous controller value at a specific beat position.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `cc` | integer | **yes** | MIDI CC number (0–127). |
| `value` | integer | **yes** | CC value (0–127). |
| `beat` | number | no | Beat position within bar (1-indexed). Default: 1. |
| `interp` | string | no | Interpolation from previous value to this value: `"step"` (default) or `"linear"`. |
| `offset_beats` | number | no | Microtiming offset in quarter-note beats. See §11.5. |

```yaml
- {beat: 1, cc: 74, value: 20}     # filter cutoff low
- {beat: 3, cc: 74, value: 90}     # filter cutoff sweep up
- {beat: 1, cc: 1, value: 64}      # mod wheel
- {beat: 1, cc: 64, value: 127}    # sustain pedal on
- {beat: 4, cc: 64, value: 0}      # sustain pedal off
```

Common CC numbers:

| CC | Name | Description |
|----|------|-------------|
| 1 | Mod Wheel | Modulation |
| 7 | Volume | Channel volume |
| 10 | Pan | Stereo pan position |
| 11 | Expression | Expression controller |
| 64 | Sustain | Sustain pedal (0=off, 127=on) |
| 71 | Resonance | Filter resonance |
| 74 | Cutoff | Filter cutoff frequency |

### 14.2 Pitch Bend Events

A pitch bend event sets the pitch bend value for the track's channel.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `pitch_bend` | integer | **yes** | Pitch bend value (-8192 to 8191). 0 = center/no bend. |
| `beat` | number | no | Beat position within bar. Default: 1. |
| `interp` | string | no | Interpolation from previous value to this value: `"step"` (default) or `"linear"`. |
| `offset_beats` | number | no | Microtiming offset in quarter-note beats. See §11.5. |

```yaml
- {beat: 1, pitch_bend: 0}         # no bend
- {beat: 2, pitch_bend: 4096}      # bend up ~1 tone
- {beat: 3, pitch_bend: 8191}      # max bend up
- {beat: 4, pitch_bend: 0}         # release
```

### 14.3 Aftertouch Events

A channel aftertouch (pressure) event.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `aftertouch` | integer | **yes** | Aftertouch pressure value (0–127). |
| `beat` | number | no | Beat position within bar. Default: 1. |
| `interp` | string | no | Interpolation from previous value to this value: `"step"` (default) or `"linear"`. |
| `offset_beats` | number | no | Microtiming offset in quarter-note beats. See §11.5. |

```yaml
- {beat: 1, aftertouch: 0}
- {beat: 2, aftertouch: 80}
- {beat: 4, aftertouch: 0}
```

### 14.4 Automation Event Rules

- CC, pitch bend, aftertouch, and text events are **always beat-addressed**, regardless of whether they appear among sequential events. They never participate in sequential cursor advancement.
- If `beat` is omitted, it defaults to 1.
- They may appear in the same bar as note/rest events.
- CC, pitch bend, and aftertouch events are always tied to the track's MIDI channel.
- Canonical key order for CC events: `beat`, `cc`, `value`, `interp`, `offset_beats`.
- Canonical key order for pitch bend events: `beat`, `pitch_bend`, `interp`, `offset_beats`.
- Canonical key order for aftertouch events: `beat`, `aftertouch`, `interp`, `offset_beats`.

### 14.5 Interpolation Semantics

The `interp` field describes how to transition **from the previous value** of the same controller **to this event's value**:

- `"step"` (default): The value changes instantly at this event's beat position. This is the standard MIDI behavior.
- `"linear"`: The value ramps linearly from the previous event's value to this event's value over the time between the two events.

If no previous event exists for the same controller in the current pattern, the starting value is **0** (for CC and aftertouch) or **0 / center** (for pitch bend).

```yaml
# Linear filter sweep from 20 to 120 over beats 1-4
- {beat: 1, cc: 74, value: 20}
- {beat: 4, cc: 74, value: 120, interp: linear}

# Step change (default) — instant jump to 0 at beat 1
- {beat: 1, cc: 74, value: 0}
```

When converting to MIDI, `interp: linear` SHOULD be realized as a series of intermediate CC messages. The RECOMMENDED default ramp resolution is one intermediate message per 1/64 note (0.0625 beats, approximately 7.5 ticks at 480 PPQ). This provides smooth automation without excessive MIDI data. Converters MAY use finer or coarser resolution.

### 14.6 Text and Marker Events

A text event anchors a text string to a beat position within a bar. Text events support lyrics, rehearsal marks, chord symbols, and general annotations.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `text` | string | **yes** | The text content. |
| `type` | string | no | Event type: `"lyric"`, `"marker"`, `"rehearsal"`, `"chord"`, or `"text"` (default). |
| `beat` | number | no | Beat position within bar (1-indexed). Default: 1. |
| `offset_beats` | number | no | Microtiming offset in quarter-note beats. See §11.5. |

```yaml
# Lyrics
- {beat: 1, text: "Hel-", type: lyric}
- {beat: 2, text: "-lo", type: lyric}

# Rehearsal mark
- {beat: 1, text: "A", type: rehearsal}

# Chord symbol (annotation only — does not generate notes)
- {beat: 1, text: "Cmaj7", type: chord}
- {beat: 3, text: "Am7", type: chord}

# General marker
- {beat: 1, text: "Solo begins", type: marker}
```

Text events do **not** advance the sequential cursor and do **not** produce MIDI note data. They participate only in beat-addressed positioning.

When converting to MIDI:
- `type: lyric` → MIDI Lyric meta-event (FF 05).
- `type: marker` → MIDI Marker meta-event (FF 06).
- `type: rehearsal` → MIDI Marker meta-event (FF 06), prefixed with the text.
- `type: chord` → MIDI Text meta-event (FF 01) or converter-specific chord track.
- `type: text` (default) → MIDI Text meta-event (FF 01).

## 15. Drum Events

On tracks where `channel` is 10 (the GM percussion channel), pitches are specified using drum names instead of note-octave notation.

### 15.1 Default Drum Map

The default drum map provides human-readable names for GM percussion notes. See Appendix B for the full table.

Common drum names:

| Name | Aliases | MIDI Note | GM Name |
|------|---------|-----------|---------|
| `kick` | `bd`, `bass_drum` | 36 | Bass Drum 1 |
| `snare` | `sd` | 38 | Acoustic Snare |
| `snare_electric` | | 40 | Electric Snare |
| `clap` | `hc` | 39 | Hand Clap |
| `hh` | `hihat`, `closed_hihat` | 42 | Closed Hi-Hat |
| `hh_open` | `open_hihat` | 46 | Open Hi-Hat |
| `hh_pedal` | `pedal_hihat` | 44 | Pedal Hi-Hat |
| `ride` | `ride_cymbal` | 51 | Ride Cymbal 1 |
| `crash` | `crash_cymbal` | 49 | Crash Cymbal 1 |
| `tom1` | `high_tom` | 50 | High Tom |
| `tom2` | `hi_mid_tom` | 48 | Hi-Mid Tom |
| `tom3` | `low_mid_tom` | 47 | Low-Mid Tom |
| `tom4` | `low_tom` | 45 | Low Tom |
| `tom5` | `high_floor_tom` | 43 | High Floor Tom |
| `tom6` | `low_floor_tom` | 41 | Low Floor Tom |
| `rimshot` | `side_stick` | 37 | Side Stick |
| `cowbell` | | 56 | Cowbell |
| `tambourine` | `tamb` | 54 | Tambourine |
| `ride_bell` | | 53 | Ride Bell |

### 15.2 Custom Drum Map

A file MAY include a `drum_map` top-level key to define or override drum name mappings:

```yaml
drum_map:
  my_kick: 36
  ghost_snare: 38
  shaker: 70
```

Custom drum map entries are merged with the default map. If a custom name conflicts with a default name, the custom definition wins.

Resolution order for drum names: per-track `drum_map` (§5.1) > global `drum_map` > default GM drum map (Appendix B).

## 16. `drum_map` Object (Optional)

The optional `drum_map` mapping provides custom drum name → MIDI note number overrides.

| Key | Type | Description |
|-----|------|-------------|
| (drum name) | integer | MIDI note number (0–127) for this drum name. |

Drum names in the custom map follow the same naming rules as track names: `[a-zA-Z_][a-zA-Z0-9_]*`.

## 17. Canonical Form

The canonical form is the normalized representation produced by `muq fmt`. It defines a single unambiguous way to represent any valid `.muq` file.

Rules:
1. Events use YAML flow mapping style: `{note: C4, dur: q}`.
2. Note names are uppercase (`C4` not `c4`).
3. Drum names are lowercase (`kick` not `Kick`).
4. Key order for note events: `beat`, `note`, `dur`, `dur_beats`, `vel`, `tie`, `voice`, `offset_beats`, `articulation`.
5. Key order for rest events: `beat`, `rest`, `rest_beats`.
6. Key order for CC events: `beat`, `cc`, `value`, `interp`, `offset_beats`.
7. Key order for pitch bend events: `beat`, `pitch_bend`, `interp`, `offset_beats`.
8. Key order for aftertouch events: `beat`, `aftertouch`, `interp`, `offset_beats`.
9. Key order for text events: `beat`, `text`, `type`, `offset_beats`.
10. Default values are omitted (e.g. `vel: 80` is not written; `interp: step` is not written; `offset_beats: 0` is not written; `type: text` is not written on text events; `notation: pitched` is not written on patterns).
11. Top-level keys appear in order: `song`, `tracks`, `patterns`, `arrangement`, `drum_map`.
12. Arrangement `patterns` uses YAML block mapping style (one track→pattern per line).
13. Bars are represented as YAML block sequences of flow mappings.
14. Indentation is 2 spaces.
15. No trailing whitespace. File ends with a single newline.
16. YAML comments (`#`) are **not preserved** by `muq fmt`. Authors who need persistent annotations should use `text` events with `type: marker` instead.
17. Key signature tonic is uppercase with a single ASCII space before the mode: `C major`, `F# minor`, `Bb dorian`.

Input parsers MAY accept lowercase tonics (e.g. `c major`) and normalize them to uppercase canonical form. Canonical form uses a single ASCII space between tonic and mode.

## 18. Error Classes

Implementations MUST detect and report the following error classes:

### 18.1 Structural Errors

| Error | Description |
|-------|-------------|
| `MISSING_REQUIRED_KEY` | A required top-level key (`song`, `tracks`, `patterns`, `arrangement`) is missing. |
| `UNKNOWN_TOP_LEVEL_KEY` | An unrecognized top-level key is present. |
| `INVALID_YAML` | The file is not valid YAML. |

### 18.2 Song Errors

| Error | Description |
|-------|-------------|
| `MISSING_TEMPO` | `song.tempo` is missing. |
| `MISSING_TIME` | `song.time` is missing. |
| `INVALID_TEMPO` | `song.tempo` is not a number in range 1–999. |
| `INVALID_TIME_SIGNATURE` | `song.time` does not match `N/D` format or D is not a power of 2. |

### 18.3 Track Errors

| Error | Description |
|-------|-------------|
| `MISSING_INSTRUMENT` | Track is missing `instrument`. |
| `MISSING_CHANNEL` | Track is missing `channel`. |
| `INVALID_CHANNEL` | Channel is not an integer 1–16. |
| `UNKNOWN_INSTRUMENT` | Instrument name is not in the GM instrument table or custom drum map. |
| `DRUM_CHANNEL_MISMATCH` | Percussion track without `percussion: true` on non-10 channel, or non-percussion instrument on channel 10 (warning). |

### 18.4 Pattern Errors

| Error | Description |
|-------|-------------|
| `MISSING_BARS` | Pattern is missing `bars`. |
| `EMPTY_PATTERN` | Pattern has zero bars. |
| `MIXED_PITCH_NOTATION` | Pattern contains note events that do not match its declared `notation` style. |
| `INVALID_NOTATION` | `notation` is not `"pitched"` or `"percussion"`. |
| `MIXED_BAR_POSITIONING` | A bar contains note/rest events with both sequential and beat-addressed positioning. See §11.3. |

### 18.5 Event Errors

| Error | Description |
|-------|-------------|
| `MISSING_NOTE_AND_REST` | Event has neither `note` nor `rest`/`rest_beats` (and is not a CC/pitch_bend/aftertouch/text event). |
| `NOTE_AND_REST_CONFLICT` | Event has both `note` and `rest`/`rest_beats`. |
| `MISSING_DURATION` | Note event is missing both `dur` and `dur_beats`. |
| `DURATION_CONFLICT` | Event has both token duration (`dur`) and numeric duration (`dur_beats`). |
| `REST_CONFLICT` | Event has both token rest (`rest`) and numeric rest (`rest_beats`). |
| `INVALID_DURATION` | Duration string is not a valid token (see §10.3). |
| `INVALID_DURATION_BEATS` | `dur_beats` is not a positive number. |
| `INVALID_REST_BEATS` | `rest_beats` is not a positive number. |
| `INVALID_PITCH` | Pitch string does not match the pitch grammar (see §9). |
| `PITCH_OUT_OF_RANGE` | Computed MIDI note number is outside 0–127. |
| `INVALID_VELOCITY` | Velocity is not an integer 1–127. |
| `INVALID_VOICE` | `voice` is not an integer. |
| `UNKNOWN_DRUM_NAME` | Drum name is not in default or custom drum map. |
| `INVALID_CC_NUMBER` | CC number is not an integer 0–127. |
| `INVALID_CC_VALUE` | CC value is not an integer 0–127. |
| `INVALID_PITCH_BEND` | Pitch bend value is not an integer -8192–8191. |
| `INVALID_AFTERTOUCH` | Aftertouch value is not an integer 0–127. |
| `INVALID_INTERP` | `interp` value is not `"step"` or `"linear"`. |
| `INVALID_OFFSET_BEATS` | `offset_beats` is not a number. |
| `INVALID_TEXT_TYPE` | `type` is not one of `"lyric"`, `"marker"`, `"rehearsal"`, `"chord"`, `"text"`. |
| `OUT_OF_SCALE` | Note pitch is outside the declared scale (when `scale_mode` is `strict`). |
| `INVALID_ARTICULATION` | `articulation` is not a recognized value, or is set on a rest/text event. |

### 18.6 Beat Errors

| Error | Description |
|-------|-------------|
| `BEAT_OUT_OF_RANGE` | Beat position is less than 1 or exceeds beats per bar. |
| `BEAT_OVERFLOW` | An event's beat + duration exceeds the bar boundary. |
| `SEQUENTIAL_OVERFLOW` | Total duration of sequential events exceeds beats per bar. |
| `BAR_DURATION_MISMATCH` | Total duration of sequential events is less than beats per bar minus tolerance (warning). |

### 18.7 Arrangement Errors

| Error | Description |
|-------|-------------|
| `UNKNOWN_PATTERN` | Section references a pattern not defined in `patterns`. |
| `UNKNOWN_TRACK_IN_SECTION` | Section `patterns` mapping references a track not defined in `tracks`. |
| `INVALID_REPEAT` | Repeat count is not a positive integer. |
| `INVALID_SECTION_TEMPO` | Section tempo override is not a valid QPM value. |
| `TEMPO_EVENT_OUT_OF_RANGE` | A `tempo_events` entry has a `bar` exceeding the section's bar count. |
| `INVALID_TEMPO_EVENT` | A tempo event is missing required fields or has invalid values. |
| `METER_EVENT_OUT_OF_RANGE` | A `meter_events` entry has a `bar` exceeding the section's bar count. |
| `INVALID_METER_EVENT` | A meter event is missing required fields or has an invalid time signature. |
| `TIE_ACROSS_NO_MATCH` | `tie_across` is true but the next section has no matching track/pitch (warning). |
| `DRUM_MAP_NON_PERCUSSION` | Per-track `drum_map` is set on a non-percussion track (warning). |
| `NOTATION_TRACK_MISMATCH` | A section binds a `notation: percussion` pattern to a non-percussion track, or a `notation: pitched` pattern to a percussion track (warning). |

### 18.8 Key Errors

| Error | Description |
|-------|-------------|
| `INVALID_KEY_SIGNATURE` | `key` string does not match the grammar `<tonic> <mode>` with a recognized tonic and mode. |

### 18.9 Tie Errors

| Error | Description |
|-------|-------------|
| `TIE_TARGET_MISSING_PITCH` | A chord tie has pitches that do not appear in the tie target (warning). |

## 19. Future Considerations

The following features are being considered for future spec versions and are NOT part of the 1.0.0 specification:

- **Chord symbol expansion**: Automatic expansion of chord symbols (e.g. `Cmaj7`, `Am`) into pitch arrays. Text events (§14.6) can annotate chord names, but do not generate note data.
- **Pattern parameters / variables**: Parameterized patterns for generative composition.
- **Exponential / curve interpolation**: Additional `interp` modes beyond `step` and `linear` (e.g. `ease_in`, `ease_out`, `bezier`) for smoother automation curves.
- **Key-poly aftertouch**: Per-note aftertouch events (currently only channel aftertouch is supported).
- **MPE (MIDI Polyphonic Expression)**: Per-note pitch bend and pressure for microtonal and expressive performance.
- **Short-key aliases**: Optional compact key aliases (e.g. `n` for `note`, `d` for `dur`) for terseness. May be reintroduced as an optional compact mode in a future version.
- **Song-level groove templates**: A song-level `groove` object specifying humanization ranges for timing and velocity across all patterns.
- **Grace notes and ornaments**: Acciaccatura, appoggiatura, trills, mordents, turns, and other ornamental figures.
- **Program change events**: Mid-song instrument changes within a track (e.g. switching from clean to distorted guitar).
- **Pattern-level repeat**: A `repeat` key on the pattern `bars` level to reduce duplication of repeated phrases within a pattern.
- **Volta brackets / multiple endings**: First/second ending structures for repeat-with-alternate-ending workflows.
- **Dynamic markings**: Semantic dynamics (`pp`, `p`, `mp`, `mf`, `f`, `ff`, `sfz`) mapped to velocity ranges, as an alternative to raw velocity values.
- **Extended articulations**: Additional articulations for orchestral writing (pizzicato, arco, tremolo, col legno, harmonics, sul ponticello, con sordino, glissando).
- **Per-event swing / per-track swing**: Finer-grained swing control beyond pattern-level, enabling different swing amounts for different instruments within a pattern.
- **File includes / imports**: Splitting large compositions across files with a `$ref`-like mechanism for multi-movement works or shared pattern libraries.
- **Automation pattern layering**: Allowing multiple patterns per track per section (or a separate `automation` mapping) to separate note data from CC/pitch bend data for reusability.

## Appendix A: GM Instrument Names

The following table maps muq instrument names to General MIDI program numbers (0-indexed).

Parsers MUST accept these names case-insensitively. Canonical form uses the exact casing shown.

### Piano (0–7)

| Program | muq Name |
|---------|----------|
| 0 | `acoustic_grand_piano` |
| 1 | `bright_acoustic_piano` |
| 2 | `electric_grand_piano` |
| 3 | `honky_tonk_piano` |
| 4 | `electric_piano_1` |
| 5 | `electric_piano_2` |
| 6 | `harpsichord` |
| 7 | `clavinet` |

### Chromatic Percussion (8–15)

| Program | muq Name |
|---------|----------|
| 8 | `celesta` |
| 9 | `glockenspiel` |
| 10 | `music_box` |
| 11 | `vibraphone` |
| 12 | `marimba` |
| 13 | `xylophone` |
| 14 | `tubular_bells` |
| 15 | `dulcimer` |

### Organ (16–23)

| Program | muq Name |
|---------|----------|
| 16 | `drawbar_organ` |
| 17 | `percussive_organ` |
| 18 | `rock_organ` |
| 19 | `church_organ` |
| 20 | `reed_organ` |
| 21 | `accordion` |
| 22 | `harmonica` |
| 23 | `tango_accordion` |

### Guitar (24–31)

| Program | muq Name |
|---------|----------|
| 24 | `acoustic_guitar_nylon` |
| 25 | `acoustic_guitar_steel` |
| 26 | `electric_guitar_jazz` |
| 27 | `electric_guitar_clean` |
| 28 | `electric_guitar_muted` |
| 29 | `overdriven_guitar` |
| 30 | `distortion_guitar` |
| 31 | `guitar_harmonics` |

### Bass (32–39)

| Program | muq Name |
|---------|----------|
| 32 | `acoustic_bass` |
| 33 | `electric_bass_finger` |
| 34 | `electric_bass_pick` |
| 35 | `fretless_bass` |
| 36 | `slap_bass_1` |
| 37 | `slap_bass_2` |
| 38 | `synth_bass_1` |
| 39 | `synth_bass_2` |

### Strings (40–47)

| Program | muq Name |
|---------|----------|
| 40 | `violin` |
| 41 | `viola` |
| 42 | `cello` |
| 43 | `contrabass` |
| 44 | `tremolo_strings` |
| 45 | `pizzicato_strings` |
| 46 | `orchestral_harp` |
| 47 | `timpani` |

### Ensemble (48–55)

| Program | muq Name |
|---------|----------|
| 48 | `string_ensemble_1` |
| 49 | `string_ensemble_2` |
| 50 | `synth_strings_1` |
| 51 | `synth_strings_2` |
| 52 | `choir_aahs` |
| 53 | `voice_oohs` |
| 54 | `synth_choir` |
| 55 | `orchestra_hit` |

### Brass (56–63)

| Program | muq Name |
|---------|----------|
| 56 | `trumpet` |
| 57 | `trombone` |
| 58 | `tuba` |
| 59 | `muted_trumpet` |
| 60 | `french_horn` |
| 61 | `brass_section` |
| 62 | `synth_brass_1` |
| 63 | `synth_brass_2` |

### Reed (64–71)

| Program | muq Name |
|---------|----------|
| 64 | `soprano_sax` |
| 65 | `alto_sax` |
| 66 | `tenor_sax` |
| 67 | `baritone_sax` |
| 68 | `oboe` |
| 69 | `english_horn` |
| 70 | `bassoon` |
| 71 | `clarinet` |

### Pipe (72–79)

| Program | muq Name |
|---------|----------|
| 72 | `piccolo` |
| 73 | `flute` |
| 74 | `recorder` |
| 75 | `pan_flute` |
| 76 | `blown_bottle` |
| 77 | `shakuhachi` |
| 78 | `whistle` |
| 79 | `ocarina` |

### Synth Lead (80–87)

| Program | muq Name |
|---------|----------|
| 80 | `lead_square` |
| 81 | `lead_sawtooth` |
| 82 | `lead_calliope` |
| 83 | `lead_chiff` |
| 84 | `lead_charang` |
| 85 | `lead_voice` |
| 86 | `lead_fifths` |
| 87 | `lead_bass_lead` |

### Synth Pad (88–95)

| Program | muq Name |
|---------|----------|
| 88 | `pad_new_age` |
| 89 | `pad_warm` |
| 90 | `pad_polysynth` |
| 91 | `pad_choir` |
| 92 | `pad_bowed` |
| 93 | `pad_metallic` |
| 94 | `pad_halo` |
| 95 | `pad_sweep` |

### Synth Effects (96–103)

| Program | muq Name |
|---------|----------|
| 96 | `fx_rain` |
| 97 | `fx_soundtrack` |
| 98 | `fx_crystal` |
| 99 | `fx_atmosphere` |
| 100 | `fx_brightness` |
| 101 | `fx_goblins` |
| 102 | `fx_echoes` |
| 103 | `fx_sci_fi` |

### Ethnic (104–111)

| Program | muq Name |
|---------|----------|
| 104 | `sitar` |
| 105 | `banjo` |
| 106 | `shamisen` |
| 107 | `koto` |
| 108 | `kalimba` |
| 109 | `bagpipe` |
| 110 | `fiddle` |
| 111 | `shanai` |

### Percussive (112–119)

| Program | muq Name |
|---------|----------|
| 112 | `tinkle_bell` |
| 113 | `agogo` |
| 114 | `steel_drums` |
| 115 | `woodblock` |
| 116 | `taiko_drum` |
| 117 | `melodic_tom` |
| 118 | `synth_drum` |
| 119 | `reverse_cymbal` |

### Sound Effects (120–127)

| Program | muq Name |
|---------|----------|
| 120 | `guitar_fret_noise` |
| 121 | `breath_noise` |
| 122 | `seashore` |
| 123 | `bird_tweet` |
| 124 | `telephone_ring` |
| 125 | `helicopter` |
| 126 | `applause` |
| 127 | `gunshot` |

### Drum Kit

| muq Name | Description |
|----------|-------------|
| `standard` | GM Standard Kit (channel 10) |

## Appendix B: GM Drum Map

Default drum name → MIDI note mappings for channel 10.

| MIDI Note | muq Name | Aliases | GM Name |
|-----------|----------|---------|---------|
| 35 | `acoustic_bass_drum` | `kick2` | Acoustic Bass Drum |
| 36 | `kick` | `bd`, `bass_drum` | Bass Drum 1 |
| 37 | `rimshot` | `side_stick` | Side Stick |
| 38 | `snare` | `sd` | Acoustic Snare |
| 39 | `clap` | `hc`, `hand_clap` | Hand Clap |
| 40 | `snare_electric` | `sd2` | Electric Snare |
| 41 | `tom6` | `low_floor_tom` | Low Floor Tom |
| 42 | `hh` | `hihat`, `closed_hihat` | Closed Hi-Hat |
| 43 | `tom5` | `high_floor_tom` | High Floor Tom |
| 44 | `hh_pedal` | `pedal_hihat` | Pedal Hi-Hat |
| 45 | `tom4` | `low_tom` | Low Tom |
| 46 | `hh_open` | `open_hihat` | Open Hi-Hat |
| 47 | `tom3` | `low_mid_tom` | Low-Mid Tom |
| 48 | `tom2` | `hi_mid_tom` | Hi-Mid Tom |
| 49 | `crash` | `crash_cymbal`, `crash1` | Crash Cymbal 1 |
| 50 | `tom1` | `high_tom` | High Tom |
| 51 | `ride` | `ride_cymbal`, `ride1` | Ride Cymbal 1 |
| 52 | `chinese_cymbal` | | Chinese Cymbal |
| 53 | `ride_bell` | | Ride Bell |
| 54 | `tambourine` | `tamb` | Tambourine |
| 55 | `splash` | `splash_cymbal` | Splash Cymbal |
| 56 | `cowbell` | | Cowbell |
| 57 | `crash2` | `crash_cymbal_2` | Crash Cymbal 2 |
| 58 | `vibraslap` | | Vibraslap |
| 59 | `ride2` | `ride_cymbal_2` | Ride Cymbal 2 |
| 60 | `bongo_hi` | `hi_bongo` | Hi Bongo |
| 61 | `bongo_lo` | `low_bongo` | Low Bongo |
| 62 | `conga_mute` | `mute_hi_conga` | Mute Hi Conga |
| 63 | `conga_hi` | `open_hi_conga` | Open Hi Conga |
| 64 | `conga_lo` | `low_conga` | Low Conga |
| 65 | `timbale_hi` | `high_timbale` | High Timbale |
| 66 | `timbale_lo` | `low_timbale` | Low Timbale |
| 67 | `agogo_hi` | `high_agogo` | High Agogo |
| 68 | `agogo_lo` | `low_agogo` | Low Agogo |
| 69 | `cabasa` | | Cabasa |
| 70 | `maracas` | | Maracas |
| 71 | `whistle_short` | `short_whistle` | Short Whistle |
| 72 | `whistle_long` | `long_whistle` | Long Whistle |
| 73 | `guiro_short` | `short_guiro` | Short Guiro |
| 74 | `guiro_long` | `long_guiro` | Long Guiro |
| 75 | `claves` | | Claves |
| 76 | `woodblock_hi` | `hi_wood_block` | Hi Wood Block |
| 77 | `woodblock_lo` | `low_wood_block` | Low Wood Block |
| 78 | `cuica_mute` | `mute_cuica` | Mute Cuica |
| 79 | `cuica_open` | `open_cuica` | Open Cuica |
| 80 | `triangle_mute` | `mute_triangle` | Mute Triangle |
| 81 | `triangle_open` | `open_triangle` | Open Triangle |

## Appendix C: MIDI Conversion Reference

### C.1 Ticks and Tempo

When converting to Standard MIDI File (SMF):
- Use a resolution (PPQ — pulses per quarter note) of at least 480.
- Beat positions (1-indexed) convert to absolute ticks using the §11.6 formula:
  ```
  absolute_qbeats = bar_start_qbeats + (beat_position - 1)
  actual_tick = round(absolute_qbeats × PPQ)
  ```
- Tempo is encoded as microseconds per quarter note: `µs_per_beat = 60_000_000 / QPM`.

### C.2 Track Mapping

Each muq track maps to a separate MIDI track in a Type 1 MIDI file. The first MIDI track (track 0) contains tempo and time signature meta-events only.

### C.3 Track Initialization

At the start of each MIDI track (tick 0), exporters SHOULD emit:
- **Program Change** for the track's `instrument` (GM program number from Appendix A).
- **CC7 (Channel Volume)** for the track's `volume`.
- **CC10 (Pan)** for the track's `pan`.

These initialization events follow the same-tick ordering table (§C.5). Channel 10 tracks do not require a Program Change (the GM standard kit is the default).

### C.4 Channel 10

Channel 10 events use GM drum note mappings (Appendix B). No Program Change is needed for channel 10 (the GM standard kit is the default).

### C.5 Same-Tick Event Ordering

When multiple MIDI events share the same absolute tick, exporters MUST use the following deterministic ordering (lowest priority number first):

| Priority | Event Type |
|----------|-----------|
| 1 | Tempo meta-events (FF 51) |
| 2 | Time signature / key signature meta-events (FF 58, FF 59) |
| 3 | Program Change / Bank Select |
| 4 | CC events (control_change) |
| 5 | Pitch Bend events |
| 6 | Channel Aftertouch events |
| 7 | Text / Lyric / Marker meta-events (FF 01, FF 05, FF 06) |
| 8 | Note-off (note_off or note_on with velocity 0) |
| 9 | Note-on |

For same tick, same channel, same pitch: **note-off MUST precede note-on**. This avoids stuck or merged notes.

When two events have the same ordering priority, exporters MUST preserve source order after arrangement expansion.

### C.6 Microtiming

When an event has `offset_beats`, the actual MIDI tick position follows the §11.6 timing layer formula:

```
absolute_qbeats = bar_start_qbeats + (beat_position - 1)
actual_tick = round((absolute_qbeats + offset_beats) × PPQ)
```

Converters MUST NOT clamp events that land before their containing bar if the resulting absolute song tick is non-negative. They MUST clamp only if `actual_tick < 0` (before the start of the song). The `offset_beats` value is independent of PPQ — converters apply the multiplication at export time.

Example at 480 PPQ: an event at beat 1.5 in a bar starting at qbeat 4.0, with `offset_beats: 0.015625`, produces `actual_tick = round((4.0 + 0.5 + 0.015625) × 480) = round(2167.5) = 2168`.

### C.7 Meter Changes

Time signature meta-events (FF 58) are emitted on MIDI track 0 at the tick position corresponding to the start of the bar where the meter changes. The section-level `time` (or `song.time`) produces a time signature event at the section's start tick. Each `meter_events` entry produces an additional time signature event at the start of its bar.

### C.8 Text Meta-Events

Text events are emitted on MIDI track 0 (or the associated track's MIDI track, at the converter's discretion) at the tick position computed by the §11.6 / §C.6 formula (incorporating the 1-indexed beat offset and bar start position).

| muq type | MIDI meta-event |
|----------|----------------|
| `lyric` | FF 05 (Lyric) |
| `marker` | FF 06 (Marker) |
| `rehearsal` | FF 06 (Marker) |
| `chord` | FF 01 (Text Event) |
| `text` | FF 01 (Text Event) |
