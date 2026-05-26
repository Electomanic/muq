"""Tests for muq — parse, validate, resolve, export, fmt."""

from __future__ import annotations

from pathlib import Path

import pytest

from muq.parser import parse, ParseError
from muq.validate import validate
from muq.resolve import resolve, resolve_pattern
from muq.midi import to_midi
from muq.fmt import fmt
from muq.gm import pitch_to_midi, is_pitched_notation, DURATION_TOKENS, beats_per_bar, GM_INSTRUMENTS, GM_DRUM_MAP

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "spec" / "examples"
INVALID_DIR = Path(__file__).resolve().parent.parent / "spec" / "invalid"


# ---------------------------------------------------------------------------
# GM tables
# ---------------------------------------------------------------------------

class TestGM:
    def test_instrument_count(self):
        assert len(GM_INSTRUMENTS) == 128

    def test_c4_is_60(self):
        assert pitch_to_midi("C4") == 60

    def test_a4_is_69(self):
        assert pitch_to_midi("A4") == 69

    def test_sharps(self):
        assert pitch_to_midi("C#4") == 61
        assert pitch_to_midi("F##4") == 67

    def test_flats(self):
        assert pitch_to_midi("Bb3") == 58
        assert pitch_to_midi("Dbb4") == 60

    def test_pitch_out_of_range(self):
        with pytest.raises(ValueError):
            pitch_to_midi("C11")

    def test_duration_tokens(self):
        assert DURATION_TOKENS["q"] == 1.0
        assert DURATION_TOKENS["e"] == 0.5
        assert DURATION_TOKENS["qd"] == 1.5
        assert DURATION_TOKENS["x"] == 0.125
        assert len(DURATION_TOKENS) == 24

    def test_beats_per_bar(self):
        assert beats_per_bar("4/4") == 4.0
        assert beats_per_bar("3/4") == 3.0
        assert beats_per_bar("6/8") == 3.0
        assert beats_per_bar("7/8") == 3.5

    def test_drum_map_kick(self):
        assert GM_DRUM_MAP["kick"] == 36
        assert GM_DRUM_MAP["bd"] == 36
        assert GM_DRUM_MAP["bass_drum"] == 36

    def test_is_pitched_notation(self):
        assert is_pitched_notation("C4") is True
        assert is_pitched_notation("F#3") is True
        assert is_pitched_notation("Bb-1") is True
        assert is_pitched_notation("kick") is False
        assert is_pitched_notation("snare") is False
        assert is_pitched_notation("hh") is False
        assert is_pitched_notation("tom1") is False


# ---------------------------------------------------------------------------
# Parser — valid examples
# ---------------------------------------------------------------------------

class TestParseValidExamples:
    @pytest.fixture(params=sorted(EXAMPLES_DIR.glob("*.muq")), ids=lambda p: p.stem)
    def example_path(self, request):
        return request.param

    def test_parse_succeeds(self, example_path):
        doc = parse(example_path)
        assert doc.song is not None
        assert len(doc.tracks) > 0
        assert len(doc.patterns) > 0
        assert len(doc.arrangement) > 0


# ---------------------------------------------------------------------------
# Parser — invalid examples
# ---------------------------------------------------------------------------

class TestParseInvalidExamples:
    def test_missing_song(self):
        with pytest.raises(ParseError):
            parse(INVALID_DIR / "missing_song.muq")

    def test_bad_duration(self):
        with pytest.raises(ParseError):
            parse(INVALID_DIR / "bad_duration.muq")

    def test_duration_conflict(self):
        with pytest.raises(ParseError):
            parse(INVALID_DIR / "duration_conflict.muq")

    def test_rest_conflict(self):
        with pytest.raises(ParseError):
            parse(INVALID_DIR / "rest_conflict.muq")

    def test_beat_overflow_passes_schema(self):
        # beat_overflow.muq is a semantic-only error, passes schema
        doc = parse(INVALID_DIR / "beat_overflow.muq")
        assert doc is not None


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_examples_no_errors(self):
        for path in sorted(EXAMPLES_DIR.glob("*.muq")):
            doc = parse(path)
            diags = validate(doc)
            errors = [d for d in diags if d.severity == "error"]
            assert errors == [], f"{path.name}: {errors}"

    def test_minimal_clean(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        diags = validate(doc)
        assert len(diags) == 0

    def test_mixed_pitch_notation(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  mixed:
    notation: pitched
    bars:
    - [{note: C4, dur: q}, {note: kick, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: mixed
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "MIXED_PITCH_NOTATION" in codes

    def test_drum_notation_with_pitched_notes(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  drums:
    instrument: standard
    channel: 10
    percussion: true
patterns:
  bad:
    notation: percussion
    bars:
    - [{note: C4, dur: q}]
arrangement:
  - name: main
    patterns:
      drums: bad
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "MIXED_PITCH_NOTATION" in codes

    def test_notation_track_mismatch_warning(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  beat:
    notation: percussion
    bars:
    - [{note: kick, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: beat
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "NOTATION_TRACK_MISMATCH" in codes
        assert all(d.severity == "warning" for d in diags if d.code == "NOTATION_TRACK_MISMATCH")

    def test_pure_drum_pattern_ok(self):
        doc = parse(EXAMPLES_DIR / "drums.muq")
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "MIXED_PITCH_NOTATION" not in codes

    def test_pure_pitched_pattern_ok(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "MIXED_PITCH_NOTATION" not in codes


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_minimal_resolve(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        resolved = resolve(doc, ppq=480)
        assert resolved.ppq == 480
        assert len(resolved.tempos) >= 1
        assert resolved.tempos[0].tempo_qpm == 120
        assert len(resolved.tracks) == 1
        # One whole note
        track = resolved.tracks[0]
        assert len(track.notes) == 1
        note = track.notes[0]
        assert note.midi_note == 60  # C4
        assert note.tick == 0
        assert note.duration_ticks == 480 * 4  # whole note

    def test_drums_resolve(self):
        doc = parse(EXAMPLES_DIR / "drums.muq")
        resolved = resolve(doc)
        # Should have at least one track with percussion notes
        drum_tracks = [t for t in resolved.tracks if t.program is None]
        assert len(drum_tracks) >= 1
        assert len(drum_tracks[0].notes) > 0

    def test_short_pattern_loops_to_fill_section(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  drums:
    instrument: standard
    channel: 10
  bass:
    instrument: acoustic_bass
    channel: 2
patterns:
  one_bar:
    notation: percussion
    bars:
      - - {beat: 1, note: kick, dur: q, vel: 100}
  two_bar:
    bars:
      - - {note: C2, dur: w, vel: 80}
      - - {note: G2, dur: w, vel: 80}
arrangement:
  - name: main
    patterns:
      drums: one_bar
      bass: two_bar
"""
        doc = parse(yaml_str)
        resolved = resolve(doc, ppq=480)
        drum_track = [t for t in resolved.tracks if t.program is None][0]
        bass_track = [t for t in resolved.tracks if t.program is not None][0]
        # 1-bar drum pattern should loop to fill 2-bar section
        assert len(drum_track.notes) == 2  # kick in bar 1, kick in bar 2
        assert drum_track.notes[0].tick == 0
        assert drum_track.notes[1].tick == 480 * 4  # start of bar 2
        # Bass should play normally across 2 bars
        assert len(bass_track.notes) == 2

    def test_same_pitch_overlap_clamped(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  drums:
    instrument: standard
    channel: 10
patterns:
  overlap:
    notation: percussion
    bars:
      - - {beat: 1, note: hh, dur: q, vel: 80}
        - {beat: 1.5, note: hh, dur: q, vel: 60}
arrangement:
  - name: main
    patterns:
      drums: overlap
"""
        doc = parse(yaml_str)
        resolved = resolve(doc, ppq=480)
        notes = resolved.tracks[0].notes
        assert len(notes) == 2
        # First note should be clamped: ends 1 tick before second starts
        a, b = notes[0], notes[1]
        assert a.tick + a.duration_ticks < b.tick


# ---------------------------------------------------------------------------
# Clip export (resolve_pattern)
# ---------------------------------------------------------------------------

class TestClipExport:
    def test_resolve_pitched_pattern(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        resolved = resolve_pattern(doc, "melody")
        assert len(resolved.tracks) == 1
        assert resolved.tracks[0].program is not None  # melodic
        assert len(resolved.tracks[0].notes) == 1
        assert resolved.tracks[0].notes[0].midi_note == 60

    def test_resolve_drum_pattern(self):
        doc = parse(EXAMPLES_DIR / "drums.muq")
        # Get first pattern name
        pname = next(iter(doc.patterns))
        resolved = resolve_pattern(doc, pname)
        assert len(resolved.tracks) == 1
        assert resolved.tracks[0].program is None  # percussion
        assert len(resolved.tracks[0].notes) > 0

    def test_clip_has_tempo_and_time_sig(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        resolved = resolve_pattern(doc, "melody")
        assert resolved.tempos[0].tempo_qpm == 120
        assert resolved.time_signatures[0].numerator == 4
        assert resolved.time_signatures[0].denominator == 4

    def test_all_patterns_export_as_clips(self):
        for path in sorted(EXAMPLES_DIR.glob("*.muq")):
            doc = parse(path)
            diags = validate(doc)
            errors = [d for d in diags if d.severity == "error"]
            if errors:
                continue
            for pname in doc.patterns:
                resolved = resolve_pattern(doc, pname)
                mid = to_midi(resolved)
                assert mid.type == 1, f"{path.name}:{pname} failed"


# ---------------------------------------------------------------------------
# MIDI export
# ---------------------------------------------------------------------------

class TestMidi:
    def test_minimal_midi(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        resolved = resolve(doc)
        mid = to_midi(resolved)
        assert mid.type == 1
        assert mid.ticks_per_beat == 480
        assert len(mid.tracks) == 2  # tempo track + 1 instrument track

    def test_full_song_midi(self):
        doc = parse(EXAMPLES_DIR / "full_song.muq")
        resolved = resolve(doc)
        mid = to_midi(resolved)
        assert mid.type == 1
        assert len(mid.tracks) >= 2

    def test_all_examples_export(self):
        for path in sorted(EXAMPLES_DIR.glob("*.muq")):
            doc = parse(path)
            diags = validate(doc)
            errors = [d for d in diags if d.severity == "error"]
            if errors:
                continue
            resolved = resolve(doc)
            mid = to_midi(resolved)
            assert mid.type == 1, f"{path.name} failed"


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

class TestFmt:
    def test_minimal_roundtrip(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        output = fmt(doc)
        # Parse the formatted output to ensure it's valid
        doc2 = parse(output)
        assert doc2.song.tempo == doc.song.tempo
        assert doc2.song.time == doc.song.time

    def test_idempotent(self):
        doc = parse(EXAMPLES_DIR / "minimal.muq")
        output1 = fmt(doc)
        doc2 = parse(output1)
        output2 = fmt(doc2)
        assert output1 == output2

    def test_yaml_reserved_words_roundtrip(self):
        """Titles like 'false', 'null', 'yes' must survive fmt round-trip."""
        for title in ("false", "null", "yes", "no", "true", "off", "on"):
            yaml_str = f"""
song:
  title: "{title}"
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  p:
    bars:
    - [{{note: C4, dur: q}}]
arrangement:
  - name: main
    patterns:
      piano: p
"""
            doc = parse(yaml_str)
            output = fmt(doc)
            doc2 = parse(output)
            assert doc2.song.title == title, f"Title '{title}' did not round-trip"


# ---------------------------------------------------------------------------
# Regression tests (review items)
# ---------------------------------------------------------------------------

class TestRegressions:
    def test_mixed_positioning_is_error(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  mixed:
    bars:
    - [{note: C4, dur: q}, {beat: 3, note: E4, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: mixed
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "MIXED_BAR_POSITIONING" in codes

    def test_beat_1_exports_at_tick_0(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  p:
    bars:
    - [{beat: 1, note: C4, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: p
"""
        doc = parse(yaml_str)
        resolved = resolve(doc, ppq=480)
        assert resolved.tracks[0].notes[0].tick == 0

    def test_sequential_overflow_is_error(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  overflow:
    bars:
    - [{note: C4, dur: w}, {note: D4, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: overflow
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        seq = [d for d in diags if d.code == "SEQUENTIAL_OVERFLOW"]
        assert len(seq) == 1
        assert seq[0].severity == "error"

    def test_6_8_validates_as_3_quarter_units(self):
        assert beats_per_bar("6/8") == 3.0

    def test_same_tick_note_off_before_note_on(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  p:
    bars:
    - [{note: C4, dur: q}, {note: C4, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: p
"""
        doc = parse(yaml_str)
        resolved = resolve(doc, ppq=480)
        mid = to_midi(resolved)
        # Find same-tick events on the instrument track
        track = mid.tracks[1]
        tick = 0
        events_at_tick: dict[int, list] = {}
        for msg in track:
            tick += msg.time
            events_at_tick.setdefault(tick, []).append(msg)
        # At tick 480 (beat 2), note_off should precede note_on
        at_480 = events_at_tick.get(480, [])
        types = [m.type for m in at_480 if hasattr(m, 'type') and m.type in ('note_on', 'note_off')]
        assert types == ["note_off", "note_on"]

    def test_scale_validation_catches_out_of_key(self):
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
  key: C major
  scale_mode: warn
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
patterns:
  p:
    bars:
    - [{note: F#4, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: p
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        codes = [d.code for d in diags]
        assert "OUT_OF_SCALE" in codes

    def test_pattern_reuse_pitched_and_percussion(self):
        """Same pattern bound to pitched + percussion track validates per binding."""
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
  drums:
    instrument: standard
    channel: 10
    percussion: true
patterns:
  shared:
    bars:
    - [{note: C4, dur: q}]
arrangement:
  - name: sec1
    patterns:
      piano: shared
  - name: sec2
    patterns:
      drums: shared
"""
        doc = parse(yaml_str)
        diags = validate(doc)
        # Should validate C4 as pitched for piano (valid) AND as drum for drums (unknown)
        codes = [d.code for d in diags]
        # Piano binding: C4 is a valid pitched note, no error
        # Drums binding: C4 is not a known drum name → UNKNOWN_DRUM_NAME
        assert "UNKNOWN_DRUM_NAME" in codes
        # Also expect NOTATION_TRACK_MISMATCH for drums binding
        assert "NOTATION_TRACK_MISMATCH" in codes

    def test_meter_events_emit_once_not_per_track(self):
        """Meter events should not be duplicated per track."""
        yaml_str = """
song:
  tempo: 120
  time: "4/4"
tracks:
  piano:
    instrument: acoustic_grand_piano
    channel: 1
  bass:
    instrument: acoustic_bass
    channel: 2
patterns:
  p1:
    bars:
    - [{note: C4, dur: q}]
    - [{note: D4, dur: q}]
  p2:
    bars:
    - [{note: E2, dur: q}]
    - [{note: F2, dur: q}]
arrangement:
  - name: main
    patterns:
      piano: p1
      bass: p2
    meter_events:
      - {bar: 2, time: "3/4"}
"""
        doc = parse(yaml_str)
        resolved = resolve(doc, ppq=480)
        # Should have exactly 2 time sigs: initial 4/4 + one 3/4 change
        assert len(resolved.time_signatures) == 2
        assert resolved.time_signatures[0].numerator == 4
        assert resolved.time_signatures[1].numerator == 3

    def test_fmt_yaml_reserved_scalars_quoted(self):
        """Formatter must quote YAML boolean/null-like scalars."""
        from muq.fmt import _yaml_scalar
        for word in ("true", "false", "null", "yes", "no", "on", "off"):
            result = _yaml_scalar(word)
            assert result.startswith('"'), f"'{word}' should be quoted, got: {result}"
