"""Pathfinding utilities.

The :class:`PathFinder` exposes a BFS adapted from a maze-solving BFS written
by the author in another project (FIFO queue + visited set + parent map +
reverse reconstruction). Instead of moving across a 2D grid with N/E/S/W
neighbours, we move across the zones of a :class:`flyin.graph.Graph` via its
connections, skipping blocked zones and optionally banned zones/edges so we
can mine several edge-disjoint paths in sequence for multi-drone routing.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from flyin.graph import Graph
from flyin.network import Zone, ZoneType


ConnectionKey = Tuple[str, str]


def _edge_key(a: str, b: str) -> ConnectionKey:
    """
    Return a canonical (sorted) key identifying the edge between ``a`` and ``b``.
    """
    first, second = sorted((a, b))
    return (first, second)


class PathFinder:
    """BFS-based pathfinder for the drone network."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    def bfs(
        self,
        source: Zone,
        target: Zone,
        banned_zones: Optional[Set[str]] = None,
        banned_edges: Optional[Set[ConnectionKey]] = None,
    ) -> Optional[List[Zone]]:
        """Find a shortest zone path from ``source`` to ``target`` via BFS.

        Blocked zones are always skipped; ``banned_zones`` and ``banned_edges``
        are additionally avoided (except the target itself). Returns the path as
        a list of zones, or ``None`` if no route exists.
        """
        banned_zones = banned_zones or set()
        banned_edges = banned_edges or set()

        if not source.is_passable or not target.is_passable:
            return None
        if source.name == target.name:
            return [source]

        visited: Set[str] = {source.name}
        parent: Dict[str, str] = {}
        queue: deque[str] = deque([source.name])

        while queue:
            current = queue.popleft()
            if current == target.name:
                break
            for neighbour, connection in self.graph.neighbors(current):
                name = neighbour.name
                if name in visited:
                    continue
                if not neighbour.is_passable:
                    continue
                if name in banned_zones and name != target.name:
                    continue
                if _edge_key(current, name) in banned_edges:
                    continue
                visited.add(name)
                parent[name] = current
                queue.append(name)

        if target.name not in visited:
            return None

        names: List[str] = []
        position = target.name
        while position in parent:
            names.append(position)
            position = parent[position]
        names.append(source.name)
        names.reverse()
        return [self.graph.get_zone(name) for name in names]

    def find_candidate_paths(self, max_paths: int) -> List[List[Zone]]:
        """Return up to ``max_paths`` distinct start-to-end paths, cheapest first.

        Mines edge-disjoint routes by repeatedly banning the edges already used,
        then adds detours that avoid each intermediate zone of the base path, so
        the scheduler has alternatives to spread drones across.
        """
        if max_paths <= 0:
            return []
        start = self.graph.start
        end = self.graph.end

        base = self.bfs(start, end)
        if base is None:
            return []

        pool: List[List[Zone]] = []
        seen: Set[Tuple[str, ...]] = set()

        def add(path: Optional[List[Zone]]) -> None:
            """Add ``path`` to the pool unless it is ``None`` or already seen."""
            if path is None:
                return
            key = tuple(zone.name for zone in path)
            if key in seen:
                return
            seen.add(key)
            pool.append(path)

        add(base)

        used_edges: Set[ConnectionKey] = set()
        for a, b in zip(base, base[1:]):
            used_edges.add(_edge_key(a.name, b.name))
        while True:
            extra = self.bfs(start, end, banned_edges=used_edges)
            if extra is None:
                break
            add(extra)
            for a, b in zip(extra, extra[1:]):
                used_edges.add(_edge_key(a.name, b.name))
        for zone in base[1:-1]:
            add(self.bfs(start, end, banned_zones={zone.name}))

        pool.sort(key=self._path_rank)
        return pool[:max_paths]

    @classmethod
    def _path_rank(cls, path: List[Zone]) -> Tuple[int, int]:
        """Rank a path: cheapest first, then most ``priority`` zones.

        The subject mandates that ``priority`` zones (same 1-turn cost as
        ``normal``) be *preferred*. We break cost ties toward the path that
        traverses the fewest non-priority zones, so an equally cheap route
        through priority zones wins.
        """
        non_priority = sum(
            1 for zone in path[1:] if zone.zone_type is not ZoneType.PRIORITY
        )
        return (cls.path_cost(path), non_priority)

    @staticmethod
    def path_cost(path: List[Zone]) -> int:
        """Return the total move cost of a path (sum of entered zones' costs)."""
        return sum(zone.zone_type.move_cost for zone in path[1:])
