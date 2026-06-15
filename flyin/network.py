"""Network model: the data objects of the drone graph.

This module groups the small value-objects that describe the network:

* :class:`ZoneType` — kind of a zone (normal/restricted/priority/blocked).
* :class:`Zone`     — a node of the network.
* :class:`Connection` — an undirected edge linking two zones.

They live together because they form a single cohesive layer (the "model")
and depend on nothing else in the package.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ZoneType(Enum):
    """Type of a zone in the network.

    Movement costs:
        NORMAL    -> 1 turn
        RESTRICTED-> 2 turns (the drone occupies the connection during transit)
        PRIORITY  -> 1 turn, preferred by pathfinding
        BLOCKED   -> impassable
    """

    NORMAL = "normal"
    RESTRICTED = "restricted"
    PRIORITY = "priority"
    BLOCKED = "blocked"

    @classmethod
    def from_string(cls, value: str) -> "ZoneType":
        """Parse a zone-type name (case-insensitive) into a ``ZoneType``."""
        value = value.strip().lower()
        for element in ZoneType:
            if element.value == value:
                return element
        raise ValueError(f"unknown zone type: {value!r}")

    @property
    def move_cost(self) -> int:
        """Number of turns it takes to enter a zone of this type."""
        if self is ZoneType.RESTRICTED:
            return 2
        else:
            return 1


class Zone:
    """A single zone (node) in the drone network."""

    def __init__(
        self,
        name: str,
        x: int,
        y: int,
        zone_type: ZoneType = ZoneType.NORMAL,
        color: Optional[str] = None,
        max_drones: int = 1,
        is_start: bool = False,
        is_end: bool = False,
    ) -> None:
        self.name = name
        self.x: int = x
        self.y: int = y
        self.zone_type: ZoneType = zone_type
        self.color: Optional[str] = color
        self.max_drones: int = max_drones
        self.is_start: bool = is_start
        self.is_end: bool = is_end
        self.LARGE_VALUE = 10**9

    @property
    def is_passable(self) -> bool:
        """``True`` unless the zone is blocked (drones may not enter)."""
        if self.zone_type is not ZoneType.BLOCKED:
            return True
        else:
            return False

    @property
    def is_terminal(self) -> bool:
        """``True`` if this zone is the start or the end hub."""
        if self.is_start or self.is_end:
            return True
        return False

    def zone_capacity(self) -> int:
        """Max drones the zone can hold (unbounded for terminal hubs)."""
        if self.is_terminal:
            return self.LARGE_VALUE
        return self.max_drones

    def display(self) -> str:
        """Return a verbose human-readable representation of the zone."""
        return (
            f"Zone(name=<{self.name}>, x=<{self.x}>, y=<{self.y}>, "
            f"type=<{self.zone_type.value}>, max_drones=<{self.max_drones}>)"
        )

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        return self.name == other.name


class Connection:
    """An undirected connection (edge) linking two zones."""

    def __init__(
        self,
        zone_a: Zone,
        zone_b: Zone,
        max_link_capacity: int = 1,
    ) -> None:
        self.zone_a = zone_a
        self.zone_b = zone_b
        self.max_link_capacity = max_link_capacity

    @property
    def endpoints(self) -> tuple[str, str]:
        """Return the two zone names sorted alphabetically (canonical form)."""
        a, b = sorted((self.zone_a.name, self.zone_b.name))
        return (a, b)

    def other(self, zone: Zone) -> Zone:
        """Return the endpoint opposite to ``zone``.

        Raises ``ValueError`` if ``zone`` is not one of the two endpoints.
        """
        if zone == self.zone_a:
            return self.zone_b
        if zone == self.zone_b:
            return self.zone_a
        raise ValueError(
            f"zone {zone.name!r} is not an endpoint of {self.display_name()}"
        )

    def links(self, name_a: str, name_b: str) -> bool:
        """Return True if this connection links ``name_a``/``name_b``."""
        return self.endpoints == tuple(sorted((name_a, name_b)))

    def display_name(self) -> str:
        """Return a short ``zoneA-zoneB`` label for output and logs."""
        return f"{self.zone_a.name}-{self.zone_b.name}"

    def display(self) -> str:
        """Return a verbose representation including capacity."""
        return (
            f"Connection({self.zone_a}-{self.zone_b}, "
            f"cap={self.max_link_capacity})"
        )

    def __hash__(self) -> int:
        return hash(self.endpoints)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Connection):
            return False
        return self.endpoints == other.endpoints
