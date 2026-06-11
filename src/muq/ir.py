"""Resolved intermediate representation — flat event list with absolute tick times."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResolvedNote:
    tick: int
    channel: int  # 0-indexed (MIDI channel 0-15)
    midi_note: int
    velocity: int
    duration_ticks: int
    voice: int | None = None


@dataclass
class ResolvedCC:
    tick: int
    channel: int
    cc: int
    value: int
    interp: str = "step"


@dataclass
class ResolvedPitchBend:
    tick: int
    channel: int
    value: int
    interp: str = "step"


@dataclass
class ResolvedAftertouch:
    tick: int
    channel: int
    value: int
    interp: str = "step"


@dataclass
class ResolvedTempo:
    tick: int
    tempo_qpm: float


@dataclass
class ResolvedTimeSig:
    tick: int
    numerator: int
    denominator: int


@dataclass
class ResolvedText:
    tick: int
    text: str
    type: str  # lyric, marker, rehearsal, chord, text


@dataclass
class ResolvedTrack:
    name: str
    channel: int  # 0-indexed
    program: int | None  # None for percussion
    volume: int  # CC7 value 0-127
    pan: int  # CC10 value 0-127
    notes: list[ResolvedNote]
    ccs: list[ResolvedCC]
    pitch_bends: list[ResolvedPitchBend]
    aftertouches: list[ResolvedAftertouch]
    texts: list[ResolvedText]


@dataclass
class ResolvedSong:
    ppq: int
    tempos: list[ResolvedTempo]
    time_signatures: list[ResolvedTimeSig]
    tracks: list[ResolvedTrack]
    markers: list[ResolvedText] = field(default_factory=list)
