"""Terminal visualization with ANSI colors for the drone simulation.

This is the project's single visual layer: a coloured, step-by-step terminal
render. It satisfies the subject's "visual representation" requirement on its
own (a GUI is an optional bonus, deliberately left out to keep the project
light and fully defendable).
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, TextIO

from flyin.network import Zone, ZoneType
from flyin.pathfinder import PathFinder
from flyin.simulator import Simulator, TurnReport


# Common color names from the map files mapped to ANSI 8-color codes.
# Names not listed here fall back to no colour (uncoloured terminal output).
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"

_COLOR_MAP: Dict[str, str] = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "purple": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "grey": "\033[90m",
    "orange": "\033[38;5;208m",
    "brown": "\033[38;5;130m",
    "pink": "\033[38;5;213m",
    "lime": "\033[38;5;154m",
    "gold": "\033[38;5;220m",
}

_MARKERS: Dict[ZoneType, str] = {
    ZoneType.NORMAL: "o",
    ZoneType.PRIORITY: "*",
    ZoneType.RESTRICTED: "!",
    ZoneType.BLOCKED: "x",
}


def _color_for(name: Optional[str]) -> str:
    if name is None:
        return ""
    return _COLOR_MAP.get(name.lower(), "")


def _zone_marker(zone: Zone) -> str:
    if zone.is_start:
        return "S"
    if zone.is_end:
        return "E"
    return _MARKERS[zone.zone_type]


class TerminalView:
    """Renders the simulation step-by-step in a coloured terminal."""

    def __init__(
        self,
        simulator: Simulator,
        stream: Optional[TextIO] = None,
        use_colour: bool = True,
    ) -> None:
        self.simulator = simulator
        self.stream: TextIO = stream if stream is not None else sys.stdout
        self.use_colour = use_colour

    # ----------------------------------------------------------------- write

    def _write(self, text: str) -> None:
        self.stream.write(text)

    def _writeln(self, text: str = "") -> None:
        self._write(text + "\n")

    def _styled(self, text: str, *codes: str) -> str:
        if not self.use_colour or not codes:
            return text
        return "".join(codes) + text + ANSI_RESET

    # ----------------------------------------------------------- top sections

    def render_header(self, paths: List[List[Zone]]) -> None:
        g = self.simulator.graph
        self._writeln(self._styled("=== Fly-in simulation ===", ANSI_BOLD))
        self._writeln(
            f"Drones: {g.nb_drones} | "
            f"Zones: {len(list(g.zones))} | "
            f"Connections: {len(list(g.connections))}"
        )
        self._writeln(f"Start: {self._styled_zone(g.start)}")
        self._writeln(f"End:   {self._styled_zone(g.end)}")
        self._writeln(self._styled("Candidate paths:", ANSI_BOLD))
        for index, path in enumerate(paths, start=1):
            sequence = " -> ".join(zone.name for zone in path)
            self._writeln(
                f"  [{index}] (cost {PathFinder.path_cost(path)}) {sequence}"
            )
        self._writeln()

    def render_legend(self) -> None:
        legend = (
            "S=start  E=end  o=normal  "
            f"{self._styled('*=priority', _color_for('cyan'))}  "
            f"{self._styled('!=restricted', _color_for('red'))}  "
            f"{self._styled('x=blocked', _color_for('gray'))}"
        )
        self._writeln(self._styled("Legend: ", ANSI_BOLD) + legend)
        self._writeln()

    # ------------------------------------------------------------- per turn

    def render_turn(self, report: TurnReport) -> None:
        line = report.render()
        prefix = self._styled(f"T{report.turn:>3}: ", ANSI_DIM)
        self._writeln(prefix + line)

    def render_simulation(self, reports: List[TurnReport]) -> None:
        self._writeln(self._styled("Simulation log:", ANSI_BOLD))
        for report in reports:
            self.render_turn(report)
        self._writeln()

    def render_spec_output(self, reports: List[TurnReport]) -> None:
        self._writeln(self._styled("Spec output:", ANSI_BOLD))
        for report in reports:
            self._writeln(report.render())
        self._writeln()

    # ---------------------------------------------------------------- stats

    def render_stats(self) -> None:
        sim = self.simulator
        delivered = sum(1 for d in sim.drones if d.delivered)
        self._writeln(self._styled("Statistics:", ANSI_BOLD))
        self._writeln(f"  total turns        : {sim.total_turns()}")
        self._writeln(f"  drones delivered   : {delivered}/{len(sim.drones)}")
        self._writeln(f"  total path cost    : {sim.total_path_cost()}")
        self._writeln(
            f"  avg turns per drone: {sim.average_turns_per_drone():.2f}"
        )

    # ------------------------------------------------------------- helpers

    def _styled_zone(self, zone: Zone) -> str:
        marker = _zone_marker(zone)
        colour = _color_for(zone.color)
        label = f"{marker}{zone.name}"
        if zone.max_drones > 1:
            label += f"[{zone.max_drones}]"
        if colour:
            return self._styled(label, ANSI_BOLD, colour)
        return self._styled(label, ANSI_BOLD)

    def render_full(
        self,
        paths: List[List[Zone]],
        reports: List[TurnReport],
        spec_only: bool = False,
    ) -> None:
        if spec_only:
            for report in reports:
                self._writeln(report.render())
            return
        self.render_header(paths)
        self.render_legend()
        self.render_simulation(reports)
        self.render_spec_output(reports)
        self.render_stats()


def render(
    simulator: Simulator,
    paths: List[List[Zone]],
    reports: List[TurnReport],
    use_colour: bool = True,
    spec_only: bool = False,
) -> None:
    view = TerminalView(simulator, use_colour=use_colour)
    view.render_full(paths, reports, spec_only=spec_only)
