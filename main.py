"""Fly-in: drone routing CLI entry point.

Usage:
    python main.py <map_file>                       # coloured terminal run
    python main.py <map_file> --no-color            # plain (no ANSI)
    python main.py <map_file> --spec-only           # spec-format lines only
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from flyin.parser import MapParseError, MapParser
from flyin.simulator import Simulator
from flyin.view import TerminalView


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fly-in",
        description="Route a fleet of drones from start to end in fewest turns.",
    )
    parser.add_argument("map_file", help="path to the map file to simulate")
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colours in the output",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help="print only the spec-mandated lines (one per turn)",
    )
    return parser


def run(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        graph = MapParser().parse_file(args.map_file)
    except MapParseError as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 2

    simulator = Simulator(graph)
    try:
        paths = simulator.prepare()
        reports = simulator.run()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 3

    view = TerminalView(simulator, use_colour=not args.no_color)
    view.render_full(paths, reports, spec_only=args.spec_only)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
