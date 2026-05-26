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

        # CC
        for c in rt.ccs:
            messages.append((c.tick, mido.Message(
                "control_change", channel=rt.channel,
                control=c.cc, value=c.value, time=0)))

        # Pitch bend
        for pb in rt.pitch_bends:
            messages.append((pb.tick, mido.Message(
                "pitchwheel", channel=rt.channel,
                pitch=pb.value, time=0)))

        # Aftertouch
        for at in rt.aftertouches:
            messages.append((at.tick, mido.Message(
                "aftertouch", channel=rt.channel,
                value=at.value, time=0)))

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

        # Sort by tick, with note_off before note_on at same tick
        messages.sort(key=lambda m: (m[0], 0 if _is_note_off(m[1]) else 1))

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


def _is_note_off(msg) -> bool:
    return isinstance(msg, mido.Message) and msg.type == "note_off"


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
