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
        # - Stocker self.drone_id (int).
        # - self.position = start (Zone courante).
        # - self.path = path si fourni sinon [start].
        # - self.path_index = 0 (index dans self.path).
        # - self.transit_connection: Optional[Connection] = None.
        # - self.transit_target: Optional[Zone] = None.
        # - self.delivered: bool = False.
        raise NotImplementedError("À implémenter")

    @property
    def label(self) -> str:
        # - Retourner f"D{self.drone_id}" (format spec).
        raise NotImplementedError("À implémenter")

    @property
    def is_in_transit(self) -> bool:
        # - Retourner True si self.transit_connection est non-None.
        raise NotImplementedError("À implémenter")

    def assign_path(self, path: List[Zone]) -> None:
        # - Si path est vide → lever ValueError("path must contain at least the start").
        # - self.path = path.
        # - self.path_index = 0.
        # - self.position = path[0].
        raise NotImplementedError("À implémenter")

    def next_zone(self) -> Optional[Zone]:
        # - Si self.path_index + 1 >= len(self.path) → retourner None (fini).
        # - Sinon retourner self.path[self.path_index + 1].
        raise NotImplementedError("À implémenter")

    def start_transit(self, connection: Connection, target: Zone) -> None:
        # - self.transit_connection = connection.
        # - self.transit_target = target.
        # (Le drone occupe la connexion pendant 1 tour avant d'arriver.)
        raise NotImplementedError("À implémenter")

    def finish_transit(self) -> None:
        # - Si self.transit_target est None → RuntimeError("no pending transit").
        # - self.position = self.transit_target (arrivée à destination).
        # - self.path_index += 1.
        # - self.transit_connection = None ; self.transit_target = None.
        raise NotImplementedError("À implémenter")

    def step_to(self, zone: Zone) -> None:
        # - self.position = zone (move 1-tour vers une zone adjacente).
        # - self.path_index += 1.
        raise NotImplementedError("À implémenter")

    def __repr__(self) -> str:
        # - Si self.is_in_transit ET self.transit_connection non-None →
        #     retourner f"{self.label}@transit({self.transit_connection.display_name()})".
        # - Sinon retourner f"{self.label}@{self.position.name}".
        raise NotImplementedError("À implémenter")
