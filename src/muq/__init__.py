"""muq — parser, validator, and MIDI exporter for the muq music format."""

from muq.parser import parse
from muq.validate import validate
from muq.resolve import resolve
from muq.midi import to_midi

__all__ = ["parse", "validate", "resolve", "to_midi"]
