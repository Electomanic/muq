"""Resolver — expand arrangement into flat resolved IR with absolute ticks."""

from __future__ import annotations

import math
import warnings

from muq.gm import (
    ARTICULATIONS,
    DURATION_TOKENS,
    gm_instrument_lookup,
    beats_per_bar,
    parse_time_signature,
    pitch_to_midi,
    resolve_drum_name,
    resolve_pan,
)
from muq.ir import (
    ResolvedAftertouch,
    ResolvedCC,
    ResolvedNote,
    ResolvedPitchBend,
    ResolvedSong,
    ResolvedTempo,
    ResolvedText,
    ResolvedTimeSig,
    ResolvedTrack,
)
from muq.model import (
    AftertouchEvent,
    CCEvent,
    MuqDocument,
    NoteEvent,
    PitchBendEvent,
    RestEvent,
    TextEvent,
)


def resolve(doc: MuqDocument, ppq: int = 480) -> ResolvedSong:
    """Expand arrangement into a ResolvedSong with absolute tick times."""
    tempos: list[ResolvedTempo] = []
    time_sigs: list[ResolvedTimeSig] = []
    resolved_tracks: dict[str, _TrackAccum] = {}

    # Initialize accumulators per track
    for tname, track in doc.tracks.items():
        program = None
        if not track.is_percussion:
            program = gm_instrument_lookup(track.instrument)
        resolved_tracks[tname] = _TrackAccum(
            name=tname,
            channel=track.channel - 1,  # 0-indexed
            program=program,
            volume=track.volume,
            pan=resolve_pan(track.pan),
        )

    # Walk arrangement
    song_beat_cursor = 0.0  # absolute beat position in song
    current_time = doc.song.time
    current_tempo = doc.song.tempo

    # Initial tempo and time sig
    num, denom = parse_time_signature(current_time)
    tempos.append(ResolvedTempo(tick=0, tempo_bpm=current_tempo))
    time_sigs.append(ResolvedTimeSig(tick=0, numerator=num, denominator=denom))

    prev_tie_across = False
    for section in doc.arrangement:
        # Clear pending ties at section boundaries unless previous section
        # had tie_across: true (§13.1)
        if not prev_tie_across:
            for accum in resolved_tracks.values():
                if accum.pending_ties:
                    for (midi_note, voice), rn in accum.pending_ties.items():
                        warnings.warn(
                            f"TIE_ACROSS_NO_MATCH: dangling tie on track '{accum.name}' "
                            f"note {midi_note} dropped at section boundary",
                            stacklevel=2,
                        )
                    accum.pending_ties.clear()

        section_tempo = section.tempo if section.tempo is not None else current_tempo
        section_time = section.time if section.time is not None else current_time

        if section_tempo != current_tempo:
            current_tempo = section_tempo
            tempos.append(ResolvedTempo(
                tick=round(song_beat_cursor * ppq),
                tempo_bpm=current_tempo,
            ))

        if section_time != current_time:
            current_time = section_time
            n, d = parse_time_signature(current_time)
            time_sigs.append(ResolvedTimeSig(
                tick=round(song_beat_cursor * ppq),
                numerator=n, denominator=d,
            ))

        for rep in range(section.repeat):
            rep_beat_cursor = song_beat_cursor
            active_time = current_time

            # Meter events (sorted by bar)
            meter_map: dict[int, str] = {}
            for me in section.meter_events:
                meter_map[me.bar] = me.time

            # Tempo events (sorted by bar+beat)
            for te in section.tempo_events:
                bar_beats_before = _beats_before_bar(
                    te.bar, active_time, meter_map, section, doc)
                te_beat = rep_beat_cursor + bar_beats_before + (te.beat - 1)
                tempos.append(ResolvedTempo(
                    tick=round(te_beat * ppq),
                    tempo_bpm=te.tempo,
                ))

            # Determine bar count from longest pattern in section
            max_bars = 0
            for tname, pname in section.patterns.items():
                if pname in doc.patterns:
                    max_bars = max(max_bars, len(doc.patterns[pname].bars))

            # Process each track's pattern
            for tname, pname in section.patterns.items():
                if tname not in doc.tracks or pname not in doc.patterns:
                    continue
                track = doc.tracks[tname]
                pattern = doc.patterns[pname]
                accum = resolved_tracks[tname]

                bar_beat_pos = rep_beat_cursor
                effective_time = active_time
                pat_bars = pattern.bars
                pat_len = len(pat_bars)

                for bi in range(max_bars):
                    bar = pat_bars[bi % pat_len]
                    bar_num = bi + 1
                    if bar_num in meter_map:
                        effective_time = meter_map[bar_num]
                        n, d = parse_time_signature(effective_time)
                        time_sigs.append(ResolvedTimeSig(
                            tick=round(bar_beat_pos * ppq),
                            numerator=n, denominator=d,
                        ))

                    # First bar shortened for pickup (anacrusis)
                    if bi == 0 and section.pickup_beats is not None:
                        bpb = section.pickup_beats
                    else:
                        bpb = beats_per_bar(effective_time)
                    _resolve_bar(
                        bar, bar_beat_pos, bpb, pattern.swing,
                        track, doc, ppq, accum,
                    )
                    bar_beat_pos += bpb

            # Advance song cursor by total beats in this repetition
            total_beats = _section_total_beats(active_time, meter_map, max_bars, section, doc)
            song_beat_cursor = rep_beat_cursor + total_beats

        # Update current tempo/time for next section
        if section.tempo is not None:
            current_tempo = section.tempo
        if section.time is not None:
            current_time = section.time
        prev_tie_across = section.tie_across

    # Build final resolved tracks
    tracks_out = []
    for tname, accum in resolved_tracks.items():
        _clamp_same_pitch_overlaps(accum.notes)
        tracks_out.append(ResolvedTrack(
            name=accum.name,
            channel=accum.channel,
            program=accum.program,
            volume=accum.volume,
            pan=accum.pan,
            notes=accum.notes,
            ccs=accum.ccs,
            pitch_bends=accum.pitch_bends,
            aftertouches=accum.aftertouches,
            texts=accum.texts,
        ))

    return ResolvedSong(
        ppq=ppq,
        tempos=tempos,
        time_signatures=time_sigs,
        tracks=tracks_out,
    )


def resolve_pattern(
    doc: MuqDocument,
    pattern_name: str,
    ppq: int = 480,
) -> ResolvedSong:
    """Resolve a single pattern in isolation for clip export.

    Uses the song's base tempo and time signature. Reads the pattern's
    `notation` field to determine pitched vs percussion resolution.
    """
    pattern = doc.patterns[pattern_name]
    is_perc = pattern.notation == "percussion"

    # Build a minimal track-like context for _resolve_bar
    from muq.model import Track
    if is_perc:
        dummy_track = Track(instrument="standard", channel=10, percussion=True)
    else:
        dummy_track = Track(instrument="acoustic_grand_piano", channel=1)

    accum = _TrackAccum(
        name=pattern_name,
        channel=dummy_track.channel - 1,
        program=None if is_perc else 0,
    )

    # Tempo and time sig from song
    tempo = doc.song.tempo
    time = doc.song.time
    num, denom = parse_time_signature(time)

    tempos = [ResolvedTempo(tick=0, tempo_bpm=tempo)]
    time_sigs = [ResolvedTimeSig(tick=0, numerator=num, denominator=denom)]

    # Walk bars
    bar_beat_pos = 0.0
    bpb = beats_per_bar(time)
    for bar in pattern.bars:
        _resolve_bar(
            bar, bar_beat_pos, bpb, pattern.swing,
            dummy_track, doc, ppq, accum,
        )
        bar_beat_pos += bpb

    _clamp_same_pitch_overlaps(accum.notes)

    track_out = ResolvedTrack(
        name=accum.name,
        channel=accum.channel,
        program=accum.program,
        volume=accum.volume,
        pan=accum.pan,
        notes=accum.notes,
        ccs=accum.ccs,
        pitch_bends=accum.pitch_bends,
        aftertouches=accum.aftertouches,
        texts=accum.texts,
    )

    return ResolvedSong(
        ppq=ppq,
        tempos=tempos,
        time_signatures=time_sigs,
        tracks=[track_out],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _TrackAccum:
    """Accumulates resolved events for a single track."""

    def __init__(self, name: str, channel: int, program: int | None,
                 volume: int = 100, pan: int = 64):
        self.name = name
        self.channel = channel
        self.program = program
        self.volume = volume
        self.pan = pan
        self.notes: list[ResolvedNote] = []
        self.ccs: list[ResolvedCC] = []
        self.pitch_bends: list[ResolvedPitchBend] = []
        self.aftertouches: list[ResolvedAftertouch] = []
        self.texts: list[ResolvedText] = []
        # Pending ties: (midi_note, voice) → ResolvedNote being extended
        self.pending_ties: dict[tuple[int, int | None], ResolvedNote] = {}


def _clamp_same_pitch_overlaps(notes: list[ResolvedNote]) -> None:
    """Shorten notes that overlap the next note_on of the same pitch.

    For each pitch, if note B starts before note A ends, A's duration
    is truncated to end 1 tick before B starts. This prevents same-pitch
    overlap in MIDI output, matching standard DAW retrigger behavior.
    """
    if not notes:
        return

    # Group by (channel, midi_note)
    from collections import defaultdict
    by_pitch: dict[tuple[int, int], list[ResolvedNote]] = defaultdict(list)
    for n in notes:
        by_pitch[(n.channel, n.midi_note)].append(n)

    for group in by_pitch.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda n: n.tick)
        for i in range(len(group) - 1):
            a = group[i]
            b = group[i + 1]
            a_end = a.tick + a.duration_ticks
            if a_end > b.tick:
                a.duration_ticks = max(1, b.tick - a.tick - 1)


def _event_dur_beats(event: NoteEvent | RestEvent) -> float:
    """Get the duration in beats from a note or rest event."""
    if isinstance(event, NoteEvent):
        if event.dur:
            return DURATION_TOKENS[event.dur]
        if event.dur_beats is not None:
            return event.dur_beats
        return 0.0  # tie continuation without explicit dur
    # RestEvent
    if event.rest:
        return DURATION_TOKENS[event.rest]
    if event.rest_beats is not None:
        return event.rest_beats
    return 0.0


def _apply_swing(base_beat: float, swing: int) -> float:
    """Apply swing to a beat position within a bar (1-indexed).

    Swing affects off-beat eighth notes (positions at 0.5 mod 1.0).
    Formula from §6.3: swung_position = floor(b) + swing/100
    """
    if swing == 50:
        return base_beat
    # Check if this beat is on an off-beat eighth (fractional part == 0.5)
    frac = base_beat - math.floor(base_beat)
    if abs(frac - 0.5) < 1e-9:
        return math.floor(base_beat) + swing / 100.0
    return base_beat


def _resolve_bar(
    bar: list,
    bar_start_beats: float,
    bpb: float,
    swing: int,
    track,
    doc: MuqDocument,
    ppq: int,
    accum: _TrackAccum,
) -> None:
    """Resolve all events in a single bar to absolute ticks."""
    cursor = 1.0  # sequential cursor, 1-indexed
    last_beat_addr_end: float | None = None

    for event in bar:
        if isinstance(event, NoteEvent):
            dur_beats = _event_dur_beats(event)

            # Determine base position
            if event.beat is not None:
                base_pos = event.beat
                last_beat_addr_end = base_pos + dur_beats
            else:
                # Sequential: cursor picks up after last beat-addressed event
                if last_beat_addr_end is not None:
                    cursor = last_beat_addr_end
                    last_beat_addr_end = None
                base_pos = cursor
                cursor += dur_beats

            # Timing layers: base → swing → offset → tick
            swung = _apply_swing(base_pos, swing)
            final_pos = swung + event.offset_beats
            abs_beats = bar_start_beats + (final_pos - 1)
            tick = round(abs_beats * ppq)
            tick = max(0, tick)

            # Articulation gate & velocity modifiers
            gate = 1.0
            vel_add = 0
            if event.articulation and event.articulation in ARTICULATIONS:
                g, v = ARTICULATIONS[event.articulation]
                if g is not None:
                    gate = g
                if v is not None:
                    vel_add = v

            velocity = max(1, min(127, event.vel + vel_add))
            dur_ticks = round(dur_beats * gate * ppq)

            # Resolve pitches
            notes_list = event.note if isinstance(event.note, list) else [event.note]
            for pitch_str in notes_list:
                if track.is_percussion:
                    midi_note = resolve_drum_name(
                        pitch_str, track.drum_map, doc.drum_map)
                    if midi_note is None:
                        continue  # unknown drum, skip
                else:
                    midi_note = pitch_to_midi(pitch_str)

                tie_key = (midi_note, event.voice)
                pending = accum.pending_ties.get(tie_key)
                if pending is not None:
                    # Extend the tied note to cover this continuation
                    pending.duration_ticks = (tick + dur_ticks) - pending.tick
                    if event.tie:
                        # Chain continues — keep the pending tie
                        pass
                    else:
                        del accum.pending_ties[tie_key]
                else:
                    note = ResolvedNote(
                        tick=tick,
                        channel=accum.channel,
                        midi_note=midi_note,
                        velocity=velocity,
                        duration_ticks=dur_ticks,
                        voice=event.voice,
                    )
                    accum.notes.append(note)
                    if event.tie:
                        accum.pending_ties[tie_key] = note

        elif isinstance(event, RestEvent):
            dur_beats = _event_dur_beats(event)
            if event.beat is not None:
                last_beat_addr_end = event.beat + dur_beats
            else:
                if last_beat_addr_end is not None:
                    cursor = last_beat_addr_end
                    last_beat_addr_end = None
                cursor += dur_beats

        elif isinstance(event, CCEvent):
            base_pos = event.beat if event.beat is not None else 1.0
            swung = _apply_swing(base_pos, swing)
            final_pos = swung + event.offset_beats
            abs_beats = bar_start_beats + (final_pos - 1)
            tick = max(0, round(abs_beats * ppq))
            accum.ccs.append(ResolvedCC(
                tick=tick, channel=accum.channel,
                cc=event.cc, value=event.value,
                interp=event.interp,
            ))

        elif isinstance(event, PitchBendEvent):
            base_pos = event.beat if event.beat is not None else 1.0
            swung = _apply_swing(base_pos, swing)
            final_pos = swung + event.offset_beats
            abs_beats = bar_start_beats + (final_pos - 1)
            tick = max(0, round(abs_beats * ppq))
            accum.pitch_bends.append(ResolvedPitchBend(
                tick=tick, channel=accum.channel,
                value=event.pitch_bend,
                interp=event.interp,
            ))

        elif isinstance(event, AftertouchEvent):
            base_pos = event.beat if event.beat is not None else 1.0
            swung = _apply_swing(base_pos, swing)
            final_pos = swung + event.offset_beats
            abs_beats = bar_start_beats + (final_pos - 1)
            tick = max(0, round(abs_beats * ppq))
            accum.aftertouches.append(ResolvedAftertouch(
                tick=tick, channel=accum.channel,
                value=event.aftertouch,
                interp=event.interp,
            ))

        elif isinstance(event, TextEvent):
            base_pos = event.beat if event.beat is not None else 1.0
            swung = _apply_swing(base_pos, swing)
            final_pos = swung + event.offset_beats
            abs_beats = bar_start_beats + (final_pos - 1)
            tick = max(0, round(abs_beats * ppq))
            accum.texts.append(ResolvedText(
                tick=tick, text=event.text, type=event.type,
            ))


def _beats_before_bar(
    bar_num: int,
    base_time: str,
    meter_map: dict[int, str],
    section,
    doc: MuqDocument,
) -> float:
    """Compute the cumulative beats before a given bar number in a section."""
    total = 0.0
    effective_time = base_time
    for b in range(1, bar_num):
        if b in meter_map:
            effective_time = meter_map[b]
        if b == 1 and section.pickup_beats is not None:
            total += section.pickup_beats
        else:
            total += beats_per_bar(effective_time)
    return total


def _section_total_beats(
    base_time: str,
    meter_map: dict[int, str],
    max_bars: int,
    section,
    doc: MuqDocument,
) -> float:
    """Compute total beats across all bars in one repetition of a section."""
    total = 0.0
    effective_time = base_time
    for b in range(1, max_bars + 1):
        if b in meter_map:
            effective_time = meter_map[b]
        if b == 1 and section.pickup_beats is not None:
            total += section.pickup_beats
        else:
            total += beats_per_bar(effective_time)
    return total
