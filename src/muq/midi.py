"""MIDI exporter — convert resolved IR to SMF Type 1 via mido."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
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
    """Write tempo, time signature, and section marker events to track 0."""
    messages: list[tuple[int, mido.MetaMessage]] = []

    for t in song.tempos:
        us_per_beat = round(60_000_000 / t.tempo_qpm)
        messages.append((t.tick, mido.MetaMessage(
            "set_tempo", tempo=us_per_beat, time=0)))

    for ts in song.time_signatures:
        messages.append((ts.tick, mido.MetaMessage(
            "time_signature",
            numerator=ts.numerator,
            denominator=ts.denominator,
            time=0,
        )))

    for mk in song.markers:
        messages.append((mk.tick, mido.MetaMessage(
            "marker", text=mk.text, time=0)))

    # Stable sort: tempo/time-sig precede markers at the same tick (§C.5)
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
    step_ticks = max(1, ppq // _RAMP_DIVISOR)

    # Group by CC number — each CC lane has its own interpolation state
    by_cc: dict[int, list] = defaultdict(list)
    for c in ccs:
        by_cc[c.cc].append(c)

    for cc_num, events in by_cc.items():
        events.sort(key=lambda e: e.tick)
        _expand_automation_lane(
            events, step_ticks, (0, 127),
            lambda v, cc=cc_num: mido.Message(
                "control_change", channel=channel,
                control=cc, value=v, time=0),
            messages,
        )


def _expand_pb_automation(
    pbs: list,
    channel: int,
    ppq: int,
    messages: list,
) -> None:
    """Emit pitch bend messages, expanding interp=linear into intermediate steps."""
    step_ticks = max(1, ppq // _RAMP_DIVISOR)
    sorted_pbs = sorted(pbs, key=lambda e: e.tick)
    _expand_automation_lane(
        sorted_pbs, step_ticks, (-8192, 8191),
        lambda v: mido.Message(
            "pitchwheel", channel=channel, pitch=v, time=0),
        messages,
    )


def _expand_at_automation(
    ats: list,
    channel: int,
    ppq: int,
    messages: list,
) -> None:
    """Emit aftertouch messages, expanding interp=linear into intermediate steps."""
    step_ticks = max(1, ppq // _RAMP_DIVISOR)
    sorted_ats = sorted(ats, key=lambda e: e.tick)
    _expand_automation_lane(
        sorted_ats, step_ticks, (0, 127),
        lambda v: mido.Message(
            "aftertouch", channel=channel, value=v, time=0),
        messages,
    )


def _expand_automation_lane(
    events: list,
    step_ticks: int,
    clamp: tuple[int, int],
    make_msg: Callable[[int], mido.Message],
    messages: list[tuple[int, mido.Message]],
) -> None:
    """Walk a sorted event lane, emitting messages with linear interpolation.

    Each event must have .tick, .value, and .interp attributes.
    ``make_msg(value)`` constructs the MIDI message for a given value.
    """
    lo, hi = clamp
    has_prev = False
    prev_val = 0
    prev_tick = 0
    for ev in events:
        # §14.5: linear with no previous event degrades to step — no
        # implicit ramp from 0
        if has_prev and ev.interp == "linear" and ev.tick > prev_tick:
            for t, v in _lerp_steps(
                prev_tick, ev.tick, prev_val, ev.value, step_ticks
            ):
                messages.append((t, make_msg(max(lo, min(hi, v)))))
        messages.append((ev.tick, make_msg(ev.value)))
        has_prev = True
        prev_val = ev.value
        prev_tick = ev.tick
