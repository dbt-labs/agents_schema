"""Command-line interface for the notes_on example provider."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .provider import NotesOnError, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agents-schema-notes-on",
        description="Publish object-scoped notes into AGENTS.NOTES_ON_* tables.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--notes-file",
        required=True,
        type=Path,
        help="path to a YAML file containing schema, table, and column notes",
    )
    args = parser.parse_args(argv)
    try:
        run(args.notes_file)
    except (FileNotFoundError, NotesOnError) as e:
        print(f"agents-schema-notes-on: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
