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
    # - Retourner tuple(sorted((a, b))) — clé canonique d'une arête non-orientée.
    raise NotImplementedError("À implémenter")


class PathFinder:
    """BFS-based pathfinder for the drone network."""

    def __init__(self, graph: Graph) -> None:
        # - Stocker self.graph = graph.
        raise NotImplementedError("À implémenter")

    # ----------------------------------------------------------------- BFS API

    def bfs(
        self,
        source: Zone,
        target: Zone,
        banned_zones: Optional[Set[str]] = None,
        banned_edges: Optional[Set[ConnectionKey]] = None,
    ) -> Optional[List[Zone]]:
        # - banned_zones = banned_zones or set() ; banned_edges = banned_edges or set().
        # - Si source ou target non-passable → retourner None.
        # - Si source.name == target.name → retourner [source].
        # - Init: visited = {source.name}, parent = {}, queue = deque([source.name]).
        # - Tant que queue non vide:
        #     - current = queue.popleft().
        #     - Si current == target.name → break.
        #     - Pour chaque (neighbour, connection) dans self.graph.neighbors(current):
        #         - Skip si déjà visité, non-passable, ou dans banned_zones (sauf target),
        #           ou edge dans banned_edges.
        #         - visited.add(neighbour.name) ; parent[neighbour.name] = current ;
        #           queue.append(neighbour.name).
        # - Si target.name not in visited → retourner None.
        # - Reconstruire le chemin par parent en remontant depuis target jusqu'à source.
        # - Reverse la liste de noms et retourner [graph.get_zone(name) for name in ...].
        raise NotImplementedError("À implémenter")

    def find_disjoint_paths(self, max_paths: int) -> List[List[Zone]]:
        # - Si max_paths <= 0 → retourner [].
        # - start = self.graph.start ; end = self.graph.end.
        # - paths = [] ; used_edges: Set[ConnectionKey] = set().
        # - Répéter max_paths fois:
        #     - path = self.bfs(start, end, banned_edges=used_edges).
        #     - Si None → break.
        #     - Append path à paths.
        #     - Ajouter chaque _edge_key(hop_a, hop_b) à used_edges (pour interdire au tour suivant).
        # - Si paths vide → fallback bfs(start, end) sans ban et l'ajouter s'il existe.
        # - paths.sort(key=self.path_cost) — tri croissant par coût.
        # - Retourner paths.
        raise NotImplementedError("À implémenter")

    def find_k_shortest_paths(self, k: int) -> List[List[Zone]]:
        # Yen-style sur self.bfs:
        # - Si k <= 0 → [].
        # - first = bfs(start, end) ; si None → [].
        # - accepted = [first] ; candidates = [] ; seen = {tuple(noms de first)}.
        # - Tant que len(accepted) < k:
        #     - previous = accepted[-1].
        #     - Pour chaque spur_index dans [0 .. len(previous)-2]:
        #         - root_path = previous[: spur_index + 1].
        #         - root_names = {z.name for z in root_path[:-1]}.
        #         - banned_edges: pour chaque path déjà accepté qui partage le même prefix,
        #             ajouter l'arête (path[spur_index], path[spur_index+1]).
        #         - spur = bfs(root_path[-1], end, banned_zones=root_names, banned_edges=banned_edges).
        #         - Si spur None → continue.
        #         - full = root_path + spur[1:] ; key = tuple(noms) ; skip si déjà vu.
        #         - seen.add(key) ; append candidate.
        #     - Si candidates vide → break.
        #     - candidates.sort(key=self.path_cost) ; accepted.append(candidates.pop(0)).
        # - Retourner accepted.
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------------------------ utils

    @staticmethod
    def path_cost(path: List[Zone]) -> int:
        # - Retourner sum(zone.zone_type.move_cost for zone in path[1:]).
        # - La première zone (départ) n'a pas de coût d'entrée.
        raise NotImplementedError("À implémenter")
