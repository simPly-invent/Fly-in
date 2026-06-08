"""Drone simulation engine.

Combines a simple multi-path *scheduler* (which decides which precomputed
path each drone follows) with a turn-by-turn *simulator* (which respects
zone capacities, connection capacities, and the 2-turn transit rule for
restricted zones).

The per-drone state (:class:`Drone`) lives here because it is only ever
manipulated by the simulator. Each turn the simulator emits one
:class:`TurnReport` so the visualization layer can render the run while
staying fully decoupled from the movement logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from flyin.graph import Graph
from flyin.network import Connection, Zone, ZoneType
from flyin.pathfinder import PathFinder


# ----------------------------------------------------------------- drone state


class Drone:
    """A single drone navigating the network.

    A drone has a stable integer identifier (D1, D2, ...), a current zone,
    and an optional in-flight transit when crossing a restricted zone (which
    requires 2 turns: 1 spent on the connection, 1 to arrive).
    """

    def __init__(
        self, drone_id: int, start: Zone, path: Optional[List[Zone]] = None
    ) -> None:
        self.drone_id = drone_id
        self.position: Zone = start
        self.path: List[Zone] = path if path is not None else [start]
        self.path_index: int = 0
        self.transit_connection: Optional[Connection] = None
        self.transit_target: Optional[Zone] = None
        self.delivered: bool = False

    @property
    def label(self) -> str:
        return f"D{self.drone_id}"

    @property
    def is_in_transit(self) -> bool:
        return self.transit_connection is not None

    def assign_path(self, path: List[Zone]) -> None:
        if not path:
            raise ValueError("path must contain at least the start")
        self.path = path
        self.path_index = 0
        self.position = path[0]

    def next_zone(self) -> Optional[Zone]:
        if self.path_index + 1 >= len(self.path):
            return None
        return self.path[self.path_index + 1]

    def start_transit(self, connection: Connection, target: Zone) -> None:
        self.transit_connection = connection
        self.transit_target = target

    def finish_transit(self) -> None:
        if self.transit_target is None:
            raise RuntimeError("no pending transit")
        self.position = self.transit_target
        self.path_index += 1
        self.transit_connection = None
        self.transit_target = None

    def step_to(self, zone: Zone) -> None:
        self.position = zone
        self.path_index += 1

    def __repr__(self) -> str:
        if self.is_in_transit and self.transit_connection is not None:
            return f"{self.label}@transit({self.transit_connection.display_name()})"
        return f"{self.label}@{self.position.name}"


# ---------------------------------------------------------------- turn reports


@dataclass
class MoveRecord:
    """One drone's movement event for a single turn."""

    drone_label: str
    destination: str  # zone name (arrival) or connection display name (transit)

    def render(self) -> str:
        return f"{self.drone_label}-{self.destination}"


@dataclass
class TurnReport:
    """Snapshot of moves performed during a single simulation turn."""

    turn: int
    moves: List[MoveRecord] = field(default_factory=list)

    def render(self) -> str:
        return " ".join(move.render() for move in self.moves)


# -------------------------------------------------------------------- scheduler


class PathScheduler:
    """Assign drones to candidate paths to minimize makespan."""

    def __init__(self, paths: List[List[Zone]]) -> None:
        if not paths:
            raise ValueError("scheduler needs at least one path")
        self.paths = paths

    def assign(self, nb_drones: int) -> List[int]:
        costs = [PathFinder.path_cost(p) for p in self.paths]
        counts = [0] * len(self.paths)
        assignment: List[int] = []
        for _ in range(nb_drones):
            best = min(
                range(len(self.paths)),
                key=lambda i: costs[i] + counts[i],
            )
            assignment.append(best)
            counts[best] += 1
        return assignment


# -------------------------------------------------------------------- simulator


class Simulator:
    """Turn-by-turn drone simulation respecting all subject constraints."""

    SAFETY_TURN_LIMIT = 10_000

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.drones: List[Drone] = []
        self.turn_reports: List[TurnReport] = []

    # ----------------------------------------------------------------- setup

    def prepare(self) -> List[List[Zone]]:
        finder = PathFinder(self.graph)
        paths = finder.find_candidate_paths(self.graph.nb_drones)
        if not paths:
            raise RuntimeError("no path from start to end")
        scheduler = PathScheduler(paths)
        assignment = scheduler.assign(self.graph.nb_drones)
        self.drones = []
        for drone_id in range(1, self.graph.nb_drones + 1):
            path = list(paths[assignment[drone_id - 1]])
            self.drones.append(Drone(drone_id, self.graph.start, path))
        return paths

    # --------------------------------------------------------------- mainloop

    def run(self) -> List[TurnReport]:
        if not self.drones:
            self.prepare()
        self.turn_reports = []
        turn = 0
        while not self._all_delivered():
            turn += 1
            if turn > self.SAFETY_TURN_LIMIT:
                raise RuntimeError("deadlock: turn limit exceeded")
            report = self._execute_turn(turn)
            self.turn_reports.append(report)
        return self.turn_reports

    def _all_delivered(self) -> bool:
        return all(drone.delivered for drone in self.drones)

    # --------------------------------------------------------------- one turn

    def _execute_turn(self, turn: int) -> TurnReport:
        report = TurnReport(turn=turn)

        # Phase A — mandatory landings (restricted = 2-turn transit).
        just_landed: Set[int] = set()
        for drone in self.drones:
            if drone.delivered or not drone.is_in_transit:
                continue
            drone.finish_transit()
            if drone.position == self.graph.end:
                drone.delivered = True
            report.moves.append(MoveRecord(drone.label, drone.position.name))
            just_landed.add(drone.drone_id)

        # Phase B — greedy moves for the remaining drones.
        self._plan_moves(report, just_landed)
        return report

    def _plan_moves(self, report: TurnReport, just_landed: Set[int]) -> None:
        # Current zone occupancy before any move this turn (transit drones
        # occupy a connection, not a zone, so they are excluded).
        occupancy: Dict[str, int] = {}
        for drone in self.drones:
            if drone.delivered or drone.is_in_transit:
                continue
            occupancy[drone.position.name] = (
                occupancy.get(drone.position.name, 0) + 1
            )

        leaving: Dict[str, int] = {}
        arriving: Dict[str, int] = {}
        edge_use: Dict[Tuple[str, str], int] = {}

        for drone in sorted(self.drones, key=lambda d: d.drone_id):
            if drone.delivered or drone.is_in_transit:
                continue
            if drone.drone_id in just_landed:
                continue
            target = drone.next_zone()
            if target is None:
                continue

            connection = self.graph.get_connection(
                drone.position.name, target.name
            )
            ek = connection.endpoints
            if edge_use.get(ek, 0) + 1 > connection.max_link_capacity:
                continue  # connection saturated this turn → wait

            staying = occupancy.get(target.name, 0) - leaving.get(target.name, 0)
            free = target.zone_capacity() - staying - arriving.get(target.name, 0)
            if free <= 0:
                continue  # destination full → wait

            edge_use[ek] = edge_use.get(ek, 0) + 1
            leaving[drone.position.name] = leaving.get(drone.position.name, 0) + 1
            arriving[target.name] = arriving.get(target.name, 0) + 1

            if target.zone_type is ZoneType.RESTRICTED:
                drone.start_transit(connection, target)
                report.moves.append(
                    MoveRecord(drone.label, connection.display_name())
                )
            else:
                drone.step_to(target)
                if target == self.graph.end:
                    drone.delivered = True
                report.moves.append(MoveRecord(drone.label, target.name))

    # ---------------------------------------------------------------- stats

    def total_turns(self) -> int:
        return len(self.turn_reports)

    def total_path_cost(self) -> int:
        return sum(PathFinder.path_cost(d.path) for d in self.drones)

    def average_turns_per_drone(self) -> float:
        if not self.drones:
            return 0.0
        return self.total_path_cost() / len(self.drones)
