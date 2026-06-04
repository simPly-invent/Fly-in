"""Fly-in: drone routing CLI entry point.

Usage:
    python main.py                       # interactive menu
    python main.py <map_file>            # run on the given map (terminal)
    python main.py <map_file> --pygame   # run with the pygame view
    python main.py <map_file> --no-color --spec-only   # plain spec output
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from flyin.parser import MapParseError, MapParser
from flyin.simulator import Simulator, TurnReport
from flyin.terminal_view import TerminalView
from flyin.zone import Zone


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fly-in",
        description=(
            "Simulate a fleet of drones moving from the start hub to the end "
            "hub of a map file, minimizing the number of simulation turns."
        ),
    )
    parser.add_argument(
        "map_file",
        nargs="?",
        help=(
            "path to a map file (see maps/ for examples). If omitted, the "
            "interactive menu is launched."
        ),
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="launch the interactive menu (default when no map is given)",
    )
    parser.add_argument(
        "--pygame",
        action="store_true",
        help="render the simulation in a pygame window (requires pygame)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors in the terminal output",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help=(
            "print only the spec-mandated movement lines (one per turn), "
            "without headers, paths, legend, or statistics"
        ),
    )
    return parser


def _run_pygame(
    simulator: Simulator,
    paths: List[List[Zone]],
    reports: List[TurnReport],
    title: str,
) -> int:
    """Open the pygame view on a fully-simulated run."""
    try:
        from flyin.pygame_view import PygameUnavailableError, PygameView
    except ImportError as exc:
        print(f"pygame view unavailable: {exc}", file=sys.stderr)
        return 4
    try:
        view = PygameView(
            simulator.graph, simulator, paths, reports, title=title
        )
        view.run()
    except PygameUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    return 0


def run(argv: Optional[List[str]] = None) -> int:
    """Parse arguments, run the simulation, render the output.

    Returns the process exit code.
    """
    args = _build_arg_parser().parse_args(argv)

    if args.menu or args.map_file is None:
        from flyin.menu import Menu
        Menu().run()
        return 0

    try:
        graph = MapParser().parse_file(args.map_file)
    except MapParseError as exc:
        print(f"map error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot read map file: {exc}", file=sys.stderr)
        return 2

    simulator = Simulator(graph)
    try:
        paths = simulator.prepare()
        reports = simulator.run()
    except RuntimeError as exc:
        print(f"simulation error: {exc}", file=sys.stderr)
        return 3

    if args.pygame:
        return _run_pygame(simulator, paths, reports, title=f"Fly-in — {args.map_file}")

    view = TerminalView(simulator, use_colour=not args.no_color)
    view.render_full(paths, reports, spec_only=args.spec_only)
    return 0


def main() -> None:
    """Script entrypoint."""
    sys.exit(run())


if __name__ == "__main__":
    main()
