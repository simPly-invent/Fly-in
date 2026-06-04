"""Terminal visualization with ANSI colors for the drone simulation."""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, TextIO

from flyin.graph import Graph
from flyin.simulator import Simulator, TurnReport
from flyin.zone import Zone, ZoneType


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


def _color_for(name: Optional[str]) -> str:
    """Return the ANSI sequence for a colour name, or empty string."""
    if name is None:
        return ""
    return _COLOR_MAP.get(name.lower(), "")


def _zone_marker(zone: Zone) -> str:
    """Return a 1-char marker used to depict a zone type at a glance."""
    if zone.is_start:
        return "S"
    if zone.is_end:
        return "E"
    return {
        ZoneType.NORMAL: "o",
        ZoneType.PRIORITY: "*",
        ZoneType.RESTRICTED: "!",
        ZoneType.BLOCKED: "x",
    }[zone.zone_type]


class TerminalView:
    """Renders the simulation step-by-step in a coloured terminal."""

    def __init__(
        self,
        simulator: Simulator,
        stream: Optional[TextIO] = None,
        use_colour: bool = True,
    ) -> None:
        self.simulator: Simulator = simulator
        self.stream: TextIO = stream if stream is not None else sys.stdout
        self.use_colour: bool = use_colour

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
        """Print map summary and the candidate paths the simulator considered."""
        g = self.simulator.graph
        self._writeln(self._styled("=== Fly-in simulation ===", ANSI_BOLD))
        self._writeln(
            f"Drones: {g.nb_drones} | "
            f"Zones: {sum(1 for _ in g.zones)} | "
            f"Connections: {sum(1 for _ in g.connections)}"
        )
        self._writeln(
            f"Start: {self._styled_zone(g.start)}  "
            f"End: {self._styled_zone(g.end)}"
        )
        self._writeln()
        self._writeln(self._styled("Candidate paths:", ANSI_BOLD))
        for i, path in enumerate(paths, 1):
            cost = sum(z.zone_type.move_cost for z in path[1:])
            rendered = " -> ".join(self._styled_zone(z) for z in path)
            self._writeln(f"  [{i}] cost={cost}  {rendered}")
        self._writeln()

    def render_legend(self) -> None:
        """Print a small legend explaining zone markers."""
        legend = "  ".join(
            [
                f"{self._styled('S', ANSI_BOLD)}=start",
                f"{self._styled('E', ANSI_BOLD)}=end",
                "o=normal",
                f"{self._styled('*', _color_for('cyan'))}=priority",
                f"{self._styled('!', _color_for('red'))}=restricted",
                f"{self._styled('x', _color_for('gray'))}=blocked",
            ]
        )
        self._writeln(self._styled("Legend: ", ANSI_BOLD) + legend)
        self._writeln()

    # ------------------------------------------------------------- per turn

    def render_turn(self, report: TurnReport) -> None:
        """Print one turn of the simulation in the spec-mandated format."""
        line = report.render()
        prefix = self._styled(f"T{report.turn:>3}: ", ANSI_DIM)
        self._writeln(prefix + line)

    def render_simulation(self, reports: List[TurnReport]) -> None:
        """Print all turn reports in order."""
        self._writeln(self._styled("Simulation log:", ANSI_BOLD))
        for report in reports:
            self.render_turn(report)
        self._writeln()

    def render_spec_output(self, reports: List[TurnReport]) -> None:
        """Print the strict spec output (no decoration, one line per turn).

        This is the format peers may compare against the subject example:
            D1-roof1 D2-corridorA
            D1-roof2 D2-tunnelB
            D1-goal D2-goal
        """
        self._writeln(self._styled("Spec output:", ANSI_BOLD))
        for report in reports:
            self._writeln(report.render())
        self._writeln()

    # ---------------------------------------------------------------- stats

    def render_stats(self) -> None:
        """Print summary metrics (total turns, secondary scoring info)."""
        sim = self.simulator
        self._writeln(self._styled("Statistics:", ANSI_BOLD))
        self._writeln(f"  total turns       : {sim.total_turns()}")
        self._writeln(f"  drones delivered  : {len(sim.drones)}")
        self._writeln(
            f"  total path cost   : {sim.total_path_cost()}"
        )
        self._writeln(
            f"  avg turns / drone : {sim.average_turns_per_drone():.2f}"
        )

    # ------------------------------------------------------------- helpers

    def _styled_zone(self, zone: Zone) -> str:
        marker = _zone_marker(zone)
        colour = _color_for(zone.color)
        label = f"{marker}{zone.name}"
        if zone.max_drones > 1:
            label = f"{label}[{zone.max_drones}]"
        return self._styled(label, ANSI_BOLD, colour) if colour else self._styled(
            label, ANSI_BOLD
        )

    def render_full(
        self,
        paths: List[List[Zone]],
        reports: List[TurnReport],
        spec_only: bool = False,
    ) -> None:
        """One-shot render: header, log, spec output, stats.

        When ``spec_only`` is True only the spec-mandated lines are printed
        (useful for scripting / piping to diff).
        """
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
    """Convenience wrapper that builds a TerminalView and renders everything."""
    _ = Graph  # keep the Graph import alive for the type checker
    view = TerminalView(simulator, use_colour=use_colour)
    view.render_full(paths, reports, spec_only=spec_only)
