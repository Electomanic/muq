#!/usr/bin/env python3
"""Dump a MIDI file as human-readable text for development inspection.

Usage:
    uv run python scripts/dump_midi.py file.mid
    uv run python scripts/dump_midi.py file.mid --json
    uv run python scripts/dump_midi.py file.mid --no-reverse  # raw numbers only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mido

# ---------------------------------------------------------------------------
# Reverse lookup tables (GM)
# ---------------------------------------------------------------------------

# Canonical GM program → name (import from muq.gm)
from muq.gm import GM_INSTRUMENTS, GM_DRUM_MAP, DURATION_TOKENS

GM_PROGRAM_TO_NAME: dict[int, str] = {v: k for k, v in GM_INSTRUMENTS.items()}

# Build reverse drum map: MIDI note → preferred short name
# Pick the shortest alias for each note number
_DRUM_NOTE_NAMES: dict[int, list[str]] = {}
for name, note in GM_DRUM_MAP.items():
    _DRUM_NOTE_NAMES.setdefault(note, []).append(name)

GM_DRUM_NOTE_TO_NAME: dict[int, str] = {
    note: min(names, key=len) for note, names in _DRUM_NOTE_NAMES.items()
}

# Reverse duration: beats → token (prefer shortest token name)
_BEATS_TO_TOKEN: dict[float, str] = {}
for tok, beats in sorted(DURATION_TOKENS.items(), key=lambda t: len(t[0])):
    if beats not in _BEATS_TO_TOKEN:
        _BEATS_TO_TOKEN[beats] = tok

# Note number → pitch name
_SEMITONE_TO_NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_pitch(note: int) -> str:
    octave = (note // 12) - 1
    return f"{_SEMITONE_TO_NOTE[note % 12]}{octave}"


def ticks_to_dur_str(ticks: int, ppq: int) -> str:
    """Convert tick duration to a readable string like '1.0 beats (q)'."""
    beats = ticks / ppq
    token = _BEATS_TO_TOKEN.get(beats)
    if token:
        return f"{beats:g} beats ({token})"
    return f"{beats:.4g} beats"


def ticks_to_beat_pos(tick: int, ppq: int) -> str:
    """Convert absolute tick to 'bar.beat' position given PPQ (assumes 4/4 for display)."""
    beat = tick / ppq
    return f"{beat:.2f}"


# ---------------------------------------------------------------------------
# MIDI parsing
# ---------------------------------------------------------------------------

def parse_midi(path: Path, reverse: bool = True) -> dict:
    """Parse a MIDI file into a structured dict."""
    mid = mido.MidiFile(str(path))
    ppq = mid.ticks_per_beat
    result: dict = {
        "file": str(path),
        "type": mid.type,
        "ppq": ppq,
        "tracks": [],
    }

    for ti, track in enumerate(mid.tracks):
        track_info = _parse_track(ti, track, ppq, reverse)
        result["tracks"].append(track_info)

    return result


def _parse_track(ti: int, track: mido.MidiTrack, ppq: int, reverse: bool) -> dict:
    """Parse a single MIDI track into a structured dict with paired note events."""
    info: dict = {"index": ti, "name": None, "channel": None, "program": None, "events": []}

    # First pass: collect raw events with absolute ticks, find metadata
    abs_tick = 0
    raw_events: list[dict] = []
    # Track pending note-ons: (channel, note) → (tick, velocity)
    pending_notes: dict[tuple[int, int], tuple[int, int]] = {}

    for msg in track:
        abs_tick += msg.time

        if msg.is_meta:
            if msg.type == "track_name":
                info["name"] = msg.name
            elif msg.type == "set_tempo":
                bpm = round(mido.tempo2bpm(msg.tempo), 2)
                raw_events.append({
                    "tick": abs_tick, "type": "tempo",
                    "bpm": bpm,
                })
            elif msg.type == "time_signature":
                raw_events.append({
                    "tick": abs_tick, "type": "time_sig",
                    "num": msg.numerator, "den": msg.denominator,
                })
            elif msg.type == "key_signature":
                raw_events.append({
                    "tick": abs_tick, "type": "key_sig",
                    "key": msg.key,
                })
            elif msg.type in ("text", "lyrics", "marker", "cue_marker"):
                raw_events.append({
                    "tick": abs_tick, "type": msg.type,
                    "text": msg.text,
                })
            elif msg.type == "end_of_track":
                info["length_ticks"] = abs_tick
            continue

        if msg.type == "program_change":
            info["channel"] = msg.channel + 1
            info["program"] = msg.program
            if reverse:
                info["instrument"] = GM_PROGRAM_TO_NAME.get(msg.program, f"program_{msg.program}")
            continue

        if msg.type == "note_on" and msg.velocity > 0:
            key = (msg.channel, msg.note)
            if info["channel"] is None:
                info["channel"] = msg.channel + 1
            pending_notes[key] = (abs_tick, msg.velocity)
            continue

        if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if key in pending_notes:
                on_tick, vel = pending_notes.pop(key)
                dur_ticks = abs_tick - on_tick
                is_drum = (msg.channel == 9)  # 0-indexed ch 10

                if reverse:
                    if is_drum:
                        pitch_str = GM_DRUM_NOTE_TO_NAME.get(msg.note, f"note_{msg.note}")
                    else:
                        pitch_str = midi_to_pitch(msg.note)
                    dur_str = ticks_to_dur_str(dur_ticks, ppq)
                else:
                    pitch_str = str(msg.note)
                    dur_str = f"{dur_ticks}t"

                raw_events.append({
                    "tick": on_tick, "type": "note",
                    "pitch": pitch_str, "midi_note": msg.note,
                    "vel": vel, "dur_ticks": dur_ticks, "dur": dur_str,
                    "channel": msg.channel + 1,
                })
            continue

        if msg.type == "control_change":
            raw_events.append({
                "tick": abs_tick, "type": "cc",
                "cc": msg.control, "value": msg.value,
                "channel": msg.channel + 1,
            })
            continue

        if msg.type == "pitchwheel":
            raw_events.append({
                "tick": abs_tick, "type": "pitch_bend",
                "value": msg.pitch,
                "channel": msg.channel + 1,
            })
            continue

        if msg.type == "aftertouch":
            raw_events.append({
                "tick": abs_tick, "type": "aftertouch",
                "value": msg.value,
                "channel": msg.channel + 1,
            })
            continue

    # Sort events by tick, then type priority (tempo/time_sig first, then notes)
    type_order = {"tempo": 0, "time_sig": 1, "key_sig": 2, "text": 3,
                  "lyrics": 3, "marker": 3, "note": 5, "cc": 4,
                  "pitch_bend": 4, "aftertouch": 4}
    raw_events.sort(key=lambda e: (e["tick"], type_order.get(e["type"], 9)))
    info["events"] = raw_events
    info["event_count"] = len(raw_events)

    return info


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def format_text(data: dict) -> str:
    lines: list[str] = []
    lines.append(f"File: {data['file']}")
    lines.append(f"Type: SMF {data['type']}")
    lines.append(f"PPQ:  {data['ppq']}")
    lines.append("")

    ppq = data["ppq"]

    for track in data["tracks"]:
        # Track header
        ti = track["index"]
        name = track["name"] or "(unnamed)"
        ch = track.get("channel")
        prog = track.get("program")
        inst = track.get("instrument")
        length = track.get("length_ticks")

        header_parts = [f"Track {ti} \"{name}\""]
        if ch is not None:
            header_parts.append(f"ch={ch}")
        if inst:
            header_parts.append(f"inst={inst}")
        elif prog is not None:
            header_parts.append(f"program={prog}")
        if length is not None:
            beats = length / ppq
            header_parts.append(f"len={length}t ({beats:g} beats)")

        lines.append("=== " + "  ".join(header_parts) + " ===")

        if not track["events"]:
            lines.append("  (no events)")
        else:
            for ev in track["events"]:
                tick = ev["tick"]
                beat_pos = ticks_to_beat_pos(tick, ppq)

                if ev["type"] == "tempo":
                    lines.append(f"  {tick:>7d} ({beat_pos:>8s}b): tempo {ev['bpm']} bpm")
                elif ev["type"] == "time_sig":
                    lines.append(f"  {tick:>7d} ({beat_pos:>8s}b): time_sig {ev['num']}/{ev['den']}")
                elif ev["type"] == "key_sig":
                    lines.append(f"  {tick:>7d} ({beat_pos:>8s}b): key_sig {ev['key']}")
                elif ev["type"] in ("text", "lyrics", "marker", "cue_marker"):
                    lines.append(f"  {tick:>7d} ({beat_pos:>8s}b): {ev['type']} \"{ev['text']}\"")
                elif ev["type"] == "note":
                    lines.append(
                        f"  {tick:>7d} ({beat_pos:>8s}b): note  "
                        f"{ev['pitch']:>12s}  vel={ev['vel']:<3d}  "
                        f"dur={ev['dur']}"
                    )
                elif ev["type"] == "cc":
                    lines.append(
                        f"  {tick:>7d} ({beat_pos:>8s}b): cc    "
                        f"#{ev['cc']:<3d}  value={ev['value']}"
                    )
                elif ev["type"] == "pitch_bend":
                    lines.append(
                        f"  {tick:>7d} ({beat_pos:>8s}b): bend  "
                        f"value={ev['value']}"
                    )
                elif ev["type"] == "aftertouch":
                    lines.append(
                        f"  {tick:>7d} ({beat_pos:>8s}b): atouch "
                        f"value={ev['value']}"
                    )

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump a MIDI file as human-readable text (dev tool)")
    parser.add_argument("file", type=Path, help="Path to .mid file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-reverse", action="store_true",
                        help="Show raw MIDI numbers instead of GM names")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"error: {args.file} not found", file=sys.stderr)
        return 1

    data = parse_midi(args.file, reverse=not args.no_reverse)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_text(data))

    return 0


if __name__ == "__main__":
    sys.exit(main())
