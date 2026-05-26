"""Parser — load YAML, validate against JSON Schema, build model."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from muq.model import (
    AftertouchEvent,
    CCEvent,
    MeterEvent,
    MuqDocument,
    NoteEvent,
    Pattern,
    PitchBendEvent,
    RestEvent,
    Section,
    Song,
    TempoEvent,
    TextEvent,
    Track,
)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "spec" / "muq.schema.json"


def _load_schema() -> dict:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _parse_event(d: dict) -> (
    NoteEvent | RestEvent | CCEvent | PitchBendEvent | AftertouchEvent | TextEvent
):
    if "note" in d:
        return NoteEvent(
            note=d["note"],
            dur=d.get("dur"),
            dur_beats=d.get("dur_beats"),
            vel=d.get("vel", 80),
            beat=d.get("beat"),
            tie=d.get("tie", False),
            voice=d.get("voice"),
            offset_beats=d.get("offset_beats", 0.0),
            articulation=d.get("articulation"),
        )
    if "rest" in d or "rest_beats" in d:
        return RestEvent(
            rest=d.get("rest"),
            rest_beats=d.get("rest_beats"),
            beat=d.get("beat"),
        )
    if "cc" in d:
        return CCEvent(
            cc=d["cc"],
            value=d["value"],
            beat=d.get("beat"),
            interp=d.get("interp", "step"),
            offset_beats=d.get("offset_beats", 0.0),
        )
    if "pitch_bend" in d:
        return PitchBendEvent(
            pitch_bend=d["pitch_bend"],
            beat=d.get("beat"),
            interp=d.get("interp", "step"),
            offset_beats=d.get("offset_beats", 0.0),
        )
    if "aftertouch" in d:
        return AftertouchEvent(
            aftertouch=d["aftertouch"],
            beat=d.get("beat"),
            interp=d.get("interp", "step"),
            offset_beats=d.get("offset_beats", 0.0),
        )
    if "text" in d:
        return TextEvent(
            text=d["text"],
            type=d.get("type", "text"),
            beat=d.get("beat"),
            offset_beats=d.get("offset_beats", 0.0),
        )
    raise ValueError(f"Unrecognized event: {d}")


def _parse_pattern(name: str, d: dict) -> Pattern:
    bars = []
    for bar_data in d["bars"]:
        bar = [_parse_event(ev) for ev in (bar_data or [])]
        bars.append(bar)
    return Pattern(bars=bars, swing=d.get("swing", 50))


def _parse_track(name: str, d: dict) -> Track:
    return Track(
        instrument=d["instrument"],
        channel=d["channel"],
        volume=d.get("volume", 100),
        pan=d.get("pan", "center"),
        percussion=d.get("percussion"),
        drum_map=d.get("drum_map"),
    )


def _parse_section(d: dict) -> Section:
    tempo_events = [
        TempoEvent(bar=te["bar"], beat=te["beat"], tempo=te["tempo"],
                    interp=te.get("interp", "step"))
        for te in d.get("tempo_events", [])
    ]
    meter_events = [
        MeterEvent(bar=me["bar"], time=me["time"])
        for me in d.get("meter_events", [])
    ]
    return Section(
        name=d["name"],
        patterns=d["patterns"],
        repeat=d.get("repeat", 1),
        tempo=d.get("tempo"),
        time=d.get("time"),
        tie_across=d.get("tie_across", False),
        tempo_events=tempo_events,
        meter_events=meter_events,
        pickup_beats=d.get("pickup_beats"),
    )


class ParseError(Exception):
    pass


def parse(source: str | Path) -> MuqDocument:
    """Parse a .muq file (path or YAML string) into a MuqDocument.

    Performs JSON Schema validation first. Raises ParseError on failure.
    """
    if isinstance(source, Path) or (isinstance(source, str) and (
        source.endswith(".muq") or source.endswith(".yaml") or source.endswith(".yml")
    )):
        path = Path(source)
        text = path.read_text(encoding="utf-8")
    else:
        text = source

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ParseError(f"Invalid YAML: {e}") from e

    if not isinstance(raw, dict):
        raise ParseError("Document root must be a YAML mapping")

    # Schema validation
    schema = _load_schema()
    try:
        jsonschema.validate(raw, schema)
    except jsonschema.ValidationError as e:
        raise ParseError(f"Schema validation failed: {e.message}") from e

    # Build model
    song_d = raw["song"]
    song = Song(
        tempo=song_d["tempo"],
        time=song_d["time"],
        title=song_d.get("title"),
        artist=song_d.get("artist"),
        key=song_d.get("key"),
        scale_mode=song_d.get("scale_mode"),
        version=song_d.get("version"),
    )

    tracks = {name: _parse_track(name, td) for name, td in raw["tracks"].items()}
    patterns = {name: _parse_pattern(name, pd) for name, pd in raw["patterns"].items()}
    arrangement = [_parse_section(sd) for sd in raw["arrangement"]]
    drum_map = raw.get("drum_map")

    return MuqDocument(
        song=song,
        tracks=tracks,
        patterns=patterns,
        arrangement=arrangement,
        drum_map=drum_map,
    )
