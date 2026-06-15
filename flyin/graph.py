"""Graph module: holds zones, connections, and adjacency helpers."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from flyin.network import Connection, Zone


class Graph:
    """A drone network graph.

    Stores zones by name and connections by sorted-endpoint tuple, plus a
    pre-computed adjacency map for fast neighbor lookups.
    """

    def __init__(self, nb_drones: int) -> None:
        if nb_drones <= 0:
            raise ValueError("nb_drones must be positive")
        self.nb_drones: int = nb_drones
        self._zones: Dict[str, Zone] = {}
        self._connections: Dict[Tuple[str, str], Connection] = {}
        self._adjacency: Dict[str, List[Connection]] = {}
        self._start: Optional[Zone] = None
        self._end: Optional[Zone] = None

    def add_zone(self, zone: Zone) -> None:
        """Register a zone, track start/end hubs, reject duplicates."""
        if zone.name in self._zones:
            raise ValueError("error: duplicate value")
        if zone.is_start:
            if self._start is not None:
                raise ValueError("multiple start_hub")
            self._start = zone
        if zone.is_end:
            if self._end is not None:
                raise ValueError("multiple end_hub")
            self._end = zone
        self._zones[zone.name] = zone
        self._adjacency[zone.name] = []

    def get_zone(self, name: str) -> Zone:
        """Return the zone named ``name`` or raise ``KeyError`` if unknown."""
        if name in self._zones:
            return self._zones[name]
        raise KeyError(f"unknown zone: {name!r}")

    def has_zone(self, name: str) -> bool:
        """Return ``True`` if a zone named ``name`` is registered."""
        return name in self._zones

    @property
    def zones(self) -> Iterable[Zone]:
        """All registered zones."""
        return self._zones.values()

    @property
    def start(self) -> Zone:
        """The start hub, or raise ``ValueError`` if none was declared."""
        if self._start is None:
            raise ValueError("graph has no start_hub")
        return self._start

    @property
    def end(self) -> Zone:
        """The end hub, or raise ``ValueError`` if none was declared."""
        if self._end is None:
            raise ValueError("graph has no end_hub")
        return self._end

    def add_connection(self, connection: Connection) -> None:
        """Register an edge, update adjacency, reject duplicate edges."""
        first, second = sorted(
            (connection.zone_a.name, connection.zone_b.name)
        )
        key = (first, second)
        if key in self._connections:
            raise ValueError("duplicate connection")
        self._connections[key] = connection
        self._adjacency[connection.zone_a.name].append(connection)
        self._adjacency[connection.zone_b.name].append(connection)

    def neighbors(self, zone_name: str) -> List[Tuple[Zone, Connection]]:
        """Return the ``(zone, connection)`` pairs adjacent to a zone."""
        zone = self.get_zone(zone_name)
        result: List[Tuple[Zone, Connection]] = []
        for connexion in self._adjacency.get(zone_name, []):
            opposite = connexion.other(zone)
            result.append((opposite, connexion))
        return result

    def get_connection(self, name_a: str, name_b: str) -> Connection:
        """Return the connection between two zones or raise ``KeyError``."""
        first, second = sorted((name_a, name_b))
        key = (first, second)
        try:
            return self._connections[key]
        except KeyError as exc:
            raise KeyError(
                f"no connection between {name_a!r} and {name_b!r}"
            ) from exc

    @property
    def connections(self) -> Iterable[Connection]:
        """All registered connections."""
        return self._connections.values()

    def validate(self) -> None:
        """Check start and end hubs exist and are passable, else raise."""
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
            f"Graph(nb_drones={self.nb_drones}, zones={len(self._zones)}, "
            f"connections={len(self._connections)})"
        )
