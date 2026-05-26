"""MIDI exporter — convert resolved IR to SMF Type 1 via mido."""

from __future__ import annotations

from pathlib import Path

import mido

from muq.ir import ResolvedSong


def to_midi(song: ResolvedSong) -> mido.MidiFile:
    """Convert a ResolvedSong to a mido MidiFile (Type 1)."""
    mid = mido.MidiFile(type=1, ticks_per_beat=song.ppq)

    # Track 0: tempo + time signature meta-events
    tempo_track = mido.MidiTrack()
    mid.tracks.append(tempo_track)
    _write_meta_track(tempo_track, song)

    # One MIDI track per resolved track
    for rt in song.tracks:
        track = mido.MidiTrack()
        mid.tracks.append(track)

        # Track name
        track.append(mido.MetaMessage("track_name", name=rt.name, time=0))

        # Program change (skip for percussion)
        if rt.program is not None:
            track.append(mido.Message(
                "program_change", channel=rt.channel, program=rt.program, time=0))

        # Volume (CC7) and Pan (CC10) at tick 0
        track.append(mido.Message(
            "control_change", channel=rt.channel, control=7,
            value=rt.volume, time=0))
        track.append(mido.Message(
            "control_change", channel=rt.channel, control=10,
            value=rt.pan, time=0))

        # Gather all messages and sort by absolute tick
        messages: list[tuple[int, mido.Message | mido.MetaMessage]] = []

        # Notes → note_on / note_off pairs
        for n in rt.notes:
            messages.append((n.tick, mido.Message(
                "note_on", channel=rt.channel,
                note=n.midi_note, velocity=n.velocity, time=0)))
            off_tick = n.tick + n.duration_ticks
            messages.append((off_tick, mido.Message(
                "note_off", channel=rt.channel,
                note=n.midi_note, velocity=0, time=0)))

        # CC (with linear interpolation expansion)
        _expand_cc_automation(rt.ccs, rt.channel, song.ppq, messages)

        # Pitch bend (with linear interpolation expansion)
        _expand_pb_automation(rt.pitch_bends, rt.channel, song.ppq, messages)

        # Aftertouch (with linear interpolation expansion)
        _expand_at_automation(rt.aftertouches, rt.channel, song.ppq, messages)

        # Text events
        for t in rt.texts:
            if t.type == "lyric":
                messages.append((t.tick, mido.MetaMessage(
                    "lyrics", text=t.text, time=0)))
            elif t.type in ("marker", "rehearsal"):
                messages.append((t.tick, mido.MetaMessage(
                    "marker", text=t.text, time=0)))
            else:
                messages.append((t.tick, mido.MetaMessage(
                    "text", text=t.text, time=0)))

        # Sort by tick with deterministic same-tick ordering (§C.5):
        # CC < pitch_bend < aftertouch < text/meta < note_off < note_on
        messages.sort(key=lambda m: (m[0], _event_sort_priority(m[1])))

        # Convert absolute ticks to delta times
        prev_tick = 0
        for abs_tick, msg in messages:
            msg.time = abs_tick - prev_tick
            prev_tick = abs_tick
            track.append(msg)

        track.append(mido.MetaMessage("end_of_track", time=0))

    return mid


def save_midi(song: ResolvedSong, path: str | Path) -> None:
    """Export a ResolvedSong to a MIDI file on disk."""
    mid = to_midi(song)
    mid.save(str(path))


def _event_sort_priority(msg) -> int:
    """Return sort priority for same-tick ordering per §C.5."""
    if isinstance(msg, mido.MetaMessage):
        # Text/lyric/marker meta-events
        return 7
    if isinstance(msg, mido.Message):
        t = msg.type
        if t == "program_change":
            return 3
        if t == "control_change":
            return 4
        if t == "pitchwheel":
            return 5
        if t == "aftertouch":
            return 6
        if t == "note_off":
            return 8
        if t == "note_on":
            return 9 if msg.velocity > 0 else 8  # vel 0 = note-off
    return 10


def _write_meta_track(track: mido.MidiTrack, song: ResolvedSong) -> None:
    """Write tempo and time signature events to track 0."""
    messages: list[tuple[int, mido.MetaMessage]] = []

    for t in song.tempos:
        us_per_beat = round(60_000_000 / t.tempo_bpm)
        messages.append((t.tick, mido.MetaMessage(
            "set_tempo", tempo=us_per_beat, time=0)))

    for ts in song.time_signatures:
        messages.append((ts.tick, mido.MetaMessage(
            "time_signature",
            numerator=ts.numerator,
            denominator=ts.denominator,
            time=0,
        )))

    messages.sort(key=lambda m: m[0])

    prev_tick = 0
    for abs_tick, msg in messages:
        msg.time = abs_tick - prev_tick
        prev_tick = abs_tick
        track.append(msg)

    track.append(mido.MetaMessage("end_of_track", time=0))


# ---------------------------------------------------------------------------
# Linear interpolation helpers
# ---------------------------------------------------------------------------

# Resolution: 1 message per 1/64 note ≈ ppq/16 ticks (§14.5)
_RAMP_DIVISOR = 16


def _lerp_steps(
    start_tick: int,
    end_tick: int,
    start_val: int,
    end_val: int,
    step_ticks: int,
) -> list[tuple[int, int]]:
    """Generate (tick, value) pairs for a linear ramp, excluding endpoints."""
    if step_ticks <= 0 or end_tick <= start_tick:
        return []
    points: list[tuple[int, int]] = []
    span = end_tick - start_tick
    t = start_tick + step_ticks
    while t < end_tick:
        frac = (t - start_tick) / span
        val = round(start_val + frac * (end_val - start_val))
        points.append((t, val))
        t += step_ticks
    return points


def _expand_cc_automation(
    ccs: list,
    channel: int,
    ppq: int,
    messages: list,
) -> None:
    """Emit CC messages, expanding interp=linear into intermediate steps."""
    from muq.ir import ResolvedCC
    step_ticks = max(1, ppq // _RAMP_DIVISOR)

    # Group by CC number to find previous values
    by_cc: dict[int, list[ResolvedCC]] = {}
    for c in ccs:
        by_cc.setdefault(c.cc, []).append(c)

    for cc_num, events in by_cc.items():
        events.sort(key=lambda e: e.tick)
        prev_val = 0  # default starting value per spec §14.5
        prev_tick = 0
        for ev in events:
            if ev.interp == "linear" and ev.tick > prev_tick:
                for t, v in _lerp_steps(prev_tick, ev.tick, prev_val, ev.value, step_ticks):
                    messages.append((t, mido.Message(
                        "control_change", channel=channel,
                        control=cc_num, value=max(0, min(127, v)), time=0)))
            messages.append((ev.tick, mido.Message(
                "control_change", channel=channel,
                control=cc_num, value=ev.value, time=0)))
            prev_val = ev.value
            prev_tick = ev.tick


def _expand_pb_automation(
    pbs: list,
    channel: int,
    ppq: int,
    messages: list,
) -> None:
    """Emit pitch bend messages, expanding interp=linear into intermediate steps."""
    from muq.ir import ResolvedPitchBend
    step_ticks = max(1, ppq // _RAMP_DIVISOR)

    sorted_pbs: list[ResolvedPitchBend] = sorted(pbs, key=lambda e: e.tick)
    prev_val = 0  # center
    prev_tick = 0
    for ev in sorted_pbs:
        if ev.interp == "linear" and ev.tick > prev_tick:
            for t, v in _lerp_steps(prev_tick, ev.tick, prev_val, ev.value, step_ticks):
                messages.append((t, mido.Message(
                    "pitchwheel", channel=channel,
                    pitch=max(-8192, min(8191, v)), time=0)))
        messages.append((ev.tick, mido.Message(
            "pitchwheel", channel=channel,
            pitch=ev.value, time=0)))
        prev_val = ev.value
        prev_tick = ev.tick


def _expand_at_automation(
    ats: list,
    channel: int,
    ppq: int,
    messages: list,
) -> None:
    """Emit aftertouch messages, expanding interp=linear into intermediate steps."""
    from muq.ir import ResolvedAftertouch
    step_ticks = max(1, ppq // _RAMP_DIVISOR)

    sorted_ats: list[ResolvedAftertouch] = sorted(ats, key=lambda e: e.tick)
    prev_val = 0
    prev_tick = 0
    for ev in sorted_ats:
        if ev.interp == "linear" and ev.tick > prev_tick:
            for t, v in _lerp_steps(prev_tick, ev.tick, prev_val, ev.value, step_ticks):
                messages.append((t, mido.Message(
                    "aftertouch", channel=channel,
                    value=max(0, min(127, v)), time=0)))
        messages.append((ev.tick, mido.Message(
            "aftertouch", channel=channel,
            value=ev.value, time=0)))
        prev_val = ev.value
        prev_tick = ev.tick
