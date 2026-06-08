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
from flyin.network import Zone


# A connection key (sorted endpoint names) — used to forbid specific edges.
ConnectionKey = Tuple[str, str]


def _edge_key(a: str, b: str) -> ConnectionKey:
    first, second = sorted((a, b))
    return (first, second)


class PathFinder:
    """BFS-based pathfinder for the drone network."""

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

    # ----------------------------------------------------------------- BFS API

    def bfs(
        self,
        source: Zone,
        target: Zone,
        banned_zones: Optional[Set[str]] = None,
        banned_edges: Optional[Set[ConnectionKey]] = None,
    ) -> Optional[List[Zone]]:
        # Same structure as the maze-solver BFS, transposed onto the graph:
        # explore neighbours via graph.neighbors(...) instead of N/E/S/W.
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
        # Build a diverse pool of routes the scheduler can spread drones over.
        # Two complementary BFS-based passes feed the pool:
        #   * edge-disjoint paths — great when the graph has truly parallel
        #     routes (each drone gets its own corridor);
        #   * node-spur paths — bans one intermediate zone of the shortest path
        #     at a time, which surfaces alternatives that legitimately SHARE a
        #     high-capacity bottleneck edge (e.g. a final merge->goal link).
        # The simulator's per-turn capacity rules then resolve any congestion.
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
            if path is None:
                return
            key = tuple(zone.name for zone in path)
            if key in seen:
                return
            seen.add(key)
            pool.append(path)

        add(base)

        # Pass 1 — edge-disjoint routes.
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

        pool.sort(key=self.path_cost)
        return pool[:max_paths]

    # ------------------------------------------------------------------ utils

    @staticmethod
    def path_cost(path: List[Zone]) -> int:
        # The first zone (the start) has no entry cost.
        return sum(zone.zone_type.move_cost for zone in path[1:])
