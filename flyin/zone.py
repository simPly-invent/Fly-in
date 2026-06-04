"""Zone module: represents a single node in the drone network."""

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
        """Parse a zone type from its textual representation.

        Args:
            value: textual zone type (case-insensitive).

        Returns:
            Matching ZoneType.

        Raises:
            ValueError: if the value does not match any zone type.
        """
        normalized = value.strip().lower()
        for zone_type in cls:
            if zone_type.value == normalized:
                return zone_type
        raise ValueError(f"unknown zone type: {value!r}")

    @property
    def move_cost(self) -> int:
        """Number of turns required to enter a zone of this type."""
        if self is ZoneType.RESTRICTED:
            return 2
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
        """Create a zone.

        Args:
            name: unique zone identifier.
            x: integer X coordinate.
            y: integer Y coordinate.
            zone_type: zone behavior.
            color: optional color metadata for visualization.
            max_drones: maximum drones allowed simultaneously (>=1).
            is_start: True if this is the start hub.
            is_end: True if this is the end hub.
        """
        self.name: str = name
        self.x: int = x
        self.y: int = y
        self.zone_type: ZoneType = zone_type
        self.color: Optional[str] = color
        self.max_drones: int = max_drones
        self.is_start: bool = is_start
        self.is_end: bool = is_end

    @property
    def is_passable(self) -> bool:
        """Return True if drones may traverse this zone."""
        return self.zone_type is not ZoneType.BLOCKED

    @property
    def is_terminal(self) -> bool:
        """Return True if this zone is the start or end hub.

        Terminal zones have unlimited capacity per the subject:
        all drones may share the start, and all drones may finish at the end.
        """
        return self.is_start or self.is_end

    def capacity_for_scheduling(self) -> int:
        """Effective capacity used by the simulator.

        Terminal zones are treated as infinite capacity.
        """
        if self.is_terminal:
            return 10 ** 9
        return self.max_drones

    def __repr__(self) -> str:
        return (
            f"Zone(name={self.name!r}, x={self.x}, y={self.y}, "
            f"type={self.zone_type.value}, max_drones={self.max_drones})"
        )

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        return self.name == other.name
