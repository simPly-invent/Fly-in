"""Graph module: holds zones, connections, and adjacency helpers."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from flyin.connection import Connection
from flyin.zone import Zone


class Graph:
    """A drone network graph.

    Stores zones by name and connections by sorted-endpoint tuple, plus a
    pre-computed adjacency map for fast neighbor lookups.
    """

    def __init__(self, nb_drones: int) -> None:
        """Create an empty graph.

        Args:
            nb_drones: total number of drones to route through the graph.
        """
        if nb_drones <= 0:
            raise ValueError("nb_drones must be a positive integer")
        self.nb_drones: int = nb_drones
        self._zones: Dict[str, Zone] = {}
        self._connections: Dict[Tuple[str, str], Connection] = {}
        self._adjacency: Dict[str, List[Connection]] = {}
        self._start: Optional[Zone] = None
        self._end: Optional[Zone] = None

    # ------------------------------------------------------------------ zones

    def add_zone(self, zone: Zone) -> None:
        """Add a zone to the graph.

        Raises:
            ValueError: if a zone with the same name already exists, or if
                more than one start/end zone is declared.
        """
        if zone.name in self._zones:
            raise ValueError(f"duplicate zone name: {zone.name!r}")
        if zone.is_start:
            if self._start is not None:
                raise ValueError("multiple start_hub zones declared")
            self._start = zone
        if zone.is_end:
            if self._end is not None:
                raise ValueError("multiple end_hub zones declared")
            self._end = zone
        self._zones[zone.name] = zone
        self._adjacency[zone.name] = []

    def get_zone(self, name: str) -> Zone:
        """Return the zone with the given name."""
        try:
            return self._zones[name]
        except KeyError as exc:
            raise KeyError(f"unknown zone: {name!r}") from exc

    def has_zone(self, name: str) -> bool:
        """Return True if a zone with this name exists."""
        return name in self._zones

    @property
    def zones(self) -> Iterable[Zone]:
        """Iterate over all zones."""
        return self._zones.values()

    @property
    def start(self) -> Zone:
        """Return the start zone."""
        if self._start is None:
            raise ValueError("graph has no start_hub")
        return self._start

    @property
    def end(self) -> Zone:
        """Return the end zone."""
        if self._end is None:
            raise ValueError("graph has no end_hub")
        return self._end

    # ------------------------------------------------------------ connections

    def add_connection(self, connection: Connection) -> None:
        """Add an undirected connection.

        Raises:
            ValueError: if a connection between the same endpoints already
                exists (in either direction).
        """
        key = connection.endpoints
        if key in self._connections:
            raise ValueError(
                f"duplicate connection: {connection.zone_a.name}-"
                f"{connection.zone_b.name}"
            )
        self._connections[key] = connection
        self._adjacency[connection.zone_a.name].append(connection)
        self._adjacency[connection.zone_b.name].append(connection)

    def neighbors(self, zone_name: str) -> List[Tuple[Zone, Connection]]:
        """Return list of (neighbor zone, connection) pairs for a zone."""
        zone = self.get_zone(zone_name)
        result: List[Tuple[Zone, Connection]] = []
        for conn in self._adjacency.get(zone_name, []):
            other = conn.other(zone)
            result.append((other, conn))
        return result

    def get_connection(self, name_a: str, name_b: str) -> Connection:
        """Return the connection between the two zones (order-insensitive)."""
        key = tuple(sorted((name_a, name_b)))
        try:
            return self._connections[key]  # type: ignore[index]
        except KeyError as exc:
            raise KeyError(
                f"no connection between {name_a!r} and {name_b!r}"
            ) from exc

    @property
    def connections(self) -> Iterable[Connection]:
        """Iterate over all connections."""
        return self._connections.values()

    # ------------------------------------------------------------------ misc

    def validate(self) -> None:
        """Sanity-check the graph after parsing.

        Raises:
            ValueError: if start or end is missing, or start/end are blocked.
        """
        if self._start is None:
            raise ValueError("no start_hub declared")
        if self._end is None:
            raise ValueError("no end_hub declared")
        if not self._start.is_passable:
            raise ValueError("start_hub cannot be blocked")
        if not self._end.is_passable:
            raise ValueError("end_hub cannot be blocked")

    def __repr__(self) -> str:
        return (
            f"Graph(nb_drones={self.nb_drones}, "
            f"zones={len(self._zones)}, "
            f"connections={len(self._connections)})"
        )
