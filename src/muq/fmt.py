"""Canonical formatter — produce normalized muq output per §17 rules."""

from __future__ import annotations

from collections import OrderedDict
from io import StringIO
from typing import Any

import yaml


from muq.model import (
    AftertouchEvent,
    CCEvent,
    MuqDocument,
    NoteEvent,
    PitchBendEvent,
    RestEvent,
    TextEvent,
)


def fmt(doc: MuqDocument) -> str:
    """Format a MuqDocument into canonical muq YAML text."""
    out = StringIO()

    # song
    out.write("song:\n")
    _write_song(out, doc)

    # tracks
    out.write("\ntracks:\n")
    _write_tracks(out, doc)

    # patterns
    out.write("\npatterns:\n")
    _write_patterns(out, doc)

    # arrangement
    out.write("\narrangement:\n")
    _write_arrangement(out, doc)

    # drum_map
    if doc.drum_map:
        out.write("\ndrum_map:\n")
        for name, note in doc.drum_map.items():
            out.write(f"  {name}: {note}\n")

    return out.getvalue()


def _normalize_key(key: str) -> str:
    """Normalize key to canonical form: uppercase tonic, single space."""
    parts = key.split()
    if len(parts) >= 2:
        tonic = parts[0][0].upper() + parts[0][1:]
        return f"{tonic} {parts[1]}"
    return key


def _write_song(out: StringIO, doc: MuqDocument) -> None:
    s = doc.song
    if s.title is not None:
        out.write(f"  title: {_yaml_scalar(s.title)}\n")
    if s.artist is not None:
        out.write(f"  artist: {_yaml_scalar(s.artist)}\n")
    out.write(f"  tempo: {_num(s.tempo)}\n")
    out.write(f"  time: \"{s.time}\"\n")
    if s.key is not None:
        out.write(f"  key: {_yaml_scalar(_normalize_key(s.key))}\n")
    if s.scale_mode is not None:
        out.write(f"  scale_mode: {s.scale_mode}\n")
    if s.spec_version != "1.0.0":
        out.write(f"  spec_version: \"{s.spec_version}\"\n")


def _write_tracks(out: StringIO, doc: MuqDocument) -> None:
    for name, track in doc.tracks.items():
        out.write(f"  {name}:\n")
        out.write(f"    instrument: {track.instrument}\n")
        out.write(f"    channel: {track.channel}\n")
        if track.volume != 100:
            out.write(f"    volume: {track.volume}\n")
        if track.pan != "center" and track.pan != 64:
            out.write(f"    pan: {_yaml_scalar(track.pan)}\n")
        if track.percussion is not None:
            out.write(f"    percussion: {str(track.percussion).lower()}\n")
        if track.drum_map:
            out.write("    drum_map:\n")
            for dn, dv in track.drum_map.items():
                out.write(f"      {dn}: {dv}\n")


def _write_patterns(out: StringIO, doc: MuqDocument) -> None:
    for name, pattern in doc.patterns.items():
        out.write(f"  {name}:\n")
        if pattern.notation != "pitched":
            out.write(f"    notation: {pattern.notation}\n")
        if pattern.swing != 50:
            out.write(f"    swing: {pattern.swing}\n")
        out.write("    bars:\n")
        for bar in pattern.bars:
            if not bar:
                out.write("    - []\n")
                continue
            out.write("    -\n")
            for event in bar:
                flow = _event_to_flow(event)
                out.write(f"      - {flow}\n")


def _write_arrangement(out: StringIO, doc: MuqDocument) -> None:
    for section in doc.arrangement:
        out.write(f"  - name: {_yaml_scalar(section.name)}\n")
        if section.tempo is not None:
            out.write(f"    tempo: {_num(section.tempo)}\n")
        if section.time is not None:
            out.write(f"    time: \"{section.time}\"\n")
        if section.repeat != 1:
            out.write(f"    repeat: {section.repeat}\n")
        if section.tie_across:
            out.write("    tie_across: true\n")
        if section.pickup_beats is not None:
            out.write(f"    pickup_beats: {_num(section.pickup_beats)}\n")
        out.write("    patterns:\n")
        for tname, pname in section.patterns.items():
            out.write(f"      {tname}: {pname}\n")
        if section.tempo_events:
            out.write("    tempo_events:\n")
            for te in section.tempo_events:
                out.write(f"      - {{bar: {te.bar}, beat: {_num(te.beat)}, tempo: {_num(te.tempo)}")
                if te.interp != "step":
                    out.write(f", interp: {te.interp}")
                out.write("}\n")
        if section.meter_events:
            out.write("    meter_events:\n")
            for me in section.meter_events:
                out.write(f"      - {{bar: {me.bar}, time: \"{me.time}\"}}\n")


# ---------------------------------------------------------------------------
# Event flow formatting
# ---------------------------------------------------------------------------

def _event_to_flow(event) -> str:
    """Render an event as a YAML flow mapping string with canonical key order."""
    if isinstance(event, NoteEvent):
        return _note_flow(event)
    if isinstance(event, RestEvent):
        return _rest_flow(event)
    if isinstance(event, CCEvent):
        return _cc_flow(event)
    if isinstance(event, PitchBendEvent):
        return _pb_flow(event)
    if isinstance(event, AftertouchEvent):
        return _at_flow(event)
    if isinstance(event, TextEvent):
        return _text_flow(event)
    return "{}"


def _note_flow(e: NoteEvent) -> str:
    # Key order: beat, note, dur, dur_beats, vel, tie, voice, offset_beats, articulation
    parts: list[str] = []
    if e.beat is not None:
        parts.append(f"beat: {_num(e.beat)}")
    # note value
    if isinstance(e.note, list):
        pitches = ", ".join(_pitch_canonical(p) for p in e.note)
        parts.append(f"note: [{pitches}]")
    else:
        parts.append(f"note: {_pitch_canonical(e.note)}")
    if e.dur is not None:
        parts.append(f"dur: {e.dur}")
    if e.dur_beats is not None:
        parts.append(f"dur_beats: {_num(e.dur_beats)}")
    # Omit defaults
    if e.vel != 80:
        parts.append(f"vel: {e.vel}")
    if e.tie:
        parts.append("tie: true")
    if e.voice is not None:
        parts.append(f"voice: {e.voice}")
    if e.offset_beats != 0.0:
        parts.append(f"offset_beats: {_num(e.offset_beats)}")
    if e.articulation is not None:
        parts.append(f"articulation: {e.articulation}")
    return "{" + ", ".join(parts) + "}"


def _rest_flow(e: RestEvent) -> str:
    # Key order: beat, rest, rest_beats
    parts: list[str] = []
    if e.beat is not None:
        parts.append(f"beat: {_num(e.beat)}")
    if e.rest is not None:
        parts.append(f"rest: {e.rest}")
    if e.rest_beats is not None:
        parts.append(f"rest_beats: {_num(e.rest_beats)}")
    return "{" + ", ".join(parts) + "}"


def _cc_flow(e: CCEvent) -> str:
    parts: list[str] = []
    if e.beat is not None and e.beat != 1.0:
        parts.append(f"beat: {_num(e.beat)}")
    parts.append(f"cc: {e.cc}")
    parts.append(f"value: {e.value}")
    if e.interp != "step":
        parts.append(f"interp: {e.interp}")
    if e.offset_beats != 0.0:
        parts.append(f"offset_beats: {_num(e.offset_beats)}")
    return "{" + ", ".join(parts) + "}"


def _pb_flow(e: PitchBendEvent) -> str:
    parts: list[str] = []
    if e.beat is not None and e.beat != 1.0:
        parts.append(f"beat: {_num(e.beat)}")
    parts.append(f"pitch_bend: {e.pitch_bend}")
    if e.interp != "step":
        parts.append(f"interp: {e.interp}")
    if e.offset_beats != 0.0:
        parts.append(f"offset_beats: {_num(e.offset_beats)}")
    return "{" + ", ".join(parts) + "}"


def _at_flow(e: AftertouchEvent) -> str:
    parts: list[str] = []
    if e.beat is not None and e.beat != 1.0:
        parts.append(f"beat: {_num(e.beat)}")
    parts.append(f"aftertouch: {e.aftertouch}")
    if e.interp != "step":
        parts.append(f"interp: {e.interp}")
    if e.offset_beats != 0.0:
        parts.append(f"offset_beats: {_num(e.offset_beats)}")
    return "{" + ", ".join(parts) + "}"


def _text_flow(e: TextEvent) -> str:
    parts: list[str] = []
    if e.beat is not None and e.beat != 1.0:
        parts.append(f"beat: {_num(e.beat)}")
    parts.append(f"text: {_yaml_scalar(e.text)}")
    if e.type != "text":
        parts.append(f"type: {e.type}")
    if e.offset_beats != 0.0:
        parts.append(f"offset_beats: {_num(e.offset_beats)}")
    return "{" + ", ".join(parts) + "}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pitch_canonical(p: str) -> str:
    """Uppercase note name for canonical form."""
    if not p:
        return p
    # Check if it's a pitched notation (letter + optional accidental + octave)
    from muq.gm import is_pitched_notation
    if is_pitched_notation(p):
        return p[0].upper() + p[1:]
    # Drum name → lowercase
    return p.lower()


def _num(v) -> str:
    """Format a number: drop trailing .0 for integers."""
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return str(v)


def _yaml_scalar(v) -> str:
    """Format a scalar for inline YAML. Quote strings that need it."""
    if isinstance(v, str):
        # Quote if contains special chars or looks like a number
        if any(c in v for c in ":{}[],&*?|>!%@`'\"#\n") or v != v.strip():
            return f'"{v}"'
        return v
    return str(v)
