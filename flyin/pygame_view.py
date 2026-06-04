"""Submarine bathymetric pygame visualization.

The scene is rendered in true 3D with a hand-rolled perspective projection
(no OpenGL dependency). The drone network is laid out as a bathymetric
chart of an undersea region: zones are positioned in 3D space, and a
triangulated seafloor is generated underneath by inverse-distance
interpolation of zone elevations. The seafloor is shaded by depth and
slope (Lambert), overlaid with isobath contour lines and an optional
nautical grid. Zones float just above the floor on a vertical mooring
pylon, like marker buoys; drones are luminous mini-subs with running
lights and a soft halo, casting circular shadows on the floor.

Controls
--------

Mouse
* Left-drag        : orbit yaw / pitch
* Middle-drag      : pan the camera target
* Wheel up / down  : zoom in / out

Keyboard
* SPACE      : play / pause
* RIGHT      : step forward one turn
* LEFT       : step back one turn
* R          : restart from turn 0
* + / -      : speed up / slow down animation
* G          : toggle grid + contour lines
* C          : cycle contour density
* ESC or X   : quit
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from flyin.graph import Graph
from flyin.simulator import Simulator, TurnReport
from flyin.zone import Zone, ZoneType


ASSETS_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "drones"
SPRITE_EXTENSIONS: Tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp")


class PygameUnavailableError(RuntimeError):
    """Raised when pygame cannot be imported."""


Vec3 = Tuple[float, float, float]
ColourRGB = Tuple[int, int, int]


# ------------------------------------------------------------------- palette

# Bathymetric palette: deep-water navy through teal mid-shelf up to a sandy
# continental ridge tint. Calibrated to look like a printed nautical chart.
BATHY_STOPS: List[Tuple[float, ColourRGB]] = [
    (0.00, (4, 12, 30)),       # abyss
    (0.20, (8, 26, 60)),       # deep
    (0.45, (18, 58, 96)),      # bathyal
    (0.65, (40, 110, 138)),    # mid-shelf teal
    (0.82, (90, 165, 175)),    # shelf
    (1.00, (170, 190, 150)),   # ridge top
]

WATER_TOP: ColourRGB = (24, 56, 90)
WATER_BOTTOM: ColourRGB = (4, 10, 22)
CONTOUR_COLOUR: ColourRGB = (90, 210, 230)
CONTOUR_DIM: ColourRGB = (40, 120, 145)
GRID_COLOUR: ColourRGB = (45, 95, 130)
PYLON_COLOUR: ColourRGB = (160, 215, 230)
BUOY_HALO: ColourRGB = (255, 220, 130)
LIGHT_DIR: Vec3 = (0.35, 0.85, 0.40)  # late-afternoon sun, slightly off-axis

NAMED_COLOURS: Dict[str, ColourRGB] = {
    "red": (235, 90, 90),
    "green": (110, 220, 130),
    "blue": (120, 160, 240),
    "yellow": (250, 220, 110),
    "cyan": (110, 220, 230),
    "magenta": (220, 130, 220),
    "purple": (185, 130, 230),
    "orange": (250, 175, 95),
    "pink": (250, 175, 215),
    "brown": (165, 120, 80),
    "gray": (150, 150, 150),
    "grey": (150, 150, 150),
    "black": (40, 40, 40),
    "white": (240, 240, 240),
    "gold": (240, 210, 90),
    "lime": (175, 235, 110),
}

DEFAULT_ZONE_FILL: Dict[ZoneType, ColourRGB] = {
    ZoneType.NORMAL: (220, 220, 230),
    ZoneType.PRIORITY: (110, 220, 240),
    ZoneType.RESTRICTED: (245, 130, 130),
    ZoneType.BLOCKED: (70, 70, 80),
}

DRONE_FALLBACK_COLOURS: List[ColourRGB] = [
    (255, 220, 100), (110, 230, 255), (255, 170, 90), (190, 240, 130),
    (235, 150, 250), (255, 140, 60), (140, 220, 200), (240, 240, 130),
]


# ------------------------------------------------------------------- math


def _lerp_colour(a: ColourRGB, b: ColourRGB, t: float) -> ColourRGB:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _depth_colour(height: float, y_min: float, y_max: float) -> ColourRGB:
    """Map a Y coordinate to a bathymetric colour."""
    if y_max - y_min < 1e-6:
        t = 0.5
    else:
        t = (height - y_min) / (y_max - y_min)
    t = max(0.0, min(1.0, t))
    for i in range(len(BATHY_STOPS) - 1):
        t0, c0 = BATHY_STOPS[i]
        t1, c1 = BATHY_STOPS[i + 1]
        if t0 <= t <= t1:
            local = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return _lerp_colour(c0, c1, local)
    return BATHY_STOPS[-1][1]


def _normalize(v: Vec3) -> Vec3:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-9:
        return (0.0, 1.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _shade(normal: Vec3, base: ColourRGB) -> ColourRGB:
    """Lambertian shading with a touch of ambient."""
    n = _normalize(normal)
    light = _normalize(LIGHT_DIR)
    lambert = max(0.0, n[0] * light[0] + n[1] * light[1] + n[2] * light[2])
    factor = 0.45 + 0.55 * lambert
    return (
        max(0, min(255, int(base[0] * factor))),
        max(0, min(255, int(base[1] * factor))),
        max(0, min(255, int(base[2] * factor))),
    )


# ------------------------------------------------------------------ camera


class Camera3D:
    """Orbit camera with hand-rolled perspective projection."""

    def __init__(self, target: Vec3, distance: float) -> None:
        self.target: Vec3 = target
        self.distance: float = distance
        self.yaw: float = math.radians(35.0)
        self.pitch: float = math.radians(-32.0)
        self.focal: float = 900.0
        self.min_distance: float = 200.0
        self.max_distance: float = 9000.0
        self.min_pitch: float = math.radians(-85.0)
        self.max_pitch: float = math.radians(85.0)

    def rotate(self, delta_yaw: float, delta_pitch: float) -> None:
        self.yaw = (self.yaw + delta_yaw) % (2 * math.pi)
        self.pitch = max(self.min_pitch,
                         min(self.max_pitch, self.pitch + delta_pitch))

    def zoom(self, factor: float) -> None:
        self.distance = max(self.min_distance,
                            min(self.max_distance, self.distance * factor))

    def pan(self, dx: float, dy: float) -> None:
        right, up, _ = self._basis()
        scale = self.distance / self.focal
        self.target = (
            self.target[0] + (right[0] * dx + up[0] * dy) * scale,
            self.target[1] + (right[1] * dx + up[1] * dy) * scale,
            self.target[2] + (right[2] * dx + up[2] * dy) * scale,
        )

    def _basis(self) -> Tuple[Vec3, Vec3, Vec3]:
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        forward: Vec3 = (sy * cp, -sp, cy * cp)
        right: Vec3 = (cy, 0.0, -sy)
        up: Vec3 = _cross(right, forward)
        return right, up, forward

    def project(
        self,
        world: Vec3,
        screen_cx: float,
        screen_cy: float,
    ) -> Optional[Tuple[int, int, float]]:
        """Project a 3D world point. Returns ``(x, y, z_eye)`` or None if behind."""
        right, up, forward = self._basis()
        cam_pos = (
            self.target[0] - forward[0] * self.distance,
            self.target[1] - forward[1] * self.distance,
            self.target[2] - forward[2] * self.distance,
        )
        rel = (world[0] - cam_pos[0],
               world[1] - cam_pos[1],
               world[2] - cam_pos[2])
        x_cam = rel[0] * right[0] + rel[1] * right[1] + rel[2] * right[2]
        y_cam = rel[0] * up[0] + rel[1] * up[1] + rel[2] * up[2]
        z_cam = rel[0] * forward[0] + rel[1] * forward[1] + rel[2] * forward[2]
        if z_cam <= 1.0:
            return None
        sx = x_cam * self.focal / z_cam + screen_cx
        sy = -y_cam * self.focal / z_cam + screen_cy
        return (int(sx), int(sy), z_cam)


# --------------------------------------------------------------- main view


class PygameView:
    """Submarine bathymetric scene + animation driver."""

    WIN_W: int = 1280
    WIN_H: int = 800
    SIDEBAR_W: int = 320
    HUD_H: int = 80
    FPS: int = 60
    DEFAULT_FRAMES_PER_TURN: int = 30
    TERRAIN_RES: int = 22

    # World scale.
    UNIT: float = 130.0
    SEAFLOOR_OFFSET: float = -90.0  # base depth of the bathymetric chart
    # Zone elevations above the seafloor (drives both layout and heightfield).
    ELEVATION: Dict[ZoneType, float] = {
        ZoneType.NORMAL: 0.0,
        ZoneType.PRIORITY: 90.0,
        ZoneType.RESTRICTED: -55.0,
        ZoneType.BLOCKED: -160.0,
    }
    DRONE_ALTITUDE: float = 75.0

    def __init__(
        self,
        graph: Graph,
        simulator: Simulator,
        paths: List[List[Zone]],
        reports: List[TurnReport],
        title: str = "Fly-in — Bathymetric Chart",
    ) -> None:
        self.graph = graph
        self.simulator = simulator
        self.paths = paths
        self.reports = reports
        self.title = title
        self.frames_per_turn: int = self.DEFAULT_FRAMES_PER_TURN
        self.show_grid: bool = True
        self.contour_density: int = 1  # 0=off, 1=normal, 2=dense

        self._pygame: Any = None
        self._screen: Any = None
        self._font: Any = None
        self._font_small: Any = None
        self._font_tiny: Any = None
        self._clock: Any = None
        self._sprites: List[Any] = []

        self._world: Dict[str, Vec3] = {}
        self._scene_extent: float = 1000.0
        self._camera: Optional[Camera3D] = None

        # Heightfield mesh of the seafloor (filled in _setup()).
        self._mesh: List[List[Vec3]] = []
        self._mesh_min_y: float = 0.0
        self._mesh_max_y: float = 0.0

    # --------------------------------------------------------------- setup

    def _import_pygame(self) -> Any:
        try:
            import pygame
        except ImportError as exc:
            raise PygameUnavailableError(
                "pygame is not installed. Install it with "
                "'pip install pygame' (or 'make install')."
            ) from exc
        return pygame

    def _setup(self) -> None:
        pg = self._pygame
        pg.init()
        pg.display.set_caption(self.title)
        self._screen = pg.display.set_mode((self.WIN_W, self.WIN_H))
        self._clock = pg.time.Clock()
        self._font = pg.font.SysFont("dejavusansmono,monospace", 16)
        self._font_small = pg.font.SysFont("dejavusansmono,monospace", 12)
        self._font_tiny = pg.font.SysFont("dejavusansmono,monospace", 10)
        self._build_world()
        self._build_terrain()
        self._init_camera()
        self._load_sprites()

    def _build_world(self) -> None:
        zones = list(self.graph.zones)
        if not zones:
            return
        xs = [z.x for z in zones]
        ys = [z.y for z in zones]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        x_mid = (x_min + x_max) / 2.0
        y_mid = (y_min + y_max) / 2.0
        for zone in zones:
            world_x = (zone.x - x_mid) * self.UNIT
            world_z = (zone.y - y_mid) * self.UNIT
            world_y = self.ELEVATION[zone.zone_type]
            self._world[zone.name] = (world_x, world_y, world_z)
        x_span = max(x_max - x_min, 1) * self.UNIT
        z_span = max(y_max - y_min, 1) * self.UNIT
        self._scene_extent = max(x_span, z_span)

    def _build_terrain(self) -> None:
        """Generate the seafloor heightfield from zone elevations (IDW)."""
        res = self.TERRAIN_RES
        half = self._scene_extent * 0.95
        step = (2 * half) / res
        # IDW power: larger = sharper features around zones.
        power = 1.6
        # Influence reach: smaller = each zone affects only a small patch.
        reach2 = (self.UNIT * 1.6) ** 2

        mesh: List[List[Vec3]] = []
        y_min = math.inf
        y_max = -math.inf
        for ix in range(res + 1):
            row: List[Vec3] = []
            for iz in range(res + 1):
                x = -half + ix * step
                z = -half + iz * step
                # IDW from zone elevations.
                total_w = 0.0
                total_y = 0.0
                for zone in self.graph.zones:
                    wp = self._world[zone.name]
                    d2 = (wp[0] - x) ** 2 + (wp[2] - z) ** 2 + reach2 * 0.05
                    w = 1.0 / (d2 ** power)
                    total_w += w
                    total_y += w * wp[1]
                base = (total_y / total_w) if total_w > 0 else 0.0
                # Add gentle organic noise so flat regions still ripple.
                noise = (
                    math.sin(x * 0.011) * 8.0
                    + math.cos(z * 0.013) * 6.0
                    + math.sin((x + z) * 0.007) * 4.0
                )
                y = base + noise + self.SEAFLOOR_OFFSET
                row.append((x, y, z))
                y_min = min(y_min, y)
                y_max = max(y_max, y)
            mesh.append(row)
        self._mesh = mesh
        # Floor of the gradient is a touch deeper than the actual minimum so
        # the deepest mesh point gets a non-black tint.
        self._mesh_min_y = y_min - 20.0
        self._mesh_max_y = y_max + 5.0

    def _init_camera(self) -> None:
        self._camera = Camera3D(
            target=(0.0, 0.0, 0.0),
            distance=max(self._scene_extent * 2.0, 800.0),
        )

    def _load_sprites(self) -> None:
        pg = self._pygame
        if not ASSETS_DIR.is_dir():
            self._sprites = []
            return
        files = sorted(
            p for p in ASSETS_DIR.iterdir()
            if p.suffix.lower() in SPRITE_EXTENSIONS
        )
        sprites: List[Any] = []
        for path in files:
            try:
                surface = pg.image.load(str(path)).convert_alpha()
                sprites.append(surface)
            except (pg.error, OSError):
                continue
        self._sprites = sprites

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        """Open the window and drive the animation + 3D render loop."""
        self._pygame = self._import_pygame()
        try:
            self._setup()
            self._loop()
        finally:
            self._pygame.quit()

    # --------------------------------------------------------- snapshots

    def _build_snapshots(self) -> List[Dict[int, Vec3]]:
        start_pos = self._world[self.graph.start.name]
        n = self.graph.nb_drones
        positions: Dict[int, Vec3] = {}
        for i in range(1, n + 1):
            positions[i] = self._fan_offset(start_pos, i, n)
        snapshots: List[Dict[int, Vec3]] = [dict(positions)]
        for report in self.reports:
            new_positions = dict(positions)
            for move in report.moves:
                drone_id = int(move.drone_label[1:])
                target = self._resolve_destination(move.destination)
                if target is not None:
                    new_positions[drone_id] = target
            positions = new_positions
            snapshots.append(dict(positions))
        return snapshots

    def _resolve_destination(self, destination: str) -> Optional[Vec3]:
        if "-" in destination:
            parts = destination.split("-")
            if (len(parts) == 2 and self.graph.has_zone(parts[0])
                    and self.graph.has_zone(parts[1])):
                pa = self._world.get(parts[0])
                pb = self._world.get(parts[1])
                if pa is not None and pb is not None:
                    mid = ((pa[0] + pb[0]) / 2.0,
                           (pa[1] + pb[1]) / 2.0 + self.DRONE_ALTITUDE,
                           (pa[2] + pb[2]) / 2.0)
                    return mid
        if self.graph.has_zone(destination):
            base = self._world.get(destination)
            if base is not None:
                return (base[0], base[1] + self.DRONE_ALTITUDE, base[2])
        return None

    def _fan_offset(self, base: Vec3, index: int, total: int) -> Vec3:
        if total <= 1:
            return (base[0], base[1] + self.DRONE_ALTITUDE, base[2])
        radius = 30.0
        angle = (2 * math.pi) * (index - 1) / max(total, 1)
        return (base[0] + radius * math.cos(angle),
                base[1] + self.DRONE_ALTITUDE,
                base[2] + radius * math.sin(angle))

    # --------------------------------------------------------- main loop

    def _loop(self) -> None:
        pg = self._pygame
        playing = False
        turn_index = 0
        frame_in_turn = 0
        total_turns = len(self.reports)
        snapshots = self._build_snapshots()
        dragging_orbit = False
        dragging_pan = False
        last_mouse: Optional[Tuple[int, int]] = None

        running = True
        while running:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_ESCAPE:
                        running = False
                    elif event.key == pg.K_SPACE:
                        playing = not playing
                        if turn_index >= total_turns:
                            turn_index = 0
                            frame_in_turn = 0
                    elif event.key == pg.K_RIGHT:
                        playing = False
                        if turn_index < total_turns:
                            turn_index += 1
                            frame_in_turn = self.frames_per_turn
                    elif event.key == pg.K_LEFT:
                        playing = False
                        if turn_index > 0:
                            turn_index -= 1
                            frame_in_turn = self.frames_per_turn
                    elif event.key == pg.K_r:
                        turn_index = 0
                        frame_in_turn = 0
                        playing = False
                    elif event.key in (pg.K_PLUS, pg.K_EQUALS, pg.K_KP_PLUS):
                        self.frames_per_turn = max(4, self.frames_per_turn - 4)
                    elif event.key in (pg.K_MINUS, pg.K_KP_MINUS):
                        self.frames_per_turn += 4
                    elif event.key == pg.K_g:
                        self.show_grid = not self.show_grid
                    elif event.key == pg.K_c:
                        self.contour_density = (self.contour_density + 1) % 3
                elif event.type == pg.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        dragging_orbit = True
                        last_mouse = event.pos
                    elif event.button == 2:
                        dragging_pan = True
                        last_mouse = event.pos
                    elif event.button == 4 and self._camera:
                        self._camera.zoom(0.9)
                    elif event.button == 5 and self._camera:
                        self._camera.zoom(1.1)
                elif event.type == pg.MOUSEBUTTONUP:
                    if event.button == 1:
                        dragging_orbit = False
                    elif event.button == 2:
                        dragging_pan = False
                    last_mouse = None
                elif event.type == pg.MOUSEMOTION and self._camera:
                    if last_mouse is not None:
                        dx = event.pos[0] - last_mouse[0]
                        dy = event.pos[1] - last_mouse[1]
                        if dragging_orbit:
                            self._camera.rotate(dx * 0.008, -dy * 0.008)
                        elif dragging_pan:
                            self._camera.pan(-dx, dy)
                        last_mouse = event.pos

            if playing and turn_index < total_turns:
                frame_in_turn += 1
                if frame_in_turn >= self.frames_per_turn:
                    frame_in_turn = 0
                    turn_index += 1
                    if turn_index >= total_turns:
                        playing = False
                        turn_index = total_turns
                        frame_in_turn = self.frames_per_turn

            self._render_frame(snapshots, turn_index, frame_in_turn, playing)
            self._clock.tick(self.FPS)

    # ----------------------------------------------------------- rendering

    def _scene_centre(self) -> Tuple[float, float]:
        cx = (self.WIN_W - self.SIDEBAR_W) / 2.0
        cy = self.HUD_H + (self.WIN_H - self.HUD_H) / 2.0
        return cx, cy

    def _render_frame(
        self,
        snapshots: List[Dict[int, Vec3]],
        turn_index: int,
        frame_in_turn: int,
        playing: bool,
    ) -> None:
        pg = self._pygame
        self._screen.fill(WATER_BOTTOM)
        self._draw_water_column()

        prims = self._collect_terrain_primitives()
        prims.extend(self._collect_scene_primitives(
            snapshots, turn_index, frame_in_turn))
        prims.sort(key=lambda p: -p[0])
        for _, draw in prims:
            draw()

        self._draw_hud(turn_index, playing)
        self._draw_sidebar(turn_index)
        self._draw_compass()
        pg.display.flip()

    def _draw_water_column(self) -> None:
        """Soft top-to-bottom water gradient (sunlight attenuation feel)."""
        pg = self._pygame
        h = self.WIN_H - self.HUD_H
        w = self.WIN_W - self.SIDEBAR_W
        for i in range(h):
            t = i / max(h - 1, 1)
            colour = _lerp_colour(WATER_TOP, WATER_BOTTOM, t)
            pg.draw.line(self._screen, colour,
                         (0, self.HUD_H + i), (w, self.HUD_H + i))

    # ------------------------------------------------- terrain primitives

    def _collect_terrain_primitives(self) -> List[Tuple[float, Callable[[], None]]]:
        """Triangulated seafloor + grid lines + contours, depth-sorted."""
        if not self._mesh or self._camera is None:
            return []
        prims: List[Tuple[float, Callable[[], None]]] = []
        cx, cy = self._scene_centre()
        mesh = self._mesh
        res = self.TERRAIN_RES

        # Triangles.
        for ix in range(res):
            for iz in range(res):
                a = mesh[ix][iz]
                b = mesh[ix + 1][iz]
                c = mesh[ix + 1][iz + 1]
                d = mesh[ix][iz + 1]
                self._maybe_add_triangle(prims, a, b, c, cx, cy)
                self._maybe_add_triangle(prims, a, c, d, cx, cy)

        # Grid lines (drawn between mesh corners). Keep them in their own
        # pass so they layer cleanly on top of the triangles.
        if self.show_grid:
            for ix in range(res + 1):
                for iz in range(res):
                    a = mesh[ix][iz]
                    b = mesh[ix][iz + 1]
                    prims.append(self._line_primitive(a, b, GRID_COLOUR, 1))
            for iz in range(res + 1):
                for ix in range(res):
                    a = mesh[ix][iz]
                    b = mesh[ix + 1][iz]
                    prims.append(self._line_primitive(a, b, GRID_COLOUR, 1))

        # Isobaths (marching squares on the heightfield).
        if self.contour_density > 0:
            prims.extend(self._collect_contours())

        return prims

    def _maybe_add_triangle(
        self,
        out: List[Tuple[float, Callable[[], None]]],
        a: Vec3,
        b: Vec3,
        c: Vec3,
        cx: float,
        cy: float,
    ) -> None:
        assert self._camera is not None
        pa = self._camera.project(a, cx, cy)
        pb = self._camera.project(b, cx, cy)
        pc = self._camera.project(c, cx, cy)
        if pa is None or pb is None or pc is None:
            return
        # Triangle normal in world space (orient so up is +Y).
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = _cross(u, v)
        if n[1] < 0:
            n = (-n[0], -n[1], -n[2])
        avg_y = (a[1] + b[1] + c[1]) / 3.0
        base = _depth_colour(avg_y, self._mesh_min_y, self._mesh_max_y)
        colour = _shade(n, base)
        avg_depth = (pa[2] + pb[2] + pc[2]) / 3.0
        points = [(pa[0], pa[1]), (pb[0], pb[1]), (pc[0], pc[1])]

        def draw() -> None:
            self._pygame.draw.polygon(self._screen, colour, points)

        out.append((avg_depth, draw))

    def _line_primitive(
        self,
        a: Vec3,
        b: Vec3,
        colour: ColourRGB,
        width: int,
    ) -> Tuple[float, Callable[[], None]]:
        assert self._camera is not None
        cx, cy = self._scene_centre()
        pa = self._camera.project(a, cx, cy)
        pb = self._camera.project(b, cx, cy)

        def draw() -> None:
            if pa is None or pb is None:
                return
            self._pygame.draw.line(self._screen, colour,
                                   (pa[0], pa[1]), (pb[0], pb[1]), width)

        if pa is None or pb is None:
            return (0.0, draw)
        return ((pa[2] + pb[2]) / 2.0 - 1.0, draw)

    def _collect_contours(self) -> List[Tuple[float, Callable[[], None]]]:
        """Marching-squares isobaths over the heightfield."""
        prims: List[Tuple[float, Callable[[], None]]] = []
        mesh = self._mesh
        if not mesh:
            return prims
        res = self.TERRAIN_RES
        y_min = self._mesh_min_y
        y_max = self._mesh_max_y
        span = max(y_max - y_min, 1e-6)
        # Density: 4 / 8 / 16 contour bands.
        n_levels = (0, 6, 14)[self.contour_density]
        for k in range(1, n_levels):
            level = y_min + span * (k / n_levels)
            major = (k % 2 == 0)
            colour = CONTOUR_COLOUR if major else CONTOUR_DIM
            width = 2 if major else 1
            for ix in range(res):
                for iz in range(res):
                    a = mesh[ix][iz]
                    b = mesh[ix + 1][iz]
                    c = mesh[ix + 1][iz + 1]
                    d = mesh[ix][iz + 1]
                    segs = self._marching_square(a, b, c, d, level)
                    for p, q in segs:
                        prims.append(self._line_primitive(p, q, colour, width))
        return prims

    @staticmethod
    def _marching_square(
        a: Vec3, b: Vec3, c: Vec3, d: Vec3, level: float
    ) -> List[Tuple[Vec3, Vec3]]:
        """Return contour-line segments for a quad cell A-B-C-D at ``level``."""
        ya, yb, yc, yd = a[1], b[1], c[1], d[1]
        code = 0
        if ya > level:
            code |= 1
        if yb > level:
            code |= 2
        if yc > level:
            code |= 4
        if yd > level:
            code |= 8

        def interp(p: Vec3, q: Vec3) -> Vec3:
            yp, yq = p[1], q[1]
            if abs(yq - yp) < 1e-9:
                t = 0.5
            else:
                t = (level - yp) / (yq - yp)
            return (
                p[0] + (q[0] - p[0]) * t,
                level,
                p[2] + (q[2] - p[2]) * t,
            )

        # 16 cases of marching squares. Use 0 and 15 (no segment) early-out.
        if code in (0, 15):
            return []
        ab = interp(a, b)
        bc = interp(b, c)
        cd = interp(c, d)
        da = interp(d, a)
        # Edges per case (standard table).
        table: Dict[int, List[Tuple[Vec3, Vec3]]] = {
            1: [(da, ab)],
            2: [(ab, bc)],
            3: [(da, bc)],
            4: [(bc, cd)],
            5: [(da, ab), (bc, cd)],   # ambiguous; pick one of the two splits
            6: [(ab, cd)],
            7: [(da, cd)],
            8: [(cd, da)],
            9: [(cd, ab)],
            10: [(ab, bc), (cd, da)],  # ambiguous
            11: [(bc, cd)],            # complement of 4
            12: [(da, bc)],            # complement of 3
            13: [(ab, bc)],            # complement of 2
            14: [(da, ab)],            # complement of 1
        }
        return table.get(code, [])

    # --------------------------------------------- scene-object primitives

    def _collect_scene_primitives(
        self,
        snapshots: List[Dict[int, Vec3]],
        turn_index: int,
        frame_in_turn: int,
    ) -> List[Tuple[float, Callable[[], None]]]:
        prims: List[Tuple[float, Callable[[], None]]] = []
        cx, cy = self._scene_centre()
        assert self._camera is not None

        if turn_index == 0:
            current = snapshots[0]
            target_snapshot = snapshots[0]
            t = 0.0
        else:
            current = snapshots[turn_index - 1]
            target_snapshot = snapshots[turn_index]
            t = min(1.0, frame_in_turn / self.frames_per_turn)

        # Connections (luminous shipping lanes).
        for conn in self.graph.connections:
            pa = self._world.get(conn.zone_a.name)
            pb = self._world.get(conn.zone_b.name)
            if pa is None or pb is None:
                continue
            mid = ((pa[0] + pb[0]) / 2.0,
                   (pa[1] + pb[1]) / 2.0,
                   (pa[2] + pb[2]) / 2.0)
            depth = self._depth_of(mid)
            if depth is None:
                continue
            prims.append((depth + 1.0,
                          self._make_connection_drawer(conn, pa, pb)))

        # Zones (mooring pylon + floating buoy with name plate).
        for zone in self.graph.zones:
            pos = self._world.get(zone.name)
            if pos is None:
                continue
            depth = self._depth_of(pos)
            if depth is None:
                continue
            prims.append((depth - 5.0,
                          self._make_zone_drawer(zone, pos)))

        # Drones (with ground shadow).
        for drone_id in range(1, self.graph.nb_drones + 1):
            start = current.get(drone_id, snapshots[0][drone_id])
            end = target_snapshot.get(drone_id, start)
            world = (
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
                start[2] + (end[2] - start[2]) * t,
            )
            depth = self._depth_of(world)
            if depth is None:
                continue
            shadow_depth = self._depth_of(
                (world[0], self._mesh_max_y + 2.0, world[2])
            )
            if shadow_depth is not None:
                prims.append((shadow_depth + 0.5,
                              self._make_shadow_drawer(world)))
            prims.append((depth - 8.0,
                          self._make_drone_drawer(drone_id, world)))
        return prims

    def _depth_of(self, world: Vec3) -> Optional[float]:
        if self._camera is None:
            return None
        cx, cy = self._scene_centre()
        proj = self._camera.project(world, cx, cy)
        return None if proj is None else proj[2]

    # --------------------------------------------------------- factories

    def _make_connection_drawer(
        self, conn: Any, pa: Vec3, pb: Vec3,
    ) -> Callable[[], None]:
        def draw() -> None:
            pg = self._pygame
            cx, cy = self._scene_centre()
            assert self._camera is not None
            a = self._camera.project(pa, cx, cy)
            b = self._camera.project(pb, cx, cy)
            if a is None or b is None:
                return
            base = (110, 200, 220)
            highlight = (200, 240, 250)
            width = 1 + min(conn.max_link_capacity, 4)
            pg.draw.line(self._screen, base, (a[0], a[1]), (b[0], b[1]),
                         width + 2)
            pg.draw.line(self._screen, highlight, (a[0], a[1]),
                         (b[0], b[1]), max(1, width - 1))
        return draw

    def _make_zone_drawer(self, zone: Zone, pos: Vec3) -> Callable[[], None]:
        def draw() -> None:
            pg = self._pygame
            cx, cy = self._scene_centre()
            assert self._camera is not None
            # Anchor on the seafloor directly under the zone.
            anchor_y = self._terrain_height_at(pos[0], pos[2])
            anchor = (pos[0], anchor_y, pos[2])
            ap = self._camera.project(anchor, cx, cy)
            zp = self._camera.project(pos, cx, cy)
            if ap is None or zp is None:
                return
            # Mooring pylon.
            pg.draw.line(self._screen, PYLON_COLOUR,
                         (ap[0], ap[1]), (zp[0], zp[1]), 2)
            # Buoy halo + body.
            radius = max(8, int(28 * 700 / max(zp[2], 200)))
            halo = pg.Surface((radius * 4, radius * 4), pg.SRCALPHA)
            pg.draw.circle(halo, (*BUOY_HALO, 60), (radius * 2, radius * 2),
                           radius * 2)
            pg.draw.circle(halo, (*BUOY_HALO, 110), (radius * 2, radius * 2),
                           int(radius * 1.4))
            self._screen.blit(halo, (zp[0] - radius * 2, zp[1] - radius * 2))
            fill = self._zone_fill(zone)
            outline = (255, 255, 255) if zone.is_terminal else (20, 30, 50)
            pg.draw.circle(self._screen, fill, (zp[0], zp[1]), radius)
            pg.draw.circle(self._screen, outline, (zp[0], zp[1]), radius, 2)
            # Anchor disc on seafloor.
            anchor_r = max(3, int(radius * 0.45))
            pg.draw.circle(self._screen, (20, 50, 70),
                           (ap[0], ap[1]), anchor_r)
            pg.draw.circle(self._screen, PYLON_COLOUR,
                           (ap[0], ap[1]), anchor_r, 1)
            # Name plate.
            label = self._font_small.render(zone.name, True, (15, 20, 30))
            self._screen.blit(label,
                              (zp[0] - label.get_width() // 2,
                               zp[1] - label.get_height() // 2))
            # Capacity tag.
            if zone.max_drones > 1:
                cap = self._font_small.render(
                    f"x{zone.max_drones}", True, (240, 240, 250)
                )
                self._screen.blit(cap, (zp[0] + radius - 4,
                                        zp[1] - radius - 14))
            # Depth read-out.
            depth_m = self._world_depth_label(pos[1])
            dlabel = self._font_tiny.render(depth_m, True, (180, 220, 235))
            self._screen.blit(dlabel,
                              (zp[0] - dlabel.get_width() // 2,
                               zp[1] + radius + 2))
            if zone.is_start:
                self._badge("START", zp[0], zp[1] + radius + 16,
                            (110, 240, 160))
            elif zone.is_end:
                self._badge("END", zp[0], zp[1] + radius + 16,
                            (250, 130, 130))
        return draw

    def _make_drone_drawer(
        self, drone_id: int, world: Vec3
    ) -> Callable[[], None]:
        def draw() -> None:
            pg = self._pygame
            cx, cy = self._scene_centre()
            assert self._camera is not None
            proj = self._camera.project(world, cx, cy)
            if proj is None:
                return
            x, y, depth = proj
            scale = max(0.4, min(2.2, 700.0 / max(depth, 200.0)))
            if self._sprites:
                sprite = self._sprites[(drone_id - 1) % len(self._sprites)]
                size = max(14, int(36 * scale))
                scaled = pg.transform.smoothscale(sprite, (size, size))
                rect = scaled.get_rect(center=(x, y))
                self._screen.blit(scaled, rect)
            else:
                self._draw_submarine(drone_id, x, y, scale)
        return draw

    def _make_shadow_drawer(self, world: Vec3) -> Callable[[], None]:
        def draw() -> None:
            pg = self._pygame
            cx, cy = self._scene_centre()
            assert self._camera is not None
            ground_y = self._terrain_height_at(world[0], world[2])
            proj = self._camera.project((world[0], ground_y + 1.0, world[2]),
                                        cx, cy)
            if proj is None:
                return
            x, y, depth = proj
            scale = max(0.4, min(2.2, 700.0 / max(depth, 200.0)))
            r = max(4, int(16 * scale))
            shadow = pg.Surface((r * 4, r * 2), pg.SRCALPHA)
            pg.draw.ellipse(shadow, (0, 0, 0, 110), shadow.get_rect())
            self._screen.blit(shadow, (x - r * 2, y - r))
        return draw

    def _draw_submarine(
        self, drone_id: int, x: int, y: int, scale: float,
    ) -> None:
        pg = self._pygame
        body_w = max(14, int(28 * scale))
        body_h = max(8, int(14 * scale))
        body_colour = DRONE_FALLBACK_COLOURS[
            (drone_id - 1) % len(DRONE_FALLBACK_COLOURS)
        ]
        # Soft halo so it pops against the dark water.
        halo = pg.Surface((body_w * 4, body_h * 4), pg.SRCALPHA)
        pg.draw.ellipse(halo, (255, 230, 130, 60), halo.get_rect())
        self._screen.blit(halo, (x - body_w * 2, y - body_h * 2))
        # Hull (ellipse).
        rect = self._pygame.Rect(x - body_w // 2, y - body_h // 2,
                                 body_w, body_h)
        pg.draw.ellipse(self._screen, body_colour, rect)
        pg.draw.ellipse(self._screen, (20, 30, 45), rect, 2)
        # Conning tower.
        tower_w = max(4, body_w // 4)
        tower_h = max(3, body_h // 2)
        tower = self._pygame.Rect(x - tower_w // 2,
                                  y - body_h // 2 - tower_h + 2,
                                  tower_w, tower_h)
        pg.draw.ellipse(self._screen, body_colour, tower)
        pg.draw.ellipse(self._screen, (20, 30, 45), tower, 1)
        # Running lights (front white, rear red).
        front_x = x + body_w // 2 - 2
        rear_x = x - body_w // 2 + 2
        pg.draw.circle(self._screen, (255, 245, 200), (front_x, y), 2)
        pg.draw.circle(self._screen, (255, 90, 90), (rear_x, y), 2)
        # Label.
        label = self._font_small.render(f"D{drone_id}", True, (15, 20, 30))
        self._screen.blit(label,
                          (x - label.get_width() // 2,
                           y - label.get_height() // 2))

    # ------------------------------------------------- helpers / lookups

    def _terrain_height_at(self, x: float, z: float) -> float:
        """Bilinear sample of the heightfield at world (x, z)."""
        if not self._mesh:
            return self.SEAFLOOR_OFFSET
        res = self.TERRAIN_RES
        half = self._scene_extent * 0.95
        step = (2 * half) / res
        fx = (x + half) / step
        fz = (z + half) / step
        ix = int(max(0, min(res - 1, math.floor(fx))))
        iz = int(max(0, min(res - 1, math.floor(fz))))
        tx = max(0.0, min(1.0, fx - ix))
        tz = max(0.0, min(1.0, fz - iz))
        a = self._mesh[ix][iz][1]
        b = self._mesh[ix + 1][iz][1]
        c = self._mesh[ix + 1][iz + 1][1]
        d = self._mesh[ix][iz + 1][1]
        ab = a + (b - a) * tx
        dc = d + (c - d) * tx
        return ab + (dc - ab) * tz

    def _zone_fill(self, zone: Zone) -> ColourRGB:
        if zone.color and zone.color.lower() in NAMED_COLOURS:
            return NAMED_COLOURS[zone.color.lower()]
        return DEFAULT_ZONE_FILL[zone.zone_type]

    @staticmethod
    def _world_depth_label(world_y: float) -> str:
        # Convert world Y to a depth in pseudo-metres for the chart feel.
        depth = -int(world_y * 0.5)
        return f"-{depth} m" if depth >= 0 else f"+{-depth} m"

    # ---------------------------------------------------- HUD / sidebar

    def _badge(
        self, text: str, x: int, y: int, colour: ColourRGB,
    ) -> None:
        label = self._font_small.render(text, True, colour)
        self._screen.blit(label, (x - label.get_width() // 2, y))

    def _draw_hud(self, turn_index: int, playing: bool) -> None:
        pg = self._pygame
        bar = pg.Rect(0, 0, self.WIN_W, self.HUD_H)
        pg.draw.rect(self._screen, (16, 28, 40), bar)
        pg.draw.line(self._screen, (50, 95, 130),
                     (0, self.HUD_H), (self.WIN_W, self.HUD_H), 2)
        info = (
            f"Turn {turn_index}/{len(self.reports)}    "
            f"Drones {self.graph.nb_drones}    "
            f"Speed {self.frames_per_turn} f/turn    "
            f"[{'PLAYING' if playing else 'PAUSED'}]"
        )
        label = self._font.render(info, True, (220, 235, 245))
        self._screen.blit(label, (16, 14))
        keys = (
            "SPACE play/pause   ← →  step   R restart   + - speed   "
            "G grid   C contours   drag rotate   wheel zoom   ESC quit"
        )
        klabel = self._font_small.render(keys, True, (150, 195, 220))
        self._screen.blit(klabel, (16, self.HUD_H - 22))

    def _draw_compass(self) -> None:
        """Compass rose, North rotates with the inverse of camera yaw."""
        if self._camera is None:
            return
        pg = self._pygame
        cx = self.WIN_W - self.SIDEBAR_W - 70
        cy = self.HUD_H + 70
        radius = 42
        pg.draw.circle(self._screen, (12, 26, 44, 200), (cx, cy),
                       radius + 4)
        pg.draw.circle(self._screen, (60, 130, 170), (cx, cy), radius, 2)
        pg.draw.circle(self._screen, (60, 130, 170), (cx, cy),
                       radius // 2, 1)
        yaw = self._camera.yaw
        # Cardinals (N at -yaw).
        for label_text, angle in (("N", 0), ("E", math.pi / 2),
                                  ("S", math.pi), ("W", -math.pi / 2)):
            a = angle - yaw
            x = cx + math.sin(a) * (radius - 6)
            y = cy - math.cos(a) * (radius - 6)
            label = self._font_small.render(
                label_text, True,
                (235, 220, 110) if label_text == "N" else (180, 220, 235),
            )
            self._screen.blit(label,
                              (x - label.get_width() // 2,
                               y - label.get_height() // 2))
        # North needle.
        a = -yaw
        nx = cx + math.sin(a) * (radius - 14)
        ny = cy - math.cos(a) * (radius - 14)
        pg.draw.line(self._screen, (240, 210, 100),
                     (cx, cy), (nx, ny), 2)
        pg.draw.circle(self._screen, (240, 210, 100), (cx, cy), 3)

    def _draw_sidebar(self, turn_index: int) -> None:
        pg = self._pygame
        x0 = self.WIN_W - self.SIDEBAR_W
        bar = pg.Rect(x0, self.HUD_H, self.SIDEBAR_W, self.WIN_H - self.HUD_H)
        pg.draw.rect(self._screen, (12, 22, 34), bar)
        pg.draw.line(self._screen, (50, 95, 130),
                     (x0, self.HUD_H), (x0, self.WIN_H), 2)
        y = self.HUD_H + 16

        def write(text: str,
                  colour: ColourRGB = (210, 230, 240)) -> None:
            nonlocal y
            label = self._font.render(text, True, colour)
            self._screen.blit(label, (x0 + 16, y))
            y += label.get_height() + 4

        write("Chart", (235, 245, 255))
        write(f"  drones    : {self.graph.nb_drones}")
        write(f"  zones     : {sum(1 for _ in self.graph.zones)}")
        write(f"  edges     : {sum(1 for _ in self.graph.connections)}")
        write(f"  total turn: {len(self.reports)}")
        y += 12

        # Depth scale.
        write("Depth scale", (235, 245, 255))
        scale_x = x0 + 16
        scale_w = 20
        scale_h = 180
        bands = 40
        for i in range(bands):
            t = 1.0 - i / max(bands - 1, 1)
            y_world = self._mesh_min_y + (self._mesh_max_y - self._mesh_min_y) * t
            colour = _depth_colour(y_world, self._mesh_min_y, self._mesh_max_y)
            band_y = y + int(i * (scale_h / bands))
            band_h = max(1, int(scale_h / bands) + 1)
            pg.draw.rect(self._screen, colour,
                         pg.Rect(scale_x, band_y, scale_w, band_h))
        pg.draw.rect(self._screen, (60, 130, 170),
                     pg.Rect(scale_x, y, scale_w, scale_h), 1)
        top_lbl = self._font_tiny.render(
            self._world_depth_label(self._mesh_max_y), True,
            (200, 230, 245),
        )
        bot_lbl = self._font_tiny.render(
            self._world_depth_label(self._mesh_min_y), True,
            (200, 230, 245),
        )
        self._screen.blit(top_lbl, (scale_x + scale_w + 8, y - 2))
        self._screen.blit(bot_lbl,
                          (scale_x + scale_w + 8, y + scale_h - 10))
        y += scale_h + 16

        write("Last moves", (235, 245, 255))
        if 1 <= turn_index <= len(self.reports):
            line = self.reports[turn_index - 1].render()
            self._render_wrapped(line, x0 + 16, y, self.SIDEBAR_W - 32,
                                 (185, 230, 215))
        else:
            write("  (start of sim)", (150, 175, 195))

    def _render_wrapped(
        self,
        text: str,
        x: int,
        y: int,
        max_width: int,
        colour: ColourRGB,
    ) -> None:
        tokens = text.split(" ")
        line = ""
        cur_y = y
        for tok in tokens:
            attempt = (line + " " + tok).strip()
            surf = self._font_small.render(attempt, True, colour)
            if surf.get_width() > max_width and line:
                self._screen.blit(self._font_small.render(line, True, colour),
                                  (x, cur_y))
                cur_y += surf.get_height() + 2
                line = tok
            else:
                line = attempt
        if line:
            self._screen.blit(self._font_small.render(line, True, colour),
                              (x, cur_y))
