"""Drone module: tracks per-drone state during the simulation."""

from __future__ import annotations

from typing import List, Optional

from flyin.connection import Connection
from flyin.zone import Zone


class Drone:
    """A single drone navigating the network.

    A drone has a stable integer identifier (D1, D2, ...), a current zone,
    and an optional in-flight transit when crossing a restricted zone (which
    requires 2 turns: 1 spent on the connection, 1 to arrive).
    """

    def __init__(self, drone_id: int, start: Zone, path: Optional[List[Zone]] = None) -> None:
        """Create a drone parked at the start zone.

        Args:
            drone_id: 1-based unique identifier.
            start: the start zone where the drone begins.
            path: optional precomputed path of zones from start to end.
        """
        self.drone_id: int = drone_id
        self.position: Zone = start
        self.path: List[Zone] = path if path is not None else [start]
        self.path_index: int = 0
        self.transit_connection: Optional[Connection] = None
        self.transit_target: Optional[Zone] = None
        self.delivered: bool = False

    @property
    def label(self) -> str:
        """Drone identifier as used in the output (e.g., D1, D2)."""
        return f"D{self.drone_id}"

    @property
    def is_in_transit(self) -> bool:
        """True if the drone occupies a connection towards a restricted zone."""
        return self.transit_connection is not None

    def assign_path(self, path: List[Zone]) -> None:
        """Assign a freshly computed path to this drone."""
        if not path:
            raise ValueError("path must contain at least the start zone")
        self.path = path
        self.path_index = 0
        self.position = path[0]

    def next_zone(self) -> Optional[Zone]:
        """Return the next zone the drone should move to, or None at end."""
        if self.path_index + 1 >= len(self.path):
            return None
        return self.path[self.path_index + 1]

    def start_transit(self, connection: Connection, target: Zone) -> None:
        """Begin a 2-turn restricted-zone transit on this connection."""
        self.transit_connection = connection
        self.transit_target = target

    def finish_transit(self) -> None:
        """Complete a restricted-zone transit; arrive at the target zone."""
        if self.transit_target is None:
            raise RuntimeError("drone has no pending transit to finish")
        self.position = self.transit_target
        self.path_index += 1
        self.transit_connection = None
        self.transit_target = None

    def step_to(self, zone: Zone) -> None:
        """Execute a single-turn move to an adjacent zone."""
        self.position = zone
        self.path_index += 1

    def __repr__(self) -> str:
        if self.is_in_transit and self.transit_connection is not None:
            return (
                f"{self.label}@transit({self.transit_connection.display_name()})"
            )
        return f"{self.label}@{self.position.name}"
