"""Semantic validator — checks beyond JSON Schema (§18 error classes)."""

from __future__ import annotations

from dataclasses import dataclass, field

from muq.gm import (
    GM_DRUM_MAP,
    DURATION_TOKENS,
    ARTICULATIONS,
    beats_per_bar,
    gm_instrument_lookup,
    is_pitched_notation,
    parse_time_signature,
    pitch_to_midi,
    resolve_drum_name,
    scale_pitch_classes,
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


_VALID_TOP_LEVEL_KEYS = {"song", "tracks", "patterns", "arrangement", "drum_map"}


def validate(doc: MuqDocument, *, raw: dict | None = None) -> list[Diagnostic]:
    """Run semantic validation on a parsed MuqDocument. Returns a list of diagnostics.

    If *raw* is provided (the original parsed dict), also checks for
    unknown top-level keys (§3.1).
    """
    diags: list[Diagnostic] = []

    if raw is not None:
        for key in raw:
            if key not in _VALID_TOP_LEVEL_KEYS:
                diags.append(Diagnostic("UNKNOWN_TOP_LEVEL_KEY",
                                        f"Unknown top-level key: {key}", path=key))

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

    if s.scale_mode and s.scale_mode not in ("off", "warn", "strict"):
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
        if not is_perc and gm_instrument_lookup(track.instrument) is None:
            diags.append(Diagnostic("UNKNOWN_INSTRUMENT",
                                    f"Unknown instrument: {track.instrument}", path=path))

        if track.drum_map and not is_perc:
            diags.append(Diagnostic("DRUM_MAP_NON_PERCUSSION",
                                    "drum_map set on non-percussion track",
                                    severity="warning", path=path))

        # §18 DRUM_CHANNEL_MISMATCH — only warn when percussion is auto-detected
        # (track.percussion is None), not when explicitly set to true.
        if is_perc and track.channel != 10 and track.percussion is None:
            diags.append(Diagnostic("DRUM_CHANNEL_MISMATCH",
                                    f"Percussion track on channel {track.channel} (expected 10)",
                                    severity="warning", path=path))
        if not is_perc and track.channel == 10:
            diags.append(Diagnostic("DRUM_CHANNEL_MISMATCH",
                                    "Non-percussion track on channel 10",
                                    severity="warning", path=path))

        # Volume range
        if not (0 <= track.volume <= 127):
            diags.append(Diagnostic("INVALID_VOLUME",
                                    f"Volume {track.volume} out of range 0-127", path=path))


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def _check_pitch_notation_consistency(
    pattern, path: str, diags: list[Diagnostic]
) -> None:
    """Check that all note events match the pattern's declared notation style."""
    if pattern.notation not in ("pitched", "percussion"):
        diags.append(Diagnostic(
            "INVALID_NOTATION",
            f"Unknown notation: {pattern.notation}",
            path=path,
        ))
        return

    expect_pitched = pattern.notation == "pitched"
    for bar in pattern.bars:
        for event in bar:
            if not isinstance(event, NoteEvent):
                continue
            notes = event.note if isinstance(event.note, list) else [event.note]
            for n in notes:
                if is_pitched_notation(n) != expect_pitched:
                    kind = "pitched" if expect_pitched else "percussion"
                    diags.append(Diagnostic(
                        "MIXED_PITCH_NOTATION",
                        f"Note '{n}' does not match pattern notation: {kind}",
                        path=path,
                    ))
                    return

def _event_dur_beats(event) -> float:
    """Resolve an event's duration to beats. Returns 0.0 if unknown."""
    if isinstance(event, NoteEvent):
        if event.dur_beats is not None:
            return event.dur_beats
        if event.dur and event.dur in DURATION_TOKENS:
            return DURATION_TOKENS[event.dur]
    elif isinstance(event, RestEvent):
        if event.rest_beats is not None:
            return event.rest_beats
        if event.rest and event.rest in DURATION_TOKENS:
            return DURATION_TOKENS[event.rest]
    return 0.0


def _validate_patterns(doc: MuqDocument, diags: list[Diagnostic]) -> None:
    # Determine which patterns are used by which tracks
    pattern_to_tracks: dict[str, set[str]] = {}
    for section in doc.arrangement:
        for track_name, pat_name in section.patterns.items():
            pattern_to_tracks.setdefault(pat_name, set()).add(track_name)

    # Build per-bar effective bpb from meter_events across all sections
    # that reference each pattern.  Maps (pattern_name, bar_index) → bpb.
    pattern_bar_bpb: dict[tuple[str, int], float] = {}
    for section in doc.arrangement:
        effective_time = section.time if section.time else doc.song.time
        meter_map: dict[int, str] = {}
        for me in section.meter_events:
            meter_map[me.bar] = me.time
        for _tn, pat_name in section.patterns.items():
            if pat_name not in doc.patterns:
                continue
            cur_time = effective_time
            for bi in range(len(doc.patterns[pat_name].bars)):
                bar_num = bi + 1  # 1-indexed
                if bar_num in meter_map:
                    cur_time = meter_map[bar_num]
                key = (pat_name, bi)
                # Use the smallest bpb seen (most restrictive) if used in
                # multiple sections with different meters.
                bpb_val = beats_per_bar(cur_time)
                if key not in pattern_bar_bpb or bpb_val < pattern_bar_bpb[key]:
                    pattern_bar_bpb[key] = bpb_val

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
            bpb = pattern_bar_bpb.get((name, bi), beats_per_bar(doc.song.time))
            seq_total = 0.0
            for ei, event in enumerate(bar):
                ev_path = f"{bar_path}[{ei}]"
                _validate_event(event, ev_path, is_perc, per_track_map,
                                doc.drum_map, doc.song, diags)
                # §18.6 BEAT_OUT_OF_RANGE
                beat = getattr(event, "beat", None)
                if beat is not None:
                    if beat < 1 or beat > bpb:
                        diags.append(Diagnostic(
                            "BEAT_OUT_OF_RANGE",
                            f"beat {beat} out of range 1..{bpb}",
                            severity="warning", path=ev_path))
                    # §11.4 beat + duration overflow
                    dur = _event_dur_beats(event)
                    if dur > 0 and beat + dur > bpb + 1:
                        diags.append(Diagnostic(
                            "BEAT_OVERFLOW",
                            f"beat {beat} + duration {dur} exceeds bar ({bpb} beats)",
                            severity="warning", path=ev_path))

                # §18.6 SEQUENTIAL_OVERFLOW — accumulate sequential durations
                if beat is None:
                    seq_total += _event_dur_beats(event)

            if seq_total > bpb:
                diags.append(Diagnostic(
                    "SEQUENTIAL_OVERFLOW",
                    f"Sequential events total {seq_total} beats, exceeds bar ({bpb} beats)",
                    severity="warning", path=bar_path))

        # Scale validation (§4.4) — only for pitched patterns
        if (not is_perc
                and pattern.notation == "pitched"
                and doc.song.key
                and doc.song.scale_mode in ("warn", "strict")):
            pcs = scale_pitch_classes(doc.song.key)
            if pcs is not None:
                severity = "error" if doc.song.scale_mode == "strict" else "warning"
                _check_scale(pattern, pcs, severity, path, diags)


def _check_scale(
    pattern: Pattern,
    pitch_classes: frozenset[int],
    severity: str,
    path: str,
    diags: list[Diagnostic],
) -> None:
    """Check pitched notes against the declared scale pitch classes."""
    for bi, bar in enumerate(pattern.bars):
        for ei, event in enumerate(bar):
            if not isinstance(event, NoteEvent):
                continue
            notes = event.note if isinstance(event.note, list) else [event.note]
            for pitch_str in notes:
                if not is_pitched_notation(pitch_str):
                    continue
                try:
                    midi = pitch_to_midi(pitch_str)
                except ValueError:
                    continue
                pc = midi % 12
                if pc not in pitch_classes:
                    diags.append(Diagnostic(
                        "OUT_OF_SCALE",
                        f"Note '{pitch_str}' is outside the declared scale",
                        severity=severity,
                        path=f"{path}.bars[{bi}][{ei}]",
                    ))


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
        # §18.5 NOTE_AND_REST_CONFLICT — also check note + rest/rest_beats coexistence
        # (schema blocks this at parse time, but check for programmatic construction)
        # Voice check
        if event.voice is not None and not isinstance(event.voice, int):
            diags.append(Diagnostic("INVALID_VOICE", f"voice must be an integer", path=path))
        # Offset beats check
        if event.offset_beats != 0 and not isinstance(event.offset_beats, (int, float)):
            diags.append(Diagnostic("INVALID_OFFSET_BEATS", f"offset_beats must be a number", path=path))
    elif isinstance(event, RestEvent):
        if event.rest_beats is not None and event.rest_beats <= 0:
            diags.append(Diagnostic("INVALID_REST_BEATS", "rest_beats must be > 0", path=path))
        # §18.5 REST_CONFLICT
        if event.rest is not None and event.rest_beats is not None:
            diags.append(Diagnostic("REST_CONFLICT",
                                    "Event has both rest and rest_beats", path=path))
        # §10.3 rest token validation
        if event.rest is not None and event.rest not in DURATION_TOKENS:
            diags.append(Diagnostic("INVALID_DURATION",
                                    f"Unknown rest duration token: {event.rest}", path=path))
    elif isinstance(event, CCEvent):
        if not (0 <= event.cc <= 127):
            diags.append(Diagnostic("INVALID_CC_NUMBER", f"CC {event.cc} out of range", path=path))
        if not (0 <= event.value <= 127):
            diags.append(Diagnostic("INVALID_CC_VALUE", f"CC value {event.value} out of range", path=path))
        if event.interp and event.interp not in ("step", "linear"):
            diags.append(Diagnostic("INVALID_INTERP",
                                    f"Unknown interp mode: {event.interp}", path=path))
    elif isinstance(event, PitchBendEvent):
        if not (-8192 <= event.pitch_bend <= 8191):
            diags.append(Diagnostic("INVALID_PITCH_BEND",
                                    f"Pitch bend {event.pitch_bend} out of range", path=path))
        if event.interp and event.interp not in ("step", "linear"):
            diags.append(Diagnostic("INVALID_INTERP",
                                    f"Unknown interp mode: {event.interp}", path=path))
    elif isinstance(event, AftertouchEvent):
        if not (0 <= event.aftertouch <= 127):
            diags.append(Diagnostic("INVALID_AFTERTOUCH",
                                    f"Aftertouch {event.aftertouch} out of range", path=path))
        if event.interp and event.interp not in ("step", "linear"):
            diags.append(Diagnostic("INVALID_INTERP",
                                    f"Unknown interp mode: {event.interp}", path=path))
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
    if event.dur is None and event.dur_beats is None:
        diags.append(Diagnostic("MISSING_DURATION", "Note has no dur or dur_beats", path=path))
    if event.dur is not None and event.dur_beats is not None:
        diags.append(Diagnostic("DURATION_CONFLICT",
                                "Event has both dur and dur_beats", path=path))
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
        if section.repeat is not None and section.repeat > 9999:
            diags.append(Diagnostic("INVALID_REPEAT", f"Repeat must be <= 9999", path=path))

        # Determine effective time signature for this section
        effective_time = section.time if section.time else doc.song.time
        bpb = beats_per_bar(effective_time)

        if section.pickup_beats is not None:
            if section.pickup_beats <= 0:
                diags.append(Diagnostic("INVALID_PICKUP_BEATS",
                                        "pickup_beats must be > 0", path=path))
            elif section.pickup_beats >= bpb:
                diags.append(Diagnostic("INVALID_PICKUP_BEATS",
                                        f"pickup_beats ({section.pickup_beats}) must be < beats_per_bar ({bpb})",
                                        path=path))

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
            # Notation–track cross-check
            if track_name in doc.tracks and pat_name in doc.patterns:
                track = doc.tracks[track_name]
                pattern = doc.patterns[pat_name]
                if pattern.notation == "percussion" and not track.is_percussion:
                    diags.append(Diagnostic(
                        "NOTATION_TRACK_MISMATCH",
                        f"Percussion pattern '{pat_name}' bound to non-percussion track '{track_name}'",
                        severity="warning", path=f"{path}.patterns"))
                elif pattern.notation == "pitched" and track.is_percussion:
                    diags.append(Diagnostic(
                        "NOTATION_TRACK_MISMATCH",
                        f"Pitched pattern '{pat_name}' bound to percussion track '{track_name}'",
                        severity="warning", path=f"{path}.patterns"))

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
