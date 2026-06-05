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
        # - Si nb_drones <= 0 → lever ValueError("nb_drones must be positive").
        # - Initialiser:
        #     self.nb_drones (int)
        #     self._zones: Dict[str, Zone] = {}
        #     self._connections: Dict[Tuple[str, str], Connection] = {}
        #     self._adjacency: Dict[str, List[Connection]] = {}
        #     self._start: Optional[Zone] = None
        #     self._end: Optional[Zone] = None
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------------------------ zones

    def add_zone(self, zone: Zone) -> None:
        # - Si zone.name est déjà dans self._zones → ValueError("duplicate zone").
        # - Si zone.is_start:
        #     - Si self._start déjà défini → ValueError("multiple start_hub").
        #     - Sinon self._start = zone.
        # - Idem pour zone.is_end avec self._end.
        # - Ajouter zone dans self._zones[zone.name].
        # - Initialiser self._adjacency[zone.name] = [].
        raise NotImplementedError("À implémenter")

    def get_zone(self, name: str) -> Zone:
        # - Retourner self._zones[name].
        # - Sur KeyError → lever KeyError(f"unknown zone: {name!r}") (chaîné).
        raise NotImplementedError("À implémenter")

    def has_zone(self, name: str) -> bool:
        # - Retourner name in self._zones.
        raise NotImplementedError("À implémenter")

    @property
    def zones(self) -> Iterable[Zone]:
        # - Retourner self._zones.values() (itérable des zones).
        raise NotImplementedError("À implémenter")

    @property
    def start(self) -> Zone:
        # - Si self._start est None → ValueError("graph has no start_hub").
        # - Sinon retourner self._start.
        raise NotImplementedError("À implémenter")

    @property
    def end(self) -> Zone:
        # - Si self._end est None → ValueError("graph has no end_hub").
        # - Sinon retourner self._end.
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------------------ connections

    def add_connection(self, connection: Connection) -> None:
        # - key = connection.endpoints (tuple trié des noms).
        # - Si key déjà dans self._connections → ValueError("duplicate connection").
        # - Stocker dans self._connections[key] = connection.
        # - Append la connexion dans self._adjacency[zone_a.name] ET [zone_b.name].
        raise NotImplementedError("À implémenter")

    def neighbors(self, zone_name: str) -> List[Tuple[Zone, Connection]]:
        # - zone = self.get_zone(zone_name).
        # - Pour chaque connexion dans self._adjacency.get(zone_name, []):
        #     - other = connexion.other(zone).
        #     - Ajouter (other, connexion) au résultat.
        # - Retourner la liste.
        raise NotImplementedError("À implémenter")

    def get_connection(self, name_a: str, name_b: str) -> Connection:
        # - key = tuple(sorted((name_a, name_b))).
        # - Retourner self._connections[key].
        # - Sur KeyError → lever KeyError(f"no connection between ..."). (chaîné)
        raise NotImplementedError("À implémenter")

    @property
    def connections(self) -> Iterable[Connection]:
        # - Retourner self._connections.values().
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------------------------ misc

    def validate(self) -> None:
        # - Si self._start est None → ValueError("no start_hub declared").
        # - Si self._end est None → ValueError("no end_hub declared").
        # - Si not self._start.is_passable → ValueError("start_hub cannot be blocked").
        # - Si not self._end.is_passable → ValueError("end_hub cannot be blocked").
        raise NotImplementedError("À implémenter")

    def __repr__(self) -> str:
        # - Retourner f"Graph(nb_drones={self.nb_drones}, zones={len(self._zones)}, "
        #             f"connections={len(self._connections)})".
        raise NotImplementedError("À implémenter")
