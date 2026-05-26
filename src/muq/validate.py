"""Semantic validator — checks beyond JSON Schema (§18 error classes)."""

from __future__ import annotations

from dataclasses import dataclass, field

from muq.gm import (
    GM_DRUM_MAP,
    GM_INSTRUMENTS,
    DURATION_TOKENS,
    ARTICULATIONS,
    beats_per_bar,
    is_pitched_notation,
    parse_time_signature,
    pitch_to_midi,
    resolve_drum_name,
)
from muq.model import (
    MuqDocument,
    NoteEvent,
    RestEvent,
    CCEvent,
    PitchBendEvent,
    AftertouchEvent,
    TextEvent,
    Pattern,
    Section,
)


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str = "error"  # "error" or "warning"
    path: str = ""  # e.g. "tracks.drums", "patterns.verse.bars[0][1]"


def validate(doc: MuqDocument) -> list[Diagnostic]:
    """Run semantic validation on a parsed MuqDocument. Returns a list of diagnostics."""
    diags: list[Diagnostic] = []

    _validate_song(doc, diags)
    _validate_tracks(doc, diags)
    _validate_patterns(doc, diags)
    _validate_arrangement(doc, diags)

    return diags


# ---------------------------------------------------------------------------
# Song
# ---------------------------------------------------------------------------

def _validate_song(doc: MuqDocument, diags: list[Diagnostic]) -> None:
    s = doc.song
    if not (1 <= s.tempo <= 999):
        diags.append(Diagnostic("INVALID_TEMPO", f"Tempo {s.tempo} out of range 1-999", path="song.tempo"))
    _check_time_sig(s.time, "song.time", diags)

    if s.scale_mode and s.scale_mode not in ("warn", "strict"):
        diags.append(Diagnostic("INVALID_SCALE_MODE", f"Unknown scale_mode: {s.scale_mode}", path="song.scale_mode"))


def _check_time_sig(time_str: str, path: str, diags: list[Diagnostic]) -> bool:
    parts = time_str.split("/")
    if len(parts) != 2:
        diags.append(Diagnostic("INVALID_TIME_SIGNATURE", f"Bad time signature: {time_str}", path=path))
        return False
    try:
        num, denom = int(parts[0]), int(parts[1])
    except ValueError:
        diags.append(Diagnostic("INVALID_TIME_SIGNATURE", f"Non-integer time signature: {time_str}", path=path))
        return False
    if num < 1 or denom < 1 or (denom & (denom - 1)) != 0:
        diags.append(Diagnostic("INVALID_TIME_SIGNATURE",
                                f"Denominator must be a power of 2: {time_str}", path=path))
        return False
    return True


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

def _validate_tracks(doc: MuqDocument, diags: list[Diagnostic]) -> None:
    for name, track in doc.tracks.items():
        path = f"tracks.{name}"
        if not (1 <= track.channel <= 16):
            diags.append(Diagnostic("INVALID_CHANNEL", f"Channel {track.channel} out of range 1-16", path=path))

        is_perc = track.is_percussion
        if not is_perc and track.instrument not in GM_INSTRUMENTS:
            diags.append(Diagnostic("UNKNOWN_INSTRUMENT",
                                    f"Unknown instrument: {track.instrument}", path=path))

        if track.drum_map and not is_perc:
            diags.append(Diagnostic("DRUM_MAP_NON_PERCUSSION",
                                    "drum_map set on non-percussion track",
                                    severity="warning", path=path))


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def _check_pitch_notation_consistency(
    pattern, path: str, diags: list[Diagnostic]
) -> None:
    """Check that all note events in a pattern use the same notation style."""
    has_pitched = False
    has_drum = False
    for bar in pattern.bars:
        for event in bar:
            if not isinstance(event, NoteEvent):
                continue
            notes = event.note if isinstance(event.note, list) else [event.note]
            for n in notes:
                if is_pitched_notation(n):
                    has_pitched = True
                else:
                    has_drum = True
                if has_pitched and has_drum:
                    diags.append(Diagnostic(
                        "MIXED_PITCH_NOTATION",
                        "Pattern mixes pitched notation (e.g. C4) and drum notation (e.g. kick)",
                        path=path,
                    ))
                    return

def _validate_patterns(doc: MuqDocument, diags: list[Diagnostic]) -> None:
    # Determine which patterns are used by which tracks
    pattern_to_tracks: dict[str, set[str]] = {}
    for section in doc.arrangement:
        for track_name, pat_name in section.patterns.items():
            pattern_to_tracks.setdefault(pat_name, set()).add(track_name)

    for name, pattern in doc.patterns.items():
        path = f"patterns.{name}"
        if not pattern.bars:
            diags.append(Diagnostic("EMPTY_PATTERN", "Pattern has zero bars", path=path))
            continue

        # Check pitch notation consistency (§6.2)
        _check_pitch_notation_consistency(pattern, path, diags)

        track_names = pattern_to_tracks.get(name, set())
        tracks = [doc.tracks[tn] for tn in track_names if tn in doc.tracks]
        is_perc = any(t.is_percussion for t in tracks)
        per_track_map = None
        for t in tracks:
            if t.drum_map:
                per_track_map = t.drum_map
                break

        for bi, bar in enumerate(pattern.bars):
            bar_path = f"{path}.bars[{bi}]"
            for ei, event in enumerate(bar):
                ev_path = f"{bar_path}[{ei}]"
                _validate_event(event, ev_path, is_perc, per_track_map,
                                doc.drum_map, doc.song, diags)


def _validate_event(
    event: NoteEvent | RestEvent | CCEvent | PitchBendEvent | AftertouchEvent | TextEvent,
    path: str,
    is_percussion: bool,
    per_track_map: dict[str, int] | None,
    global_map: dict[str, int] | None,
    song,
    diags: list[Diagnostic],
) -> None:
    if isinstance(event, NoteEvent):
        _validate_note_event(event, path, is_percussion, per_track_map, global_map, song, diags)
    elif isinstance(event, RestEvent):
        pass  # Schema handles most rest validation
    elif isinstance(event, CCEvent):
        if not (0 <= event.cc <= 127):
            diags.append(Diagnostic("INVALID_CC_NUMBER", f"CC {event.cc} out of range", path=path))
        if not (0 <= event.value <= 127):
            diags.append(Diagnostic("INVALID_CC_VALUE", f"CC value {event.value} out of range", path=path))
    elif isinstance(event, PitchBendEvent):
        if not (-8192 <= event.pitch_bend <= 8191):
            diags.append(Diagnostic("INVALID_PITCH_BEND",
                                    f"Pitch bend {event.pitch_bend} out of range", path=path))
    elif isinstance(event, AftertouchEvent):
        if not (0 <= event.aftertouch <= 127):
            diags.append(Diagnostic("INVALID_AFTERTOUCH",
                                    f"Aftertouch {event.aftertouch} out of range", path=path))
    elif isinstance(event, TextEvent):
        valid_types = {"lyric", "marker", "rehearsal", "chord", "text"}
        if event.type not in valid_types:
            diags.append(Diagnostic("INVALID_TEXT_TYPE",
                                    f"Unknown text type: {event.type}", path=path))


def _validate_note_event(
    event: NoteEvent,
    path: str,
    is_percussion: bool,
    per_track_map: dict[str, int] | None,
    global_map: dict[str, int] | None,
    song,
    diags: list[Diagnostic],
) -> None:
    # Duration
    if event.dur is None and event.dur_beats is None and not event.tie:
        diags.append(Diagnostic("MISSING_DURATION", "Note has no dur or dur_beats", path=path))
    if event.dur and event.dur not in DURATION_TOKENS:
        diags.append(Diagnostic("INVALID_DURATION", f"Unknown duration token: {event.dur}", path=path))
    if event.dur_beats is not None and event.dur_beats <= 0:
        diags.append(Diagnostic("INVALID_DURATION_BEATS", f"dur_beats must be positive", path=path))

    # Velocity
    if not (1 <= event.vel <= 127):
        diags.append(Diagnostic("INVALID_VELOCITY", f"Velocity {event.vel} out of range 1-127", path=path))

    # Articulation
    if event.articulation and event.articulation not in ARTICULATIONS:
        diags.append(Diagnostic("INVALID_ARTICULATION",
                                f"Unknown articulation: {event.articulation}", path=path))

    # Pitch(es)
    notes = event.note if isinstance(event.note, list) else [event.note]
    for pitch_str in notes:
        if is_percussion:
            midi = resolve_drum_name(pitch_str, per_track_map, global_map)
            if midi is None:
                diags.append(Diagnostic("UNKNOWN_DRUM_NAME",
                                        f"Unknown drum name: {pitch_str}", path=path))
        else:
            try:
                pitch_to_midi(pitch_str)
            except ValueError as e:
                diags.append(Diagnostic("INVALID_PITCH", str(e), path=path))


# ---------------------------------------------------------------------------
# Arrangement
# ---------------------------------------------------------------------------

def _validate_arrangement(doc: MuqDocument, diags: list[Diagnostic]) -> None:
    for si, section in enumerate(doc.arrangement):
        path = f"arrangement[{si}]"
        if section.repeat is not None and section.repeat < 1:
            diags.append(Diagnostic("INVALID_REPEAT", f"Repeat must be >= 1", path=path))

        if section.tempo is not None and not (1 <= section.tempo <= 999):
            diags.append(Diagnostic("INVALID_SECTION_TEMPO",
                                    f"Section tempo {section.tempo} out of range", path=path))

        if section.time is not None:
            _check_time_sig(section.time, f"{path}.time", diags)

        for track_name, pat_name in section.patterns.items():
            if track_name not in doc.tracks:
                diags.append(Diagnostic("UNKNOWN_TRACK_IN_SECTION",
                                        f"Unknown track: {track_name}", path=f"{path}.patterns"))
            if pat_name not in doc.patterns:
                diags.append(Diagnostic("UNKNOWN_PATTERN",
                                        f"Unknown pattern: {pat_name}", path=f"{path}.patterns"))

        # Determine bar count from the longest pattern in the section
        max_bars = 0
        for track_name, pat_name in section.patterns.items():
            if pat_name in doc.patterns:
                max_bars = max(max_bars, len(doc.patterns[pat_name].bars))

        for te in section.tempo_events:
            if te.bar > max_bars:
                diags.append(Diagnostic("TEMPO_EVENT_OUT_OF_RANGE",
                                        f"Tempo event bar {te.bar} exceeds section ({max_bars} bars)",
                                        path=f"{path}.tempo_events"))
            if not (1 <= te.tempo <= 999):
                diags.append(Diagnostic("INVALID_TEMPO_EVENT",
                                        f"Tempo event has invalid BPM: {te.tempo}",
                                        path=f"{path}.tempo_events"))

        for me in section.meter_events:
            if me.bar > max_bars:
                diags.append(Diagnostic("METER_EVENT_OUT_OF_RANGE",
                                        f"Meter event bar {me.bar} exceeds section ({max_bars} bars)",
                                        path=f"{path}.meter_events"))
            _check_time_sig(me.time, f"{path}.meter_events", diags)
