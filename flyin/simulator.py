"""Drone simulation engine.

Combines a simple multi-path *scheduler* (which decides which precomputed
path each drone follows) with a turn-by-turn *simulator* (which respects
zone capacities, connection capacities, and the 2-turn transit rule for
restricted zones).

The simulator emits one :class:`TurnReport` per turn so the visualization
layer can render coloured terminal output while staying decoupled from the
movement logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from flyin.connection import Connection
from flyin.drone import Drone
from flyin.graph import Graph
from flyin.pathfinder import PathFinder
from flyin.zone import Zone, ZoneType


@dataclass
class MoveRecord:
    """One drone's movement event for a single turn."""

    drone_label: str
    destination: str  # zone name (arrival) or connection display name (transit)

    def render(self) -> str:
        """Format the move as ``D<id>-<destination>`` (spec output)."""
        return f"{self.drone_label}-{self.destination}"


@dataclass
class TurnReport:
    """Snapshot of moves performed during a single simulation turn."""

    turn: int
    moves: List[MoveRecord] = field(default_factory=list)

    def render(self) -> str:
        """Spec-compliant output: moves space-separated, one line per turn."""
        return " ".join(move.render() for move in self.moves)


class PathScheduler:
    """Assign drones to candidate paths to minimize makespan.

    Greedy heuristic: each drone is placed on the path that yields the
    smallest projected completion turn, considering both the path cost
    (sum of zone movement costs) and the number of drones already routed
    on that path (which queue at one drone per turn at the tightest
    bottleneck).
    """

    def __init__(self, paths: List[List[Zone]]) -> None:
        if not paths:
            raise ValueError("scheduler needs at least one path")
        self.paths: List[List[Zone]] = paths

    def assign(self, nb_drones: int) -> List[int]:
        """Return a list of length ``nb_drones`` mapping drone -> path index."""
        costs = [PathFinder.path_cost(p) for p in self.paths]
        counts = [0] * len(self.paths)
        assignment: List[int] = []
        for _ in range(nb_drones):
            best = 0
            best_finish = costs[0] + counts[0]
            for i in range(1, len(self.paths)):
                finish = costs[i] + counts[i]
                if finish < best_finish:
                    best_finish = finish
                    best = i
            assignment.append(best)
            counts[best] += 1
        return assignment


class Simulator:
    """Turn-by-turn drone simulation respecting all subject constraints."""

    SAFETY_TURN_LIMIT = 10_000

    def __init__(self, graph: Graph) -> None:
        self.graph: Graph = graph
        self.drones: List[Drone] = []
        self.turn_reports: List[TurnReport] = []

    # ----------------------------------------------------------------- setup

    def prepare(self) -> List[List[Zone]]:
        """Compute candidate paths and assign drones to them.

        Returns the list of paths used (for documentation / display).
        """
        finder = PathFinder(self.graph)
        budget = min(self.graph.nb_drones, 16)
        paths = finder.find_k_shortest_paths(budget)
        if not paths:
            raise RuntimeError("no path from start to end exists")
        scheduler = PathScheduler(paths)
        assignment = scheduler.assign(self.graph.nb_drones)

        self.drones = []
        start = self.graph.start
        for drone_id in range(1, self.graph.nb_drones + 1):
            path_index = assignment[drone_id - 1]
            drone = Drone(drone_id, start, list(paths[path_index]))
            self.drones.append(drone)
        return paths

    # --------------------------------------------------------------- mainloop

    def run(self) -> List[TurnReport]:
        """Run the simulation to completion and return per-turn reports."""
        if not self.drones:
            self.prepare()
        self.turn_reports = []

        turn = 0
        while not self._all_delivered():
            turn += 1
            if turn > self.SAFETY_TURN_LIMIT:
                raise RuntimeError(
                    f"simulation exceeded {self.SAFETY_TURN_LIMIT} turns; "
                    "the algorithm is likely deadlocked"
                )
            report = self._execute_turn(turn)
            self.turn_reports.append(report)
        return self.turn_reports

    # --------------------------------------------------------------- helpers

    def _all_delivered(self) -> bool:
        return all(drone.delivered for drone in self.drones)

    def _execute_turn(self, turn: int) -> TurnReport:
        """Compute and apply moves for one simulation turn.

        Strategy (multi-pass to handle chain-following correctly):
            Phase A: drones currently mid-transit (restricted zones) MUST
                     arrive at their destination this turn.
            Phase B: every other drone proposes a one-step move; we iterate
                     until no additional drone can be confirmed in this turn.
                     A drone is confirmed when its destination zone and the
                     connection still have spare capacity, accounting for
                     drones already confirmed leaving the source zone and
                     drones already confirmed arriving at the destination.
        """
        report = TurnReport(turn=turn)

        # Snapshot zone occupancy *before* any moves this turn (drones in
        # transit do NOT count against zone capacity).
        zone_load: Dict[str, int] = {}
        for drone in self.drones:
            if drone.delivered or drone.is_in_transit:
                continue
            zone_load[drone.position.name] = (
                zone_load.get(drone.position.name, 0) + 1
            )

        zone_arrivals: Dict[str, int] = {}
        connection_usage: Dict[Tuple[str, str], int] = {}
        # Track drones currently flying towards a restricted destination so
        # we never start a transit that would over-fill the target on arrival.
        pending_landings: Dict[str, int] = {}
        for drone in self.drones:
            if drone.is_in_transit and drone.transit_target is not None:
                pending_landings[drone.transit_target.name] = (
                    pending_landings.get(drone.transit_target.name, 0) + 1
                )

        # --------------------------------------------------- Phase A: landings
        # Each drone may perform at most one move per turn. Drones that land
        # this turn cannot also step in Phase B.
        just_landed: set[int] = set()
        for drone in self.drones:
            if drone.delivered or not drone.is_in_transit:
                continue
            target = drone.transit_target
            assert target is not None
            arrivals = zone_arrivals.get(target.name, 0)
            if arrivals + 1 > target.capacity_for_scheduling():
                raise RuntimeError(
                    f"drone {drone.label} cannot land on {target.name!r}: "
                    "destination is over capacity (scheduler bug)"
                )
            zone_arrivals[target.name] = arrivals + 1
            pending_landings[target.name] = pending_landings.get(target.name, 0) - 1
            drone.finish_transit()
            just_landed.add(drone.drone_id)
            if drone.position is self.graph.end:
                drone.delivered = True
            report.moves.append(MoveRecord(drone.label, drone.position.name))

        # ----------------------------------------- Phase B: collect intents
        # Each non-delivered, non-transiting, non-just-landed drone proposes
        # at most one move. We then solve all intents together so swaps
        # (D7<->D10 between two cap-1 zones) and chain-following both resolve.
        intents: Dict[Drone, Tuple[Zone, Connection, str]] = {}
        for drone in self.drones:
            if drone.delivered or drone.is_in_transit:
                continue
            if drone.drone_id in just_landed:
                continue
            next_zone = drone.next_zone()
            if next_zone is None:
                if drone.position is self.graph.end:
                    drone.delivered = True
                continue
            connection = self.graph.get_connection(
                drone.position.name, next_zone.name
            )
            kind = (
                "transit"
                if next_zone.zone_type is ZoneType.RESTRICTED
                else "step"
            )
            intents[drone] = (next_zone, connection, kind)

        active = dict(intents)
        self._prune_until_feasible(
            active, zone_load, zone_arrivals, connection_usage, pending_landings
        )
        self._commit_intents(active, report)

        return report

    # ------------------------------------------------- intent resolution

    def _prune_until_feasible(
        self,
        active: Dict[Drone, Tuple[Zone, Connection, str]],
        zone_load: Dict[str, int],
        zone_arrivals: Dict[str, int],
        connection_usage: Dict[Tuple[str, str], int],
        pending_landings: Dict[str, int],
    ) -> None:
        """Drop intents (lowest priority first) until all constraints hold."""
        while active:
            violator = self._find_violator(
                active,
                zone_load,
                zone_arrivals,
                connection_usage,
                pending_landings,
            )
            if violator is None:
                return
            del active[violator]

    def _find_violator(
        self,
        active: Dict[Drone, Tuple[Zone, Connection, str]],
        zone_load: Dict[str, int],
        zone_arrivals: Dict[str, int],
        connection_usage: Dict[Tuple[str, str], int],
        pending_landings: Dict[str, int],
    ) -> Optional[Drone]:
        """Return a drone to drop, or None if all constraints are satisfied.

        Among offenders we prefer to drop drones whose departure does NOT
        free any tight capacity (e.g., drones still at the start hub or in
        a zone that's well under its cap). Keeping the "capacity-relievers"
        is what allows swaps (D7@gate2 <-> D10@gate3 with cap=1) to resolve.
        Tie-breaker: drop the drone with the highest id.
        """
        leaving: Dict[str, int] = {}
        entering: Dict[str, int] = {}
        edge_usage: Dict[Tuple[str, str], int] = {}
        new_landings: Dict[str, int] = {}

        for drone, (target, conn, kind) in active.items():
            leaving[drone.position.name] = leaving.get(drone.position.name, 0) + 1
            edge_usage[conn.endpoints] = edge_usage.get(conn.endpoints, 0) + 1
            if kind == "step":
                entering[target.name] = entering.get(target.name, 0) + 1
            else:
                new_landings[target.name] = new_landings.get(target.name, 0) + 1

        for conn in self.graph.connections:
            usage = (
                connection_usage.get(conn.endpoints, 0)
                + edge_usage.get(conn.endpoints, 0)
            )
            if usage > conn.max_link_capacity:
                offenders = [
                    d for d, (_, c, _) in active.items()
                    if c.endpoints == conn.endpoints
                ]
                if offenders:
                    return self._pick_drop(offenders, zone_load)

        for zone in self.graph.zones:
            load = zone_load.get(zone.name, 0)
            net = (
                load
                + zone_arrivals.get(zone.name, 0)
                + entering.get(zone.name, 0)
                - leaving.get(zone.name, 0)
            )
            if net > zone.capacity_for_scheduling():
                offenders = [
                    d for d, (target, _, kind) in active.items()
                    if kind == "step" and target.name == zone.name
                ]
                if offenders:
                    return self._pick_drop(offenders, zone_load)

        for zone in self.graph.zones:
            future = (
                pending_landings.get(zone.name, 0)
                + new_landings.get(zone.name, 0)
            )
            if future > zone.capacity_for_scheduling():
                offenders = [
                    d for d, (target, _, kind) in active.items()
                    if kind == "transit" and target.name == zone.name
                ]
                if offenders:
                    return self._pick_drop(offenders, zone_load)

        return None

    @staticmethod
    def _pick_drop(
        offenders: List[Drone], zone_load: Dict[str, int]
    ) -> Drone:
        """Pick which offender to drop from a violating constraint.

        Heuristic: prefer dropping drones whose source zone has plenty of
        spare capacity (terminal zones, lightly-used hubs). Drones leaving
        a fully-saturated zone are kept because their departure unlocks
        another drone's arrival. Ties broken by largest drone id.
        """
        def slack(drone: Drone) -> int:
            cap = drone.position.capacity_for_scheduling()
            load = zone_load.get(drone.position.name, 0)
            # Big slack = "useless" departure for chain resolution.
            return cap - load

        return max(offenders, key=lambda d: (slack(d), d.drone_id))

    def _commit_intents(
        self,
        active: Dict[Drone, Tuple[Zone, Connection, str]],
        report: TurnReport,
    ) -> None:
        """Apply all admitted intents and append output records."""
        for drone in sorted(active, key=lambda d: d.drone_id):
            target, connection, kind = active[drone]
            if kind == "transit":
                drone.start_transit(connection, target)
                report.moves.append(
                    MoveRecord(drone.label, connection.display_name())
                )
            else:
                drone.step_to(target)
                if target is self.graph.end:
                    drone.delivered = True
                report.moves.append(MoveRecord(drone.label, target.name))

    # ---------------------------------------------------------------- stats

    def total_turns(self) -> int:
        """Total simulation turns (== final turn number, 0 if nothing ran)."""
        return len(self.turn_reports)

    def total_path_cost(self) -> int:
        """Sum of per-drone path costs (secondary metric mentioned in spec)."""
        return sum(PathFinder.path_cost(d.path) for d in self.drones)

    def average_turns_per_drone(self) -> float:
        """Average turns per drone (secondary metric)."""
        if not self.drones:
            return 0.0
        return self.total_path_cost() / len(self.drones)
