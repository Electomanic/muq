"""CLI entry point — muq validate / muq export / muq clips / muq fmt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from muq.parser import parse, ParseError
from muq.validate import validate
from muq.resolve import resolve, resolve_pattern
from muq.midi import save_midi
from muq.fmt import fmt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="muq", description="muq music format tool")
    sub = parser.add_subparsers(dest="command")

    # validate
    p_val = sub.add_parser("validate", help="Validate a .muq file")
    p_val.add_argument("file", type=Path, help="Path to .muq file")

    # export
    p_exp = sub.add_parser("export", help="Export a .muq file to MIDI")
    p_exp.add_argument("file", type=Path, help="Path to .muq file")
    p_exp.add_argument("-o", "--output", type=Path, help="Output .mid file path")
    p_exp.add_argument("--ppq", type=int, default=480, help="Pulses per quarter note (default: 480)")

    # fmt
    p_fmt = sub.add_parser("fmt", help="Format a .muq file to canonical form")
    p_fmt.add_argument("file", type=Path, help="Path to .muq file")
    p_fmt.add_argument("-o", "--output", type=Path, help="Output file (default: stdout)")
    p_fmt.add_argument("-i", "--in-place", action="store_true", help="Format in place")

    # clips
    p_clips = sub.add_parser("clips", help="Export each pattern as a separate MIDI clip")
    p_clips.add_argument("file", type=Path, help="Path to .muq file")
    p_clips.add_argument("-o", "--output-dir", type=Path, default=None,
                         help="Output directory (default: <file>_clips/)")
    p_clips.add_argument("--ppq", type=int, default=480,
                         help="Pulses per quarter note (default: 480)")
    p_clips.add_argument("-p", "--pattern", type=str, default=None,
                         help="Export only this pattern (by name)")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "validate":
        return _cmd_validate(args)
    elif args.command == "export":
        return _cmd_export(args)
    elif args.command == "fmt":
        return _cmd_fmt(args)
    elif args.command == "clips":
        return _cmd_clips(args)
    return 1


def _cmd_validate(args) -> int:
    try:
        doc = parse(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    diags = validate(doc)
    errors = [d for d in diags if d.severity == "error"]
    warnings = [d for d in diags if d.severity == "warning"]

    for d in errors:
        print(f"error[{d.code}]: {d.message} ({d.path})", file=sys.stderr)
    for d in warnings:
        print(f"warning[{d.code}]: {d.message} ({d.path})", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1

    if warnings:
        print(f"valid ({len(warnings)} warning(s))", file=sys.stderr)
    else:
        print("valid", file=sys.stderr)
    return 0


def _cmd_export(args) -> int:
    try:
        doc = parse(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    diags = validate(doc)
    errors = [d for d in diags if d.severity == "error"]
    if errors:
        for d in errors:
            print(f"error[{d.code}]: {d.message} ({d.path})", file=sys.stderr)
        return 1

    resolved = resolve(doc, ppq=args.ppq)

    out_path = args.output
    if out_path is None:
        out_path = args.file.with_suffix(".mid")

    save_midi(resolved, out_path)
    print(f"Exported to {out_path}", file=sys.stderr)
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


def _cmd_clips(args) -> int:
    try:
        doc = parse(args.file)
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    diags = validate(doc)
    errors = [d for d in diags if d.severity == "error"]
    if errors:
        for d in errors:
            print(f"error[{d.code}]: {d.message} ({d.path})", file=sys.stderr)
        return 1

    out_dir = args.output_dir
    if out_dir is None:
        out_dir = args.file.with_suffix("") / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)

    pattern_names = [args.pattern] if args.pattern else list(doc.patterns.keys())
    for pname in pattern_names:
        if pname not in doc.patterns:
            print(f"error: unknown pattern: {pname}", file=sys.stderr)
            return 1
        resolved = resolve_pattern(doc, pname, ppq=args.ppq)
        out_path = out_dir / f"{pname}.mid"
        save_midi(resolved, out_path)
        print(f"  {pname} -> {out_path}", file=sys.stderr)

    print(f"Exported {len(pattern_names)} clip(s) to {out_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
