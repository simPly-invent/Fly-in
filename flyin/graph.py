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

    # ------------------------------------------------------------------ zones

    def add_zone(self, zone: Zone) -> None:
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
        if name in self._zones:
            return self._zones[name]
        raise KeyError(f"unknown zone: {name!r}")

    def has_zone(self, name: str) -> bool:
        return name in self._zones

    @property
    def zones(self) -> Iterable[Zone]:
        return self._zones.values()

    @property
    def start(self) -> Zone:
        if self._start is None:
            raise ValueError("graph has no start_hub")
        return self._start

    @property
    def end(self) -> Zone:
        if self._end is None:
            raise ValueError("graph has no end_hub")
        return self._end

    # ------------------------------------------------------------ connections

    def add_connection(self, connection: Connection) -> None:
        first, second = sorted((connection.zone_a.name, connection.zone_b.name))
        key = (first, second)
        if key in self._connections:
            raise ValueError("duplicate connection")
        self._connections[key] = connection
        self._adjacency[connection.zone_a.name].append(connection)
        self._adjacency[connection.zone_b.name].append(connection)

    def neighbors(self, zone_name: str) -> List[Tuple[Zone, Connection]]:
        zone = self.get_zone(zone_name)
        result: List[Tuple[Zone, Connection]] = []
        for connexion in self._adjacency.get(zone_name, []):
            opposite = connexion.other(zone)
            result.append((opposite, connexion))
        return result

    def get_connection(self, name_a: str, name_b: str) -> Connection:
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
        return self._connections.values()

    # ------------------------------------------------------------------ misc

    def validate(self) -> None:
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
