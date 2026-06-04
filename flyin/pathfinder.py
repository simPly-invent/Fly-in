"""Pathfinding utilities.

The :class:`PathFinder` exposes a BFS adapted from a maze-solving BFS
(FIFO queue + parent map + reverse reconstruction). Instead of moving across
a 2D grid with N/E/S/W neighbours, we move across the zones of a
:class:`flyin.graph.Graph` via its connections, skipping blocked zones and
optionally banned zones/edges so we can mine several edge-disjoint paths in
sequence for multi-drone routing.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from flyin.graph import Graph
from flyin.zone import Zone


# A connection key (sorted endpoint names) — used to forbid specific edges.
ConnectionKey = Tuple[str, str]


def _edge_key(a: str, b: str) -> ConnectionKey:
    """Return the canonical key for an undirected edge."""
    return tuple(sorted((a, b)))  # type: ignore[return-value]


class PathFinder:
    """BFS-based pathfinder for the drone network."""

    def __init__(self, graph: Graph) -> None:
        self.graph: Graph = graph

    # ----------------------------------------------------------------- BFS API

    def bfs(
        self,
        source: Zone,
        target: Zone,
        banned_zones: Optional[Set[str]] = None,
        banned_edges: Optional[Set[ConnectionKey]] = None,
    ) -> Optional[List[Zone]]:
        """Find the shortest-hop path from ``source`` to ``target``.

        FIFO breadth-first search over zones:
            1. Start from ``source`` and mark it visited.
            2. Explore all passable neighbours (skip blocked / banned).
            3. Record each zone's parent to allow path reconstruction.
            4. Stop as soon as ``target`` is dequeued.
            5. Walk back through the parent map to build the final path.

        BFS guarantees the path with the fewest hops; restricted-zone
        movement cost (2 turns) is accounted for later by the simulator.

        Args:
            source: starting zone.
            target: destination zone.
            banned_zones: zone names that must not be traversed (except the
                source and target themselves, which are always allowed).
            banned_edges: canonical edge keys (sorted endpoint names) that
                must not be used.

        Returns:
            Ordered list of zones from ``source`` to ``target`` inclusive, or
            ``None`` if no path exists.
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
            current_name = queue.popleft()

            if current_name == target.name:
                break

            for neighbour, connection in self.graph.neighbors(current_name):
                if neighbour.name in visited:
                    continue
                if not neighbour.is_passable:
                    continue
                if (
                    neighbour.name in banned_zones
                    and neighbour.name != target.name
                ):
                    continue
                edge = _edge_key(current_name, neighbour.name)
                if edge in banned_edges:
                    continue

                visited.add(neighbour.name)
                parent[neighbour.name] = current_name
                queue.append(neighbour.name)

        if target.name not in visited:
            return None

        path_names: List[str] = [target.name]
        cursor = target.name
        while cursor in parent:
            cursor = parent[cursor]
            path_names.append(cursor)
        path_names.reverse()
        return [self.graph.get_zone(name) for name in path_names]

    def find_disjoint_paths(self, max_paths: int) -> List[List[Zone]]:
        """Find up to ``max_paths`` edge-disjoint paths from start to end.

        Iteratively runs BFS, banning the edges of each accepted path so the
        next search must take a different route. Shared intermediate zones
        remain allowed — capacity conflicts on those zones are resolved later
        by the simulator using ``max_drones``.

        Args:
            max_paths: hard cap on the number of paths to return (we never
                want more paths than we have drones to spread).

        Returns:
            A list of paths (each a list of zones), sorted by ascending
            turn-cost so the simulator prefers the fastest routes first.
        """
        if max_paths <= 0:
            return []
        start = self.graph.start
        end = self.graph.end

        paths: List[List[Zone]] = []
        used_edges: Set[ConnectionKey] = set()

        for _ in range(max_paths):
            path = self.bfs(start, end, banned_edges=used_edges)
            if path is None:
                break
            paths.append(path)
            for hop_a, hop_b in zip(path, path[1:]):
                used_edges.add(_edge_key(hop_a.name, hop_b.name))

        if not paths:
            fallback = self.bfs(start, end)
            if fallback is not None:
                paths.append(fallback)

        paths.sort(key=self.path_cost)
        return paths

    def find_k_shortest_paths(self, k: int) -> List[List[Zone]]:
        """Find up to ``k`` simple paths from start to end, shortest first.

        Yen-style algorithm built on top of :meth:`bfs`: starts from the
        shortest path, then for each "spur node" along an accepted path it
        searches for alternatives that share a prefix but diverge from it.
        Unlike :meth:`find_disjoint_paths`, the returned paths may share
        edges and intermediate zones — useful when the graph has a forced
        trunk (e.g., a single start exit) followed by a fork.
        """
        if k <= 0:
            return []
        start = self.graph.start
        end = self.graph.end

        first = self.bfs(start, end)
        if first is None:
            return []
        accepted: List[List[Zone]] = [first]
        candidates: List[List[Zone]] = []
        seen: Set[Tuple[str, ...]] = {tuple(z.name for z in first)}

        while len(accepted) < k:
            previous = accepted[-1]
            for spur_index in range(len(previous) - 1):
                root_path = previous[: spur_index + 1]
                root_names = {z.name for z in root_path[:-1]}
                banned_edges: Set[ConnectionKey] = set()
                for path in accepted:
                    if (
                        len(path) > spur_index + 1
                        and [z.name for z in path[: spur_index + 1]]
                        == [z.name for z in root_path]
                    ):
                        banned_edges.add(
                            _edge_key(
                                path[spur_index].name,
                                path[spur_index + 1].name,
                            )
                        )
                spur = self.bfs(
                    root_path[-1],
                    end,
                    banned_zones=root_names,
                    banned_edges=banned_edges,
                )
                if spur is None:
                    continue
                full = root_path + spur[1:]
                key = tuple(z.name for z in full)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(full)

            if not candidates:
                break
            candidates.sort(key=self.path_cost)
            accepted.append(candidates.pop(0))

        return accepted

    # ------------------------------------------------------------------ utils

    @staticmethod
    def path_cost(path: List[Zone]) -> int:
        """Return the number of turns this path costs in isolation.

        Movement cost depends on the *destination* zone type:
        normal/priority = 1 turn, restricted = 2 turns. The first zone (the
        starting position) has no entry cost.
        """
        return sum(zone.zone_type.move_cost for zone in path[1:])
