"""Connection module: undirected edge between two zones."""

from __future__ import annotations

from flyin.zone import Zone


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
        """Return True if this connection links the two zones named ``name_a`` and ``name_b``."""
        return self.endpoints == tuple(sorted((name_a, name_b)))

    def display_name(self) -> str:
        """Return a short ``zoneA-zoneB`` label for output and logs."""
        return f"{self.zone_a.name}-{self.zone_b.name}"

    def display(self) -> str:
        """Return a verbose human-readable representation including capacity."""
        return f"Connection({self.zone_a}-{self.zone_b}, cap={self.max_link_capacity})"

    def __hash__(self) -> int:
        return hash(self.endpoints)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Connection):
            return False
        return self.endpoints == other.endpoints
