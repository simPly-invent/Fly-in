*This project has been created as part of the 42 curriculum by mobenais.*

# Fly-in

## Description

Fly-in is a drone routing simulator. Given a network of zones described in a
plain-text map file, the program routes a fleet of drones from a single
**start hub** to a single **end hub** while respecting movement constraints
(zone types and capacities, connection capacities, restricted-zone 2-turn
transit) and minimizing the total number of simulation turns.

The implementation is written in Python 3.10+, is fully object-oriented,
fully type-checked (mypy) and lint-clean (flake8). No external graph
library is used — the BFS, the multi-path search and the turn-by-turn
simulation are all implemented from scratch in the `flyin/` package.

## Project layout

```
.
├── main.py                # CLI entry point
├── Makefile               # install / run / debug / clean / lint targets
├── requirements.txt       # dev tooling only (flake8, mypy)
├── setup.cfg              # flake8 + mypy config
├── flyin/                 # OOP package (one class per responsibility)
│   ├── zone.py            #   Zone, ZoneType
│   ├── connection.py      #   Connection
│   ├── graph.py           #   Graph (adjacency, validation)
│   ├── drone.py           #   Drone (per-agent state)
│   ├── parser.py          #   MapParser, MapParseError
│   ├── pathfinder.py      #   PathFinder (BFS + k-shortest paths)
│   ├── simulator.py       #   PathScheduler, Simulator (turn engine)
│   ├── terminal_view.py   #   TerminalView (ANSI-coloured rendering)
│   ├── pygame_view.py     #   PygameView (GUI animation, optional)
│   └── menu.py            #   Menu (interactive map picker / render switch)
├── assets/
│   └── drones/            # user-supplied drone sprites for the pygame view
└── maps/                  # provided test maps (easy / medium / hard / challenger)
```

## Instructions

### Install

```sh
make install
```

Installs the dependencies listed in `requirements.txt`. The simulation
itself only requires Python 3.10 or later — `pygame` is optional and only
needed to launch the GUI view (the terminal view works without it).

### Run

```sh
make run MAP=maps/easy/02_simple_fork.txt        # terminal output
make pygame MAP=maps/hard/03_ultimate_challenge.txt  # GUI animation
make menu                                          # interactive menu
# or directly:
python main.py maps/medium/03_priority_puzzle.txt
python main.py maps/hard/02_capacity_hell.txt --pygame
python main.py                                     # no map → menu
```

Available CLI options:

| Option        | Effect                                                       |
|---------------|--------------------------------------------------------------|
| `--menu`      | Launch the interactive text menu (also the default with no map). |
| `--pygame`    | Render the simulation in a pygame window.                    |
| `--no-color`  | Disable ANSI colours (useful for piping or for CI logs).     |
| `--spec-only` | Print only the spec-mandated lines (one per turn) and exit.  |

The **pygame view is a real-time 3D bathymetric chart** rendered with a
hand-rolled perspective pipeline (no OpenGL dependency). The drone
network is laid out as an undersea topographic map: zones are placed at
their `(x, y)` map coordinates with Y elevation derived from their type
(`priority` zones form sea-mounts, `restricted` zones sit in trenches,
`blocked` zones are abyssal pits). A triangulated seafloor is generated
underneath them by inverse-distance interpolation of zone heights, then
shaded with depth-tinted Lambert lighting and overlaid with
marching-squares isobaths (contour lines) and an optional nautical grid.
Zones float just above the floor on a vertical mooring pylon, connections
glow like submerged shipping lanes, and drones are luminous mini-subs
with running lights and circular shadows on the seafloor. A compass rose
that rotates with the camera and a depth scale on the sidebar complete
the chart feel.

| Input            | Action                                |
|------------------|---------------------------------------|
| Left-drag        | Orbit the camera (yaw / pitch)        |
| Middle-drag      | Pan the camera target                 |
| Mouse wheel      | Zoom in / out                         |
| `SPACE`          | Play / pause animation                |
| `← / →`          | Step back / forward 1 turn            |
| `R`              | Restart from turn 0                   |
| `+ / -`          | Speed up / slow down the animation    |
| `G`              | Toggle the seafloor grid              |
| `C`              | Cycle contour-line density (off / normal / dense) |
| `ESC` or `X`     | Quit                                  |

Default output prints a header, candidate paths, the turn-by-turn log, the
spec-mandated lines and a short statistics block.

### Drone sprites (pygame 3D)

Drop your drone images into `assets/drones/` (PNG with transparency is
recommended). Each sprite is loaded once and rendered as a billboard
(always facing the camera, scaled by distance). Sprites are assigned to
drones D1, D2, D3, … in alphabetical order of their filename, cycling
back to the first when there are more drones than sprites. If the folder
is empty, drones are drawn as labelled coloured discs with depth shading
and a small ground shadow. See `assets/drones/README.md` for the exact
expected format.

### Debug

```sh
make debug MAP=maps/hard/02_capacity_hell.txt
```

Runs the entry point under Python's built-in debugger (`pdb`).

### Lint

```sh
make lint           # flake8 . + mypy with the flags required by the subject
make lint-strict    # flake8 . + mypy --strict (optional, recommended)
```

### Clean

```sh
make clean
```

Removes Python bytecode and `__pycache__`, `.mypy_cache`, `.pytest_cache`,
`.ruff_cache` directories.

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
capacities, names with dashes or whitespace, missing start/end, etc. all
fail fast with an explicit message.

### 2. Pathfinding (`flyin/pathfinder.py`)

The base primitive is a **BFS** adapted from a maze-solving BFS used in
another project: FIFO queue, visited set, parent map, reverse
reconstruction. Instead of moving across a grid with N/E/S/W neighbours we
move across the `Graph`'s zones via its `Connection` adjacency list.
The BFS accepts optional sets of banned zones and banned edges so we can
mine alternative paths.

On top of BFS, `find_k_shortest_paths` implements a Yen-style search: from
each accepted path it spurs alternative branches by banning the next edge
along the current path and forbidding the prefix zones. This delivers
several distinct routes when the graph has forks downstream of a shared
trunk (e.g. the `simple_fork` map where everyone must cross `junction`
before splitting).

### 3. Scheduling (`flyin/simulator.PathScheduler`)

Given the k candidate paths and the number of drones, the scheduler
greedily assigns each drone to the path with the smallest projected
completion turn (`path_cost + drones_already_on_path`). This minimizes the
expected makespan when the bottleneck is the path's narrowest hop.

### 4. Simulation (`flyin/simulator.Simulator`)

Each simulation turn proceeds in two phases:

* **Phase A — landings.** Drones in mid-transit on a restricted-zone
  connection MUST arrive this turn (the subject explicitly forbids extra
  waiting on the connection). Capacity invariants are checked on the way
  in; a violation surfaces as a `RuntimeError` rather than silently
  corrupting state. Drones that land this turn skip Phase B (single move
  per drone per turn).
* **Phase B — global intent resolution.** Every remaining drone proposes
  at most one move (step into a normal/priority zone, or start a transit
  toward a restricted zone). We then solve all intents *together* by
  checking, for each zone and each connection, that
  `load + arrivals + entering – leaving ≤ capacity`. If any constraint is
  violated we drop the lowest-priority offender (preferring drones whose
  source zone is not saturated, since their departure does not "rescue"
  anyone else) and re-check until feasibility is reached. This approach
  is what lets the simulator resolve **swaps** correctly — two drones
  trading places on two capacity-1 zones, which neither could do under a
  naive incremental admission strategy.

### 5. Visualization (`flyin/terminal_view.py`)

`TerminalView` renders the simulation with ANSI colours derived from each
zone's `color=` metadata, with markers identifying the start (`S`), end
(`E`), restricted (`!`), priority (`*`), normal (`o`) and blocked (`x`)
zones. The default output is structured: header, candidate paths,
legend, turn-by-turn log, the strict spec-format lines, and statistics
(total turns, total path cost, average turns per drone). The `--spec-only`
flag strips everything except the spec-mandated movement lines so the
output can be diffed against an expected log.

## Performance against subject benchmarks

Running each provided map with the default scheduler:

| Map                                    | Drones | Target | Result      |
|----------------------------------------|--------|--------|-------------|
| `easy/01_linear_path.txt`              | 2      | ≤ 6    | **4**       |
| `easy/02_simple_fork.txt`              | 4      | ≤ 8    | **4**       |
| `easy/03_basic_capacity.txt`           | 4      | ≤ 6    | **4**       |
| `medium/01_dead_end_trap.txt`          | 5      | ≤ 12   | **8**       |
| `medium/02_circular_loop.txt`          | 6      | ≤ 15   | **10**      |
| `medium/03_priority_puzzle.txt`        | 5      | ≤ 12   | **6**       |
| `hard/01_maze_nightmare.txt`           | 8      | ≤ 30   | **13**      |
| `hard/02_capacity_hell.txt`            | 12     | ≤ 35   | **16**      |
| `hard/03_ultimate_challenge.txt`       | 15     | ≤ 45   | **27**      |
| `challenger/01_the_impossible_dream.txt` (optional) | 25 | reference 45 | 51 |

All nine mandatory benchmarks beat their target. The challenger map is
optional and does not affect grading.

## Resources

* Subject PDF: `en.subject.pdf` (root of the repository).
* Algorithmic references used during the design:
  * BFS on graphs — Cormen, Leiserson, Rivest, Stein, *Introduction to
    Algorithms*, chapter on Elementary Graph Algorithms.
  * Yen's k-shortest paths algorithm — Yen, J. Y. (1971), *Finding the K
    Shortest Loopless Paths in a Network*. The `find_k_shortest_paths`
    method follows the same spur-node / root-path structure.
  * The "lem-in" 42 project, which inspired the multi-path-distribution
    heuristic used by `PathScheduler`.

### Use of AI

AI assistance (Claude) was used as a pair-programmer during this project.
Concretely:

* The BFS in `flyin/pathfinder.py` is an adaptation of a BFS implementation
  written by the author in another 42 project (maze solver). The
  adaptation to the zone/connection graph and the addition of banned-edge
  / banned-zone constraints were drafted with AI assistance and reviewed
  line-by-line by the author.
* Boilerplate scaffolding (Makefile targets, `setup.cfg`, docstrings,
  type hints) was generated with AI assistance.
* The capacity-resolution heuristic in `Simulator._find_violator` (drop
  the offender with the most slack in their source zone first) was
  iteratively refined by tracing deadlocks together with AI; the final
  rule and its rationale are documented inline in the source.
* All code in the repository has been read, understood and is owned by
  the author. Any function in this codebase can be explained on demand
  during the peer review.
