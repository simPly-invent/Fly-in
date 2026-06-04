"""Interactive text menu for picking a map and a render mode.

Inspired by the maze-project menu the author wrote previously: a refreshing
text screen (using ``\\033c`` to clear) with numbered options, plus a
sub-menu to pick a map from the ``maps/`` directory.

The menu drives a single Simulator + (TerminalView or PygameView) pipeline,
so it has no logic of its own beyond user interaction.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from flyin.graph import Graph
from flyin.parser import MapParseError, MapParser
from flyin.simulator import Simulator, TurnReport
from flyin.terminal_view import TerminalView
from flyin.zone import Zone


CLEAR = "\033c"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
MAGENTA = "\033[35m"

DEFAULT_MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


class Menu:
    """Top-level interactive menu loop.

    Attributes:
        maps_dir: directory scanned for map files (recursively).
        map_path: currently selected map file.
        render_mode: 'terminal' or 'pygame'.
    """

    def __init__(self, maps_dir: Optional[Path] = None) -> None:
        self.maps_dir: Path = maps_dir if maps_dir is not None else DEFAULT_MAPS_DIR
        self.map_path: Optional[Path] = self._default_map()
        self.render_mode: str = "terminal"
        self.use_colour: bool = True
        self.spec_only: bool = False

    # ----------------------------------------------------------- map listing

    def _all_maps(self) -> List[Path]:
        """Return every .txt file under ``maps_dir`` sorted by category/name."""
        if not self.maps_dir.is_dir():
            return []
        return sorted(self.maps_dir.rglob("*.txt"))

    def _default_map(self) -> Optional[Path]:
        maps = self._all_maps() if hasattr(self, "maps_dir") else []
        if not maps:
            maps = sorted(DEFAULT_MAPS_DIR.rglob("*.txt"))
        if not maps:
            return None
        # Prefer the simplest available map: easy → medium → hard → challenger.
        preference = ("easy", "medium", "hard", "challenger")
        for tier in preference:
            for path in maps:
                if tier in path.parts:
                    return path
        return maps[0]

    # ------------------------------------------------------------- printing

    @staticmethod
    def _print(text: str = "") -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def _print_header(self) -> None:
        self._print(CLEAR + BOLD + " ============== " + RESET)
        self._print(BOLD + "|  Fly-in menu  |" + RESET)
        self._print(BOLD + " ============== " + RESET)

    def _print_state(self) -> None:
        map_label = str(self.map_path) if self.map_path else "(no map)"
        self._print(f"  Map        : {GREEN}{map_label}{RESET}")
        self._print(
            f"  Render     : {CYAN}{self.render_mode}{RESET}"
            f"  (colour: {'on' if self.use_colour else 'off'},"
            f" spec-only: {'on' if self.spec_only else 'off'})"
        )

    def _print_menu(self) -> None:
        self._print()
        self._print(BOLD + "  What do you want?" + RESET)
        self._print("    1) Launch simulation")
        self._print("    2) Choose a map")
        self._print("    3) Switch render (terminal / pygame)")
        self._print("    4) Toggle colour output")
        self._print("    5) Toggle spec-only output (terminal mode)")
        self._print("    6) Quit")
        self._print()

    # ------------------------------------------------------------- choices

    def _choose_map(self) -> None:
        maps = self._all_maps()
        if not maps:
            self._print(RED + "No map files found under " + str(self.maps_dir) + RESET)
            input("Press Enter to continue...")
            return

        # Group by parent folder (category) for a clearer listing.
        groups: dict[str, List[Path]] = {}
        for path in maps:
            category = path.parent.name if path.parent != self.maps_dir else "(root)"
            groups.setdefault(category, []).append(path)

        index_to_path: List[Path] = []
        self._print(CLEAR + BOLD + "  Available maps" + RESET)
        for category in sorted(groups):
            self._print(f"\n  {YELLOW}{category}{RESET}")
            for path in groups[category]:
                index_to_path.append(path)
                self._print(f"    {len(index_to_path):>2}) {path.name}")
        self._print("\n     0) Cancel")

        choice = input("\n  Pick a number: ").strip()
        if choice == "0" or choice == "":
            return
        try:
            n = int(choice)
        except ValueError:
            self._print(RED + "  Not a number." + RESET)
            input("  Press Enter to continue...")
            return
        if not 1 <= n <= len(index_to_path):
            self._print(RED + "  Out of range." + RESET)
            input("  Press Enter to continue...")
            return
        self.map_path = index_to_path[n - 1]

    def _switch_render(self) -> None:
        self.render_mode = "pygame" if self.render_mode == "terminal" else "terminal"

    def _launch(self) -> None:
        if self.map_path is None:
            self._print(RED + "  No map selected." + RESET)
            input("  Press Enter to continue...")
            return
        try:
            graph = MapParser().parse_file(self.map_path)
        except MapParseError as exc:
            self._print(RED + f"  map error: {exc}" + RESET)
            input("  Press Enter to continue...")
            return
        except OSError as exc:
            self._print(RED + f"  cannot read map: {exc}" + RESET)
            input("  Press Enter to continue...")
            return

        simulator = Simulator(graph)
        try:
            paths = simulator.prepare()
            reports = simulator.run()
        except RuntimeError as exc:
            self._print(RED + f"  simulation error: {exc}" + RESET)
            input("  Press Enter to continue...")
            return

        if self.render_mode == "pygame":
            self._launch_pygame(graph, simulator, paths, reports)
        else:
            self._launch_terminal(simulator, paths, reports)

    def _launch_terminal(
        self,
        simulator: Simulator,
        paths: List[List[Zone]],
        reports: List[TurnReport],
    ) -> None:
        self._print(CLEAR)
        view = TerminalView(simulator, use_colour=self.use_colour)
        view.render_full(paths, reports, spec_only=self.spec_only)
        input("\n  Press Enter to return to the menu...")

    def _launch_pygame(
        self,
        graph: Graph,
        simulator: Simulator,
        paths: List[List[Zone]],
        reports: List[TurnReport],
    ) -> None:
        try:
            from flyin.pygame_view import PygameUnavailableError, PygameView
        except ImportError as exc:
            self._print(RED + f"  pygame view unavailable: {exc}" + RESET)
            input("  Press Enter to continue...")
            return
        try:
            view = PygameView(
                graph,
                simulator,
                paths,
                reports,
                title=f"Fly-in — {self.map_path.name if self.map_path else ''}",
            )
            view.run()
        except PygameUnavailableError as exc:
            self._print(RED + f"  {exc}" + RESET)
            input("  Press Enter to continue...")

    # ---------------------------------------------------------------- loop

    def run(self) -> None:
        """Start the interactive menu loop. Returns when the user quits."""
        while True:
            self._print_header()
            self._print_state()
            self._print_menu()
            try:
                choice = input("  : ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print(CLEAR + "  Goodbye :)")
                return

            if choice == "1":
                self._launch()
            elif choice == "2":
                self._choose_map()
            elif choice == "3":
                self._switch_render()
            elif choice == "4":
                self.use_colour = not self.use_colour
            elif choice == "5":
                self.spec_only = not self.spec_only
            elif choice == "6":
                self._print(CLEAR + "  Goodbye :)")
                return
            # any other input just refreshes the menu
