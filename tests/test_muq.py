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
        assert resolved.tempos[0].tempo_bpm == 120
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
        assert resolved.tempos[0].tempo_bpm == 120
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
