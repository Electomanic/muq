"""Music theory utilities — pitch, duration, scales, time signatures."""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Duration tokens & articulations
# ---------------------------------------------------------------------------

# Duration token → beats (quarter-note units)
DURATION_TOKENS: dict[str, float] = {
    "w": 4.0, "wd": 6.0, "wdd": 7.0, "wt": 4.0 * 2 / 3,
    "h": 2.0, "hd": 3.0, "hdd": 3.5, "ht": 2.0 * 2 / 3,
    "q": 1.0, "qd": 1.5, "qdd": 1.75, "qt": 1.0 * 2 / 3,
    "e": 0.5, "ed": 0.75, "edd": 0.875, "et": 0.5 * 2 / 3,
    "s": 0.25, "sd": 0.375, "sdd": 0.4375, "st": 0.25 * 2 / 3,
    "x": 0.125, "xd": 0.1875, "xdd": 0.21875, "xt": 0.125 * 2 / 3,
}

# Articulation effects: name → (gate_multiplier, velocity_add)
# None means no change from default
ARTICULATIONS: dict[str, tuple[float | None, int | None]] = {
    "staccato": (0.5, None),
    "staccatissimo": (0.25, None),
    "legato": (1.0, None),
    "tenuto": (1.0, 10),
    "accent": (None, 20),
    "marcato": (0.85, 30),
    "portato": (0.75, None),
}


def event_dur_beats(event) -> float:
    """Get the duration of a note or rest event in beats.

    Checks token-based duration (dur/rest) first, then numeric
    (dur_beats/rest_beats). Returns 0.0 if neither is set (e.g. tie
    continuation without explicit duration).
    """
    dur = getattr(event, "dur", None)
    if dur and dur in DURATION_TOKENS:
        return DURATION_TOKENS[dur]
    dur_beats = getattr(event, "dur_beats", None)
    if dur_beats is not None:
        return dur_beats
    rest = getattr(event, "rest", None)
    if rest and rest in DURATION_TOKENS:
        return DURATION_TOKENS[rest]
    rest_beats = getattr(event, "rest_beats", None)
    if rest_beats is not None:
        return rest_beats
    return 0.0


# ---------------------------------------------------------------------------
# Pitch utilities
# ---------------------------------------------------------------------------

_NOTE_TO_SEMITONE: dict[str, int] = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}


def pitch_to_midi(pitch: str) -> int:
    """Convert a pitch string like 'C4', 'F#5', 'Bb3' to a MIDI note number.

    C4 = 60 (middle C). Raises ValueError for invalid pitch strings.
    """
    p = pitch.upper()
    idx = 1
    note_name = p[0]
    if note_name not in _NOTE_TO_SEMITONE:
        raise ValueError(f"Invalid note name: {pitch}")
    semitone = _NOTE_TO_SEMITONE[note_name]
    # Accidentals
    if idx < len(p) and p[idx] == "#":
        semitone += 1
        idx += 1
        if idx < len(p) and p[idx] == "#":
            semitone += 1
            idx += 1
    elif idx < len(p) and p[idx] == "B":
        semitone -= 1
        idx += 1
        if idx < len(p) and p[idx] == "B":
            semitone -= 1
            idx += 1
    # Octave
    octave_str = p[idx:]
    try:
        octave = int(octave_str)
    except ValueError:
        raise ValueError(f"Invalid octave in pitch: {pitch}")
    midi_note = (octave + 1) * 12 + semitone
    if not 0 <= midi_note <= 127:
        raise ValueError(f"MIDI note {midi_note} out of range for pitch: {pitch}")
    return midi_note


def is_pitched_notation(name: str) -> bool:
    """Return True if a note string looks like pitched notation (e.g. C4, F#3, Bb-1)."""
    if not name:
        return False
    upper = name.upper()
    if upper[0] not in _NOTE_TO_SEMITONE:
        return False
    i = 1
    while i < len(upper) and upper[i] in ("#", "B"):
        i += 1
    if i >= len(upper):
        return False
    rest = upper[i:]
    try:
        int(rest)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Scales & key validation
# ---------------------------------------------------------------------------

# Scale intervals (semitones from root) — §4.4 scale validation
_SCALE_INTERVALS: dict[str, tuple[int, ...]] = {
    "major":            (0, 2, 4, 5, 7, 9, 11),
    "minor":            (0, 2, 3, 5, 7, 8, 10),  # alias for natural_minor
    "natural_minor":    (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor":   (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor":    (0, 2, 3, 5, 7, 9, 11),
    "dorian":           (0, 2, 3, 5, 7, 9, 10),
    "phrygian":         (0, 1, 3, 5, 7, 8, 10),
    "lydian":           (0, 2, 4, 6, 7, 9, 11),
    "mixolydian":       (0, 2, 4, 5, 7, 9, 10),
    "aeolian":          (0, 2, 3, 5, 7, 8, 10),
    "locrian":          (0, 1, 3, 5, 6, 8, 10),
    "pentatonic":       (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues":            (0, 3, 5, 6, 7, 10),
    "chromatic":        tuple(range(12)),
}


def scale_pitch_classes(key: str) -> frozenset[int] | None:
    """Return the set of pitch classes (0-11) for the given key string.

    Key format: 'C major', 'F# minor', 'Bb dorian', etc.
    Returns None if the scale mode is unknown.
    """
    parts = key.split()
    if len(parts) < 2:
        return None
    root_str = parts[0].upper()
    mode = "_".join(parts[1:]).lower()

    # Parse root note semitone
    idx = 0
    if root_str[0] not in _NOTE_TO_SEMITONE:
        return None
    root = _NOTE_TO_SEMITONE[root_str[0]]
    idx = 1
    while idx < len(root_str) and root_str[idx] == "#":
        root += 1
        idx += 1
    while idx < len(root_str) and root_str[idx] == "B":
        root -= 1
        idx += 1

    intervals = _SCALE_INTERVALS.get(mode)
    if intervals is None:
        return None

    return frozenset((root + i) % 12 for i in intervals)


_KEY_GRAMMAR = re.compile(
    r'^[A-Ga-g](?:#|b|##|bb)?\s+'
    r'(?:major|minor|natural_minor|harmonic_minor|melodic_minor|'
    r'dorian|phrygian|lydian|mixolydian|aeolian|locrian|'
    r'pentatonic|minor_pentatonic|blues|chromatic)$'
)


def is_valid_key(key: str) -> bool:
    """Check if a key string matches the muq key grammar."""
    return _KEY_GRAMMAR.match(key) is not None


# ---------------------------------------------------------------------------
# Time signatures
# ---------------------------------------------------------------------------

def parse_time_signature(time_str: str) -> tuple[int, int]:
    """Parse a time signature string like '4/4' into (numerator, denominator)."""
    parts = time_str.split("/")
    return int(parts[0]), int(parts[1])


def beats_per_bar(time_str: str) -> float:
    """Compute beats per bar (in quarter notes) from a time signature string."""
    num, denom = parse_time_signature(time_str)
    return num * (4.0 / denom)
