"""Fly-in: drone routing CLI entry point.

Launches the interactive map menu and keeps looping until the user quits.

Usage:
    python main.py                  # interactive map menu
    python main.py --no-color       # plain (no ANSI)
    python main.py --spec-only      # spec-format lines only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from flyin.menu import Menu
from flyin.parser import MapParseError, MapParser
from flyin.simulator import Simulator
from flyin.view import TerminalView

DEFAULT_MAPS_ROOT = Path(__file__).resolve().parent / "maps"


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="fly-in",
        description=(
            "Route a fleet of drones from start to end in fewest turns."
        ),
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="browse maps interactively",
    )
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
    parser.add_argument(
        "map_file",
        nargs="?",
        default=None,
        help="map file to simulate directly (without --menu)",
    )
    return parser


def _simulate(map_file: str, use_colour: bool, spec_only: bool) -> int:
    """Parse, simulate, and render a single map; return a process exit code.

    Returns 0 on success, 2 for parse/IO errors, and 3 if the simulation
    cannot complete (e.g. no path or deadlock).
    """
    try:
        graph = MapParser().parse_file(map_file)
    except (OSError, MapParseError) as exc:
        print(exc, file=sys.stderr)
        return 2
    simulator = Simulator(graph)
    try:
        paths = simulator.prepare()
        reports = simulator.run()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 3

    view = TerminalView(simulator, use_colour=use_colour)
    view.render_full(paths, reports, spec_only=spec_only)
    return 0


def _wait_for_enter() -> bool:
    """Pause until the user presses Enter. Returns False if the user aborts."""
    try:
        input("\nPress Enter to return to the menu (Ctrl+C to quit)... ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return True


def run(argv: Optional[List[str]] = None) -> int:
    """Run the interactive menu loop, simulating each chosen map until quit."""
    args = _build_arg_parser().parse_args(argv)
    menu_choice = args.menu
    use_colour = not args.no_color
    spec_only = args.spec_only

    if menu_choice:
        menu = Menu(Path(DEFAULT_MAPS_ROOT), use_colour=use_colour)
        while True:
            choice = menu.prompt()
            if choice is None:
                print("Bye.")
                return 0
            _simulate(str(choice), use_colour, spec_only)
            if not _wait_for_enter():
                return 0
    else:
        map_path = Path(args.map_file)
        if map_path.is_dir():
            print("Use --menu to browse a directory.", file=sys.stderr)
            return 1
        _simulate(str(map_path), use_colour, spec_only)
    return 0


def main() -> None:
    """CLI entry point: run the app and exit with its status code."""
    try:
        run()
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        print("PROGRAM TERMINATED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
