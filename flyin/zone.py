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
        value = value.strip().lower()
        for element in ZoneType:
            if element.value == value:
                return element
        raise ValueError(f"unknown zone type: {value!r}")

    @property
    def move_cost(self) -> int:
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
        if self.zone_type is not ZoneType.BLOCKED:
            return True
        else:
            return False

    @property
    def is_terminal(self) -> bool:
        if self.is_start or self.is_end:
            return True
        return False

    def zone_capacity(self) -> int:
        if self.is_terminal:
            return self.LARGE_VALUE
        return self.max_drones

    def display(self) -> str:
        return(f"Zone(name=<{self.name}>, x=<{self.x}>, y=<{self.y}>, "
               f"type=<{self.zone_type.value}>, max_drones=<{self.max_drones}>)")

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if(not isinstance(other, Zone)):
            return NotImplemented
        return self.name == other.name




if __name__ == "__main__":
    test = ZoneType("normal")
    test.from_string("normal")