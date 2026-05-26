"""CLI entry point for the muq music format tool.

Commands:
    muq validate <file>           — check a .muq file for errors
    muq info <file>               — show song metadata, tracks, and patterns
    muq fmt <file>                — reformat to canonical style
    muq export song <file>        — export full arrangement as MIDI
    muq export track <file>       — export tracks as separate MIDI stems
    muq export pattern <file>     — export patterns as separate MIDI clips
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from muq.parser import parse, ParseError
from muq.validate import validate
from muq.resolve import resolve, resolve_pattern
from muq.midi import save_midi
from muq.fmt import fmt
from muq.ir import ResolvedSong


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_and_validate(path: Path) -> tuple:
    """Parse and validate a .muq file. Returns (doc, errors, warnings)."""
    doc = parse(path)
    diags = validate(doc)
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]
    return doc, errors, warnings


def _print_diags(errors, warnings) -> None:
    for d in errors:
        print(f"error[{d.code}]: {d.message} ({d.path})", file=sys.stderr)
    for d in warnings:
        print(f"warning[{d.code}]: {d.message} ({d.path})", file=sys.stderr)


def _save_one(resolved: ResolvedSong, out_path: Path, label: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_midi(resolved, out_path)
    print(f"  {label} -> {out_path}", file=sys.stderr)


def _filter_tracks(resolved: ResolvedSong, names: list[str]) -> ResolvedSong:
    """Return a copy of resolved keeping only tracks whose name is in *names*."""
    return ResolvedSong(
        ppq=resolved.ppq,
        tempos=resolved.tempos,
        time_signatures=resolved.time_signatures,
        tracks=[t for t in resolved.tracks if t.name in names],
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muq",
        description="muq — YAML-based music format tool",
    )
    sub = parser.add_subparsers(dest="command")

    # --- validate -----------------------------------------------------------
    p_val = sub.add_parser(
        "validate",
        help="Check a .muq file for errors and warnings",
        description="Parse and validate a .muq file, reporting any "
                    "schema violations, semantic errors, or warnings.",
    )
    p_val.add_argument("file", type=Path, help="Path to .muq file")

    # --- info ---------------------------------------------------------------
    p_info = sub.add_parser(
        "info",
        help="Show song metadata, tracks, and patterns",
        description="Print a summary of a .muq file: song metadata, "
                    "track listing (instrument, channel), pattern listing "
                    "(notation, bar count), and arrangement sections.",
    )
    p_info.add_argument("file", type=Path, help="Path to .muq file")

    # --- fmt ----------------------------------------------------------------
    p_fmt = sub.add_parser(
        "fmt",
        help="Reformat a .muq file to canonical style",
        description="Parse and re-emit a .muq file using the canonical "
                    "formatting rules from the spec (§17). Useful for "
                    "normalizing hand-edited files.",
    )
    p_fmt.add_argument("file", type=Path, help="Path to .muq file")
    p_fmt.add_argument(
        "-o", "--output", type=Path,
        help="Write formatted output to this file (default: stdout)",
    )
    p_fmt.add_argument(
        "-i", "--in-place", action="store_true",
        help="Overwrite the input file with formatted output",
    )

    # --- export (group) -----------------------------------------------------
    p_export = sub.add_parser(
        "export",
        help="Export to MIDI (song, track, or pattern)",
        description="Export a .muq file to one or more MIDI files. "
                    "Use a sub-command to choose what to export:\n\n"
                    "  song     Full arrangement as a single MIDI file\n"
                    "  track    Individual tracks as separate MIDI stems\n"
                    "  pattern  Individual patterns as separate MIDI clips",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_sub = p_export.add_subparsers(dest="export_target")

    # Shared export arguments added via parent
    export_common = argparse.ArgumentParser(add_help=False)
    export_common.add_argument("file", type=Path, help="Path to .muq file")
    export_common.add_argument(
        "--ppq", type=int, default=480,
        help="Pulses per quarter note (default: 480)",
    )
    export_common.add_argument(
        "--dry-run", action="store_true",
        help="Validate and resolve without writing files",
    )

    # export song
    p_exp_song = export_sub.add_parser(
        "song",
        parents=[export_common],
        help="Export the full arrangement as a single MIDI file",
        description="Resolve the complete arrangement and write a "
                    "Standard MIDI File (Type 1). Each track becomes a "
                    "separate MIDI track.",
    )
    p_exp_song.add_argument(
        "-o", "--output", type=Path,
        help="Output .mid file (default: <input>.mid)",
    )

    # export track
    p_exp_track = export_sub.add_parser(
        "track",
        parents=[export_common],
        help="Export tracks as separate MIDI stems",
        description="Resolve the full arrangement, then write each track "
                    "as its own MIDI file. Use -n/--name to select specific "
                    "tracks; without it, all tracks are exported.",
    )
    p_exp_track.add_argument(
        "-o", "--output", type=Path,
        help="Output directory (default: <input>_tracks/)",
    )
    p_exp_track.add_argument(
        "-n", "--name", type=str, action="append", default=None,
        metavar="TRACK",
        help="Export only this track (repeatable for multiple tracks)",
    )

    # export pattern
    p_exp_pat = export_sub.add_parser(
        "pattern",
        parents=[export_common],
        help="Export patterns as separate MIDI clips",
        description="Export each pattern in isolation as a short MIDI clip, "
                    "using the song's base tempo and time signature. "
                    "Use -n/--name to select specific patterns; without it, "
                    "all patterns are exported.",
    )
    p_exp_pat.add_argument(
        "-o", "--output", type=Path,
        help="Output directory (default: <input>_patterns/)",
    )
    p_exp_pat.add_argument(
        "-n", "--name", type=str, action="append", default=None,
        metavar="PATTERN",
        help="Export only this pattern (repeatable for multiple patterns)",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_validate(args) -> int:
    try:
        doc, errors, warnings = _parse_and_validate(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_diags(errors, warnings)

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    if warnings:
        print(f"valid ({len(warnings)} warning(s))", file=sys.stderr)
    else:
        print("valid", file=sys.stderr)
    return 0


def _cmd_info(args) -> int:
    try:
        doc = parse(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    s = doc.song
    print(f"Song:  {s.title or '(untitled)'}")
    if s.artist:
        print(f"  artist: {s.artist}")
    print(f"  tempo:  {s.tempo} qpm")
    print(f"  time:   {s.time}")
    if s.key:
        print(f"  key:    {s.key}", end="")
        if s.scale_mode:
            print(f" {s.scale_mode}", end="")
        print()

    print(f"\nTracks ({len(doc.tracks)}):")
    for name, track in doc.tracks.items():
        perc = " [percussion]" if track.is_percussion else ""
        print(f"  {name:20s}  ch {track.channel:>2d}  {track.instrument}{perc}")

    print(f"\nPatterns ({len(doc.patterns)}):")
    for name, pat in doc.patterns.items():
        nota = f" [{pat.notation}]" if pat.notation != "pitched" else ""
        swing = f" swing={pat.swing}" if pat.swing != 50 else ""
        print(f"  {name:20s}  {len(pat.bars)} bar(s){nota}{swing}")

    print(f"\nArrangement ({len(doc.arrangement)} section(s)):")
    for sec in doc.arrangement:
        repeat = f" x{sec.repeat}" if sec.repeat > 1 else ""
        tracks = ", ".join(sec.patterns.keys())
        print(f"  {sec.name:20s}  tracks: {tracks}{repeat}")

    return 0


def _cmd_fmt(args) -> int:
    try:
        doc = parse(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    output = fmt(doc)

    if args.in_place:
        args.file.write_text(output, encoding="utf-8")
        print(f"Formatted {args.file}", file=sys.stderr)
    elif args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Formatted to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


def _cmd_export_song(args) -> int:
    try:
        doc, errors, warnings = _parse_and_validate(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_diags(errors, warnings)
    if errors:
        return 1

    resolved = resolve(doc, ppq=args.ppq)

    if args.dry_run:
        print("dry-run: resolved OK", file=sys.stderr)
        return 0

    out_path = args.output or args.file.with_suffix(".mid")
    _save_one(resolved, out_path, "song")
    return 0


def _cmd_export_track(args) -> int:
    try:
        doc, errors, warnings = _parse_and_validate(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_diags(errors, warnings)
    if errors:
        return 1

    # Determine which tracks to export
    track_names = args.name or list(doc.tracks.keys())
    for name in track_names:
        if name not in doc.tracks:
            print(f"error: unknown track: {name}", file=sys.stderr)
            return 1

    resolved = resolve(doc, ppq=args.ppq)

    if args.dry_run:
        print("dry-run: resolved OK", file=sys.stderr)
        return 0

    out_dir = args.output or (args.file.with_suffix("") / "tracks")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in track_names:
        filtered = _filter_tracks(resolved, [name])
        out_path = out_dir / f"{name}.mid"
        _save_one(filtered, out_path, name)

    print(f"Exported {len(track_names)} track(s) to {out_dir}", file=sys.stderr)
    return 0


def _cmd_export_pattern(args) -> int:
    try:
        doc, errors, warnings = _parse_and_validate(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    _print_diags(errors, warnings)
    if errors:
        return 1

    # Determine which patterns to export
    pattern_names = args.name or list(doc.patterns.keys())
    for name in pattern_names:
        if name not in doc.patterns:
            print(f"error: unknown pattern: {name}", file=sys.stderr)
            return 1

    if args.dry_run:
        for name in pattern_names:
            resolve_pattern(doc, name, ppq=args.ppq)
        print("dry-run: resolved OK", file=sys.stderr)
        return 0

    out_dir = args.output or (args.file.with_suffix("") / "patterns")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in pattern_names:
        resolved = resolve_pattern(doc, name, ppq=args.ppq)
        out_path = out_dir / f"{name}.mid"
        _save_one(resolved, out_path, name)

    print(f"Exported {len(pattern_names)} pattern(s) to {out_dir}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_EXPORT_DISPATCH = {
    "song": _cmd_export_song,
    "track": _cmd_export_track,
    "pattern": _cmd_export_pattern,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "info":
        return _cmd_info(args)
    if args.command == "fmt":
        return _cmd_fmt(args)
    if args.command == "export":
        target = getattr(args, "export_target", None)
        if not target:
            # Show export help when no sub-command given
            parser.parse_args(["export", "--help"])
            return 1
        return _EXPORT_DISPATCH[target](args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
