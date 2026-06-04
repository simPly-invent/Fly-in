"""Connection module: undirected edge between two zones."""

from __future__ import annotations

from typing import Tuple

from flyin.zone import Zone


class Connection:
    """An undirected connection (edge) linking two zones."""

    def __init__(
        self,
        zone_a: Zone,
        zone_b: Zone,
        max_link_capacity: int = 1,
    ) -> None:
        """Create a connection.

        Args:
            zone_a: first endpoint.
            zone_b: second endpoint.
            max_link_capacity: maximum drones traversing simultaneously.
        """
        self.zone_a: Zone = zone_a
        self.zone_b: Zone = zone_b
        self.max_link_capacity: int = max_link_capacity

    @property
    def endpoints(self) -> Tuple[str, str]:
        """Sorted tuple of endpoint names; used for de-duplication."""
        return tuple(sorted((self.zone_a.name, self.zone_b.name)))  # type: ignore[return-value]

    def other(self, zone: Zone) -> Zone:
        """Return the zone on the opposite end of this connection."""
        if zone is self.zone_a or zone.name == self.zone_a.name:
            return self.zone_b
        if zone is self.zone_b or zone.name == self.zone_b.name:
            return self.zone_a
        raise ValueError(
            f"zone {zone.name!r} is not an endpoint of connection "
            f"{self.zone_a.name}-{self.zone_b.name}"
        )

    def connects(self, name_a: str, name_b: str) -> bool:
        """Return True if this connection links the two given zone names."""
        return self.endpoints == tuple(sorted((name_a, name_b)))

    def display_name(self) -> str:
        """Human-readable connection label used in the simulation output."""
        return f"{self.zone_a.name}-{self.zone_b.name}"

    def __repr__(self) -> str:
        return (
            f"Connection({self.zone_a.name}-{self.zone_b.name}, "
            f"cap={self.max_link_capacity})"
        )

    def __hash__(self) -> int:
        return hash(self.endpoints)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Connection):
            return NotImplemented
        return self.endpoints == other.endpoints
