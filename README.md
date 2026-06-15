*This project has been created as part of the 42 curriculum by mobenais.*

# Fly-in

## Description

Fly-in is a drone routing simulator. Given a network of zones described in a
plain-text map file, the program routes a fleet of drones from a single
**start hub** to a single **end hub** while respecting movement constraints
(zone types and capacities, connection capacities, restricted-zone 2-turn
transit) and minimizing the total number of simulation turns.

The implementation is written in Python 3.10+, is fully object-oriented,
fully type-checked (mypy) and lint-clean (flake8). No external graph library
is used — the BFS, the multi-path search and the turn-by-turn simulation are
all implemented from scratch in the `flyin/` package.

## Project layout

```
.
├── main.py                # CLI entry point
├── Makefile               # install / run / debug / clean / lint targets
├── requirements.txt       # runtime (pydantic) + dev tooling (flake8, mypy)
├── setup.cfg              # flake8 + mypy config
├── flyin/                 # OOP package
│   ├── network.py         #   ZoneType, Zone, Connection (the data model)
│   ├── graph.py           #   Graph (adjacency, validation)
│   ├── parser.py          #   MapParser, MapParseError
│   ├── pathfinder.py      #   PathFinder (BFS + edge-disjoint paths)
│   ├── simulator.py       #   Drone, PathMonitor, Simulator (turn engine)
│   └── view.py            #   TerminalView (ANSI-coloured rendering)
└── maps/                  # provided test maps (easy / medium / hard / challenger)
```

## Instructions

### Install

```sh
make install
```

The simulation requires Python 3.10 or later and a single runtime dependency,
`pydantic` (used for the turn-report value objects). `requirements.txt` also
lists the dev tooling (flake8, mypy).

### Run

```sh
make run                        # launch the interactive map menu
# or directly:
python main.py                  # interactive map menu
python main.py --no-color       # plain output (no ANSI colours)
python main.py --spec-only      # only the spec-mandated lines (one per turn)
python main.py --maps-root DIR  # scan DIR instead of ./maps for maps
```

The program launches an interactive menu listing every map found under `maps/`
(or under `--maps-root`); pick one and its simulation runs. To test your own
map, drop the `.txt` file into the maps directory, or point `--maps-root` at
the folder that contains it.

Available CLI options:

| Option         | Effect                                                       |
|----------------|--------------------------------------------------------------|
| `--no-color`   | Disable ANSI colours (useful for piping or for CI logs).     |
| `--spec-only`  | Print only the spec-mandated lines (one per turn).           |
| `--maps-root`  | Directory scanned by the interactive menu (default: `./maps`).|

Default output prints a header, the candidate paths, a legend, the
turn-by-turn log, the spec-mandated lines and a short statistics block.

### Debug

```sh
make debug          # launch the interactive menu under pdb
```

### Lint

```sh
make lint           # flake8 . + mypy with the flags required by the subject
make lint-strict    # flake8 . + mypy --strict (optional, recommended)
```

### Clean

```sh
make clean          # remove bytecode and cache directories
```

## Map format (quick reference)

```
nb_drones: 5

start_hub: start 0 0 [color=green]
end_hub: goal 10 10 [color=yellow]
hub: roof1 3 4 [zone=restricted color=red]
hub: corridorA 4 3 [zone=priority color=green max_drones=2]

connection: start-roof1
connection: corridorA-roof1 [max_link_capacity=2]
```

Zone types: `normal` (1 turn — default), `priority` (1 turn, preferred),
`restricted` (2 turns, drone occupies the connection during transit),
`blocked` (impassable). Zone names cannot contain dashes or whitespace.

## Algorithm and implementation strategy

### 1. Parsing (`flyin/parser.py`)

`MapParser` is a stateful parser that reads the map line by line, strips
comments, and dispatches on the directive prefix (`nb_drones:`, `start_hub:`,
`end_hub:`, `hub:`, `connection:`). All validation errors raise
`MapParseError` with the offending line number — duplicate zones, duplicate
connections (in either direction), unknown zone types, non-positive
capacities, names with dashes or whitespace, missing start/end, etc. all fail
fast with an explicit message.

### 2. Pathfinding (`flyin/pathfinder.py`)

The base primitive is a **BFS** adapted from a maze-solving BFS the author
wrote in another project: FIFO queue, visited set, parent map, reverse
reconstruction. Instead of moving across a grid with N/E/S/W neighbours we
move across the `Graph`'s zones via its `Connection` adjacency list. The BFS
accepts optional sets of banned zones and banned edges.

On top of BFS, `find_candidate_paths` builds a diverse pool of routes with two
complementary passes, both reusing the same BFS primitive:

* **edge-disjoint pass** — run BFS, ban every edge of the path just found, and
  repeat. This surfaces truly parallel corridors so each drone can get its own
  route when the graph forks.
* **node-spur pass** — ban one intermediate zone of the shortest path at a
  time. This surfaces alternatives that legitimately *share* a high-capacity
  bottleneck edge (e.g. a final `merge_point-goal` link of capacity 2), which a
  strictly edge-disjoint search would miss.

The candidates are deduplicated and sorted by cost; the scheduler then spreads
drones across them and the simulator's per-turn capacity rules resolve any
remaining congestion.

### 3. Scheduling (`flyin/simulator.PathMonitor`)

Given the candidate paths and the number of drones, the scheduler greedily
assigns each drone to the path with the smallest projected completion turn
(`path_cost + drones_already_on_path`). This minimizes the expected makespan
when the bottleneck is the path's length.

### 4. Simulation (`flyin/simulator.Simulator`)

Each simulation turn proceeds in two phases:

* **Phase A — landings.** Drones mid-transit on a restricted-zone connection
  MUST arrive this turn (the subject forbids extra waiting on the connection),
  so they finish their transit first and free the connection.
* **Phase B — greedy moves.** The remaining drones are processed by fewest
  remaining steps first — drones closest to the end move first, freeing the
  zones behind them so followers can advance the same turn — with the drone id
  as a deterministic tie-break. For each one we check the destination zone
  capacity and the connection capacity against the moves already admitted this
  turn; if both hold the drone moves (or starts a transit toward a restricted
  zone), otherwise it waits. Drones leaving a zone free up its capacity for the
  same turn, as required by the spec.

This deterministic resolution (remaining-steps, then id) is intentionally
simple: every decision can be explained line by line during the peer review.

### 5. Visualization (`flyin/view.py`)

`TerminalView` renders the simulation with ANSI colours derived from each
zone's `color=` metadata, with markers identifying the start (`S`), end
(`E`), restricted (`!`), priority (`*`), normal (`o`) and blocked (`x`)
zones. The default output is structured: header, candidate paths, legend,
turn-by-turn log, the strict spec-format lines, and statistics (total turns,
total path cost, average turns per drone). The `--spec-only` flag strips
everything except the spec-mandated movement lines so the output can be
diffed against an expected log. The coloured terminal output is the project's
single visual layer and satisfies the subject's visual-representation
requirement on its own.

## Performance targets

The subject defines reference targets per map (easy `< 10` turns, medium
`10–30`, hard `< 60`). The provided maps live under `maps/` and can be run
from the interactive menu (`make run`) to compare the achieved turn count
against the targets listed in the subject (VII.7).

## Resources

* Subject PDF: `en.subject.pdf` (root of the repository).
* Algorithmic references used during the design:
  * BFS on graphs — Cormen, Leiserson, Rivest, Stein, *Introduction to
    Algorithms*, chapter on Elementary Graph Algorithms.

### Use of AI

AI assistance was used as a pair-programmer during this project:

* All code in the repository has been read, understood and is owned by the
  author. Any function in this codebase can be explained on demand during the
  peer review.
