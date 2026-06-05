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
    # - Créer un argparse.ArgumentParser(prog="fly-in", description=...).
    # - Ajouter:
    #     map_file (positional, nargs="?")
    #     --menu (store_true)
    #     --pygame (store_true)
    #     --no-color (store_true)
    #     --spec-only (store_true)
    # - Retourner le parser.
    raise NotImplementedError("À implémenter")


def _run_pygame(
    simulator: Simulator,
    paths: List[List[Zone]],
    reports: List[TurnReport],
    title: str,
) -> int:
    # - Import dynamique de flyin.pygame_view (catch ImportError → print stderr + return 4).
    # - Construire PygameView(simulator.graph, simulator, paths, reports, title=title) puis view.run().
    # - Catch PygameUnavailableError → print stderr + return 4.
    # - Sinon retourner 0.
    raise NotImplementedError("À implémenter")


def run(argv: Optional[List[str]] = None) -> int:
    # - args = _build_arg_parser().parse_args(argv).
    # - Si args.menu OU args.map_file None → from flyin.menu import Menu ; Menu().run() ; return 0.
    # - graph = MapParser().parse_file(args.map_file):
    #     - catch MapParseError → stderr + return 2.
    #     - catch OSError → stderr + return 2.
    # - simulator = Simulator(graph).
    # - paths = simulator.prepare() ; reports = simulator.run() (catch RuntimeError → stderr + 3).
    # - Si args.pygame → _run_pygame(...) et return son code.
    # - Sinon view = TerminalView(simulator, use_colour=not args.no_color)
    #         view.render_full(paths, reports, spec_only=args.spec_only).
    # - return 0.
    raise NotImplementedError("À implémenter")


def main() -> None:
    # - sys.exit(run()) — propage le code retour au shell.
    raise NotImplementedError("À implémenter")


if __name__ == "__main__":
    main()
