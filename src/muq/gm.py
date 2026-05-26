"""General MIDI instrument and drum name lookup tables (Appendix A & B).

Music theory utilities (pitch, duration, scales, time signatures) live in
muq.theory.  For convenience they are re-exported here so existing imports
like ``from muq.gm import pitch_to_midi`` continue to work.
"""

from __future__ import annotations

# Re-export theory utilities so ``from muq.gm import X`` still works
from muq.theory import (  # noqa: F401
    ARTICULATIONS,
    DURATION_TOKENS,
    beats_per_bar,
    event_dur_beats,
    is_pitched_notation,
    is_valid_key,
    parse_time_signature,
    pitch_to_midi,
    scale_pitch_classes,
)


# ---------------------------------------------------------------------------
# GM instrument table (Appendix A)
# ---------------------------------------------------------------------------

# Instrument name → GM program number (0-indexed)
GM_INSTRUMENTS: dict[str, int] = {
    # Piano (0-7)
    "acoustic_grand_piano": 0,
    "bright_acoustic_piano": 1,
    "electric_grand_piano": 2,
    "honky_tonk_piano": 3,
    "electric_piano_1": 4,
    "electric_piano_2": 5,
    "harpsichord": 6,
    "clavinet": 7,
    # Chromatic Percussion (8-15)
    "celesta": 8,
    "glockenspiel": 9,
    "music_box": 10,
    "vibraphone": 11,
    "marimba": 12,
    "xylophone": 13,
    "tubular_bells": 14,
    "dulcimer": 15,
    # Organ (16-23)
    "drawbar_organ": 16,
    "percussive_organ": 17,
    "rock_organ": 18,
    "church_organ": 19,
    "reed_organ": 20,
    "accordion": 21,
    "harmonica": 22,
    "tango_accordion": 23,
    # Guitar (24-31)
    "acoustic_guitar_nylon": 24,
    "acoustic_guitar_steel": 25,
    "electric_guitar_jazz": 26,
    "electric_guitar_clean": 27,
    "electric_guitar_muted": 28,
    "overdriven_guitar": 29,
    "distortion_guitar": 30,
    "guitar_harmonics": 31,
    # Bass (32-39)
    "acoustic_bass": 32,
    "electric_bass_finger": 33,
    "electric_bass_pick": 34,
    "fretless_bass": 35,
    "slap_bass_1": 36,
    "slap_bass_2": 37,
    "synth_bass_1": 38,
    "synth_bass_2": 39,
    # Strings (40-47)
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "contrabass": 43,
    "tremolo_strings": 44,
    "pizzicato_strings": 45,
    "orchestral_harp": 46,
    "timpani": 47,
    # Ensemble (48-55)
    "string_ensemble_1": 48,
    "string_ensemble_2": 49,
    "synth_strings_1": 50,
    "synth_strings_2": 51,
    "choir_aahs": 52,
    "voice_oohs": 53,
    "synth_choir": 54,
    "orchestra_hit": 55,
    # Brass (56-63)
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "muted_trumpet": 59,
    "french_horn": 60,
    "brass_section": 61,
    "synth_brass_1": 62,
    "synth_brass_2": 63,
    # Reed (64-71)
    "soprano_sax": 64,
    "alto_sax": 65,
    "tenor_sax": 66,
    "baritone_sax": 67,
    "oboe": 68,
    "english_horn": 69,
    "bassoon": 70,
    "clarinet": 71,
    # Pipe (72-79)
    "piccolo": 72,
    "flute": 73,
    "recorder": 74,
    "pan_flute": 75,
    "blown_bottle": 76,
    "shakuhachi": 77,
    "whistle": 78,
    "ocarina": 79,
    # Synth Lead (80-87)
    "lead_square": 80,
    "lead_sawtooth": 81,
    "lead_calliope": 82,
    "lead_chiff": 83,
    "lead_charang": 84,
    "lead_voice": 85,
    "lead_fifths": 86,
    "lead_bass_lead": 87,
    # Synth Pad (88-95)
    "pad_new_age": 88,
    "pad_warm": 89,
    "pad_polysynth": 90,
    "pad_choir": 91,
    "pad_bowed": 92,
    "pad_metallic": 93,
    "pad_halo": 94,
    "pad_sweep": 95,
    # Synth Effects (96-103)
    "fx_rain": 96,
    "fx_soundtrack": 97,
    "fx_crystal": 98,
    "fx_atmosphere": 99,
    "fx_brightness": 100,
    "fx_goblins": 101,
    "fx_echoes": 102,
    "fx_sci_fi": 103,
    # Ethnic (104-111)
    "sitar": 104,
    "banjo": 105,
    "shamisen": 106,
    "koto": 107,
    "kalimba": 108,
    "bagpipe": 109,
    "fiddle": 110,
    "shanai": 111,
    # Percussive (112-119)
    "tinkle_bell": 112,
    "agogo": 113,
    "steel_drums": 114,
    "woodblock": 115,
    "taiko_drum": 116,
    "melodic_tom": 117,
    "synth_drum": 118,
    "reverse_cymbal": 119,
    # Sound Effects (120-127)
    "guitar_fret_noise": 120,
    "breath_noise": 121,
    "seashore": 122,
    "bird_tweet": 123,
    "telephone_ring": 124,
    "helicopter": 125,
    "applause": 126,
    "gunshot": 127,
}

# Reverse lookup: program number → canonical name
GM_PROGRAM_TO_NAME: dict[int, str] = {v: k for k, v in GM_INSTRUMENTS.items()}

# Case-insensitive lookup: lowercased name → program number
_GM_INSTRUMENTS_LOWER: dict[str, int] = {k.lower(): v for k, v in GM_INSTRUMENTS.items()}


def gm_instrument_lookup(name: str) -> int | None:
    """Case-insensitive GM instrument lookup. Returns program number or None."""
    return _GM_INSTRUMENTS_LOWER.get(name.lower())


# ---------------------------------------------------------------------------
# Pan resolution
# ---------------------------------------------------------------------------

# Pan string → MIDI CC 10 value
_PAN_MAP: dict[str, int] = {"left": 0, "center": 64, "right": 127}


def resolve_pan(pan: str | int) -> int:
    """Resolve a pan value (string or int) to MIDI CC 10 integer 0-127."""
    if isinstance(pan, int):
        return max(0, min(127, pan))
    return _PAN_MAP.get(pan.lower(), 64)


# ---------------------------------------------------------------------------
# GM drum map (Appendix B)
# ---------------------------------------------------------------------------

# GM drum map: name → MIDI note (includes primary names and all aliases)
GM_DRUM_MAP: dict[str, int] = {
    # 35
    "acoustic_bass_drum": 35, "kick2": 35,
    # 36
    "kick": 36, "bd": 36, "bass_drum": 36,
    # 37
    "rimshot": 37, "side_stick": 37,
    # 38
    "snare": 38, "sd": 38,
    # 39
    "clap": 39, "hc": 39, "hand_clap": 39,
    # 40
    "snare_electric": 40, "sd2": 40,
    # 41
    "tom6": 41, "low_floor_tom": 41,
    # 42
    "hh": 42, "hihat": 42, "closed_hihat": 42,
    # 43
    "tom5": 43, "high_floor_tom": 43,
    # 44
    "hh_pedal": 44, "pedal_hihat": 44,
    # 45
    "tom4": 45, "low_tom": 45,
    # 46
    "hh_open": 46, "open_hihat": 46,
    # 47
    "tom3": 47, "low_mid_tom": 47,
    # 48
    "tom2": 48, "hi_mid_tom": 48,
    # 49
    "crash": 49, "crash_cymbal": 49, "crash1": 49,
    # 50
    "tom1": 50, "high_tom": 50,
    # 51
    "ride": 51, "ride_cymbal": 51, "ride1": 51,
    # 52
    "chinese_cymbal": 52,
    # 53
    "ride_bell": 53,
    # 54
    "tambourine": 54, "tamb": 54,
    # 55
    "splash": 55, "splash_cymbal": 55,
    # 56
    "cowbell": 56,
    # 57
    "crash2": 57, "crash_cymbal_2": 57,
    # 58
    "vibraslap": 58,
    # 59
    "ride2": 59, "ride_cymbal_2": 59,
    # 60
    "bongo_hi": 60, "hi_bongo": 60,
    # 61
    "bongo_lo": 61, "low_bongo": 61,
    # 62
    "conga_mute": 62, "mute_hi_conga": 62,
    # 63
    "conga_hi": 63, "open_hi_conga": 63,
    # 64
    "conga_lo": 64, "low_conga": 64,
    # 65
    "timbale_hi": 65, "high_timbale": 65,
    # 66
    "timbale_lo": 66, "low_timbale": 66,
    # 67
    "agogo_hi": 67, "high_agogo": 67,
    # 68
    "agogo_lo": 68, "low_agogo": 68,
    # 69
    "cabasa": 69,
    # 70
    "maracas": 70,
    # 71
    "whistle_short": 71, "short_whistle": 71,
    # 72
    "whistle_long": 72, "long_whistle": 72,
    # 73
    "guiro_short": 73, "short_guiro": 73,
    # 74
    "guiro_long": 74, "long_guiro": 74,
    # 75
    "claves": 75,
    # 76
    "woodblock_hi": 76, "hi_wood_block": 76,
    # 77
    "woodblock_lo": 77, "low_wood_block": 77,
    # 78
    "cuica_mute": 78, "mute_cuica": 78,
    # 79
    "cuica_open": 79, "open_cuica": 79,
    # 80
    "triangle_mute": 80, "mute_triangle": 80,
    # 81
    "triangle_open": 81, "open_triangle": 81,
}


def resolve_drum_name(
    name: str,
    per_track_map: dict[str, int] | None,
    global_map: dict[str, int] | None,
) -> int | None:
    """Resolve a drum name to MIDI note. Returns None if not found."""
    lower = name.lower()
    if per_track_map and lower in per_track_map:
        return per_track_map[lower]
    if global_map and lower in global_map:
        return global_map[lower]
    return GM_DRUM_MAP.get(lower)
