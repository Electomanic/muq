"""Data model — dataclasses mirroring the muq spec."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@dataclass
class NoteEvent:
    note: str | list[str]
    dur: str | None = None
    dur_beats: float | None = None
    vel: int = 80
    beat: float | None = None
    tie: bool = False
    voice: int | None = None
    offset_beats: float = 0.0
    articulation: str | None = None


@dataclass
class RestEvent:
    rest: str | None = None
    rest_beats: float | None = None
    beat: float | None = None


@dataclass
class CCEvent:
    cc: int
    value: int
    beat: float | None = None
    interp: str = "step"
    offset_beats: float = 0.0


@dataclass
class PitchBendEvent:
    pitch_bend: int
    beat: float | None = None
    interp: str = "step"
    offset_beats: float = 0.0


@dataclass
class AftertouchEvent:
    aftertouch: int
    beat: float | None = None
    interp: str = "step"
    offset_beats: float = 0.0


@dataclass
class TextEvent:
    text: str
    type: str = "text"
    beat: float | None = None
    offset_beats: float = 0.0


Event = NoteEvent | RestEvent | CCEvent | PitchBendEvent | AftertouchEvent | TextEvent

Bar = list[Event]


# ---------------------------------------------------------------------------
# Pattern / Track / Section
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    bars: list[Bar]
    notation: str = "pitched"
    swing: int = 50


@dataclass
class Track:
    instrument: str
    channel: int
    volume: int = 100
    pan: str | int = "center"
    percussion: bool | None = None
    drum_map: dict[str, int] | None = None

    @property
    def is_percussion(self) -> bool:
        if self.percussion is not None:
            return self.percussion
        return self.channel == 10 or self.instrument == "standard"


@dataclass
class TempoEvent:
    bar: int
    beat: float
    tempo: float
    interp: str = "step"


@dataclass
class MeterEvent:
    bar: int
    time: str


@dataclass
class Section:
    name: str
    patterns: dict[str, str]  # track_name → pattern_name
    repeat: int = 1
    tempo: float | None = None
    time: str | None = None
    tie_across: bool = False
    tempo_events: list[TempoEvent] = field(default_factory=list)
    meter_events: list[MeterEvent] = field(default_factory=list)
    pickup_beats: float | None = None


# ---------------------------------------------------------------------------
# Song / Document
# ---------------------------------------------------------------------------

@dataclass
class Song:
    tempo: float
    time: str
    title: str | None = None
    artist: str | None = None
    key: str | None = None
    scale_mode: str | None = None
    version: str | None = None


@dataclass
class MuqDocument:
    song: Song
    tracks: dict[str, Track]
    patterns: dict[str, Pattern]
    arrangement: list[Section]
    drum_map: dict[str, int] | None = None
