"""Resolved intermediate representation — flat event list with absolute tick times."""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass
class ResolvedPitchBend:
    tick: int
    channel: int
    value: int


@dataclass
class ResolvedAftertouch:
    tick: int
    channel: int
    value: int


@dataclass
class ResolvedTempo:
    tick: int
    tempo_bpm: float


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
