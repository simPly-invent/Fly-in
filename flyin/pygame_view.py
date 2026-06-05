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

BATHY_STOPS: List[Tuple[float, ColourRGB]] = [
    (0.00, (4, 12, 30)),
    (0.20, (8, 26, 60)),
    (0.45, (18, 58, 96)),
    (0.65, (40, 110, 138)),
    (0.82, (90, 165, 175)),
    (1.00, (170, 190, 150)),
]

WATER_TOP: ColourRGB = (24, 56, 90)
WATER_BOTTOM: ColourRGB = (4, 10, 22)
CONTOUR_COLOUR: ColourRGB = (90, 210, 230)
CONTOUR_DIM: ColourRGB = (40, 120, 145)
GRID_COLOUR: ColourRGB = (45, 95, 130)
PYLON_COLOUR: ColourRGB = (160, 215, 230)
BUOY_HALO: ColourRGB = (255, 220, 130)
LIGHT_DIR: Vec3 = (0.35, 0.85, 0.40)

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
    # - Clamp t dans [0, 1].
    # - Pour chaque composante (r, g, b): result = int(a + (b - a) * t).
    # - Retourner le triplet.
    raise NotImplementedError("À implémenter")


def _depth_colour(height: float, y_min: float, y_max: float) -> ColourRGB:
    # - Si (y_max - y_min) < 1e-6 → t = 0.5.
    # - Sinon t = (height - y_min) / (y_max - y_min), clampé dans [0, 1].
    # - Parcourir BATHY_STOPS deux à deux (i, i+1):
    #     - Si t0 <= t <= t1 → local = (t - t0) / (t1 - t0) (ou 0 si égaux) ;
    #       retourner _lerp_colour(c0, c1, local).
    # - Fallback: retourner BATHY_STOPS[-1][1].
    raise NotImplementedError("À implémenter")


def _normalize(v: Vec3) -> Vec3:
    # - n = sqrt(v[0]^2 + v[1]^2 + v[2]^2).
    # - Si n < 1e-9 → retourner (0, 1, 0) (default up).
    # - Sinon retourner (v[0]/n, v[1]/n, v[2]/n).
    raise NotImplementedError("À implémenter")


def _cross(a: Vec3, b: Vec3) -> Vec3:
    # - Retourner le produit vectoriel (a1*b2-a2*b1, a2*b0-a0*b2, a0*b1-a1*b0).
    raise NotImplementedError("À implémenter")


def _shade(normal: Vec3, base: ColourRGB) -> ColourRGB:
    # Lambertien avec ambient:
    # - n = _normalize(normal) ; light = _normalize(LIGHT_DIR).
    # - lambert = max(0, dot(n, light)).
    # - factor = 0.45 + 0.55 * lambert.
    # - Retourner chaque composante clampée dans [0, 255]: int(base_i * factor).
    raise NotImplementedError("À implémenter")


# ------------------------------------------------------------------ camera


class Camera3D:
    """Orbit camera with hand-rolled perspective projection."""

    def __init__(self, target: Vec3, distance: float) -> None:
        # - Stocker target, distance.
        # - yaw = radians(35), pitch = radians(-32).
        # - focal = 900.0 (longueur focale en pixels).
        # - min_distance/max_distance = 200/9000 ; min_pitch/max_pitch = ±radians(85).
        raise NotImplementedError("À implémenter")

    def rotate(self, delta_yaw: float, delta_pitch: float) -> None:
        # - yaw = (yaw + delta_yaw) mod 2π.
        # - pitch = clamp(pitch + delta_pitch, min_pitch, max_pitch).
        raise NotImplementedError("À implémenter")

    def zoom(self, factor: float) -> None:
        # - distance = clamp(distance * factor, min_distance, max_distance).
        raise NotImplementedError("À implémenter")

    def pan(self, dx: float, dy: float) -> None:
        # - right, up, _ = self._basis().
        # - scale = distance / focal.
        # - target = target + (right * dx + up * dy) * scale (composante par composante).
        raise NotImplementedError("À implémenter")

    def _basis(self) -> Tuple[Vec3, Vec3, Vec3]:
        # - cy, sy = cos(yaw), sin(yaw).
        # - cp, sp = cos(pitch), sin(pitch).
        # - forward = (sy*cp, -sp, cy*cp).
        # - right = (cy, 0, -sy).
        # - up = _cross(right, forward).
        # - Retourner (right, up, forward).
        raise NotImplementedError("À implémenter")

    def project(
        self,
        world: Vec3,
        screen_cx: float,
        screen_cy: float,
    ) -> Optional[Tuple[int, int, float]]:
        # - right, up, forward = self._basis().
        # - cam_pos = target - forward * distance.
        # - rel = world - cam_pos.
        # - x_cam = dot(rel, right) ; y_cam = dot(rel, up) ; z_cam = dot(rel, forward).
        # - Si z_cam <= 1.0 → None (point derrière la cam ou trop proche).
        # - sx = x_cam * focal / z_cam + screen_cx.
        # - sy = -y_cam * focal / z_cam + screen_cy.
        # - Retourner (int(sx), int(sy), z_cam).
        raise NotImplementedError("À implémenter")


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

    UNIT: float = 130.0
    SEAFLOOR_OFFSET: float = -90.0
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
        # - Stocker graph, simulator, paths, reports, title.
        # - frames_per_turn = DEFAULT_FRAMES_PER_TURN.
        # - show_grid = True ; contour_density = 1.
        # - Initialiser à None: _pygame, _screen, _font, _font_small, _font_tiny, _clock.
        # - _sprites = [] ; _world: Dict[str, Vec3] = {}.
        # - _scene_extent = 1000.0 ; _camera = None.
        # - _mesh = [] ; _mesh_min_y = 0.0 ; _mesh_max_y = 0.0.
        raise NotImplementedError("À implémenter")

    # --------------------------------------------------------------- setup

    def _import_pygame(self) -> Any:
        # - try: import pygame ; return pygame.
        # - except ImportError → lever PygameUnavailableError(...).
        raise NotImplementedError("À implémenter")

    def _setup(self) -> None:
        # - pg = self._pygame ; pg.init() ; pg.display.set_caption(title).
        # - _screen = pg.display.set_mode((WIN_W, WIN_H)).
        # - _clock = pg.time.Clock().
        # - Init fonts (dejavusansmono): 16 / 12 / 10.
        # - _build_world() ; _build_terrain() ; _init_camera() ; _load_sprites().
        raise NotImplementedError("À implémenter")

    def _build_world(self) -> None:
        # - Récupérer la liste des zones ; si vide → return.
        # - Calculer x_mid, y_mid (centre) à partir des coords.
        # - Pour chaque zone:
        #     - world_x = (zone.x - x_mid) * UNIT
        #     - world_z = (zone.y - y_mid) * UNIT
        #     - world_y = ELEVATION[zone.zone_type]
        #     - Stocker dans self._world[zone.name].
        # - Calculer scene_extent = max(x_span, z_span).
        raise NotImplementedError("À implémenter")

    def _build_terrain(self) -> None:
        # Heightfield IDW:
        # - res = TERRAIN_RES ; half = scene_extent * 0.95 ; step = 2*half/res.
        # - power = 1.6 ; reach2 = (UNIT * 1.6)**2.
        # - Pour ix dans [0, res] et iz dans [0, res]:
        #     - x = -half + ix*step ; z = -half + iz*step.
        #     - Pour chaque zone: d2 = (wp_x - x)^2 + (wp_z - z)^2 + reach2*0.05 ;
        #         w = 1 / d2^power ; accumuler total_w et total_y (pondéré).
        #     - base = total_y / total_w (ou 0).
        #     - noise = sin(x*0.011)*8 + cos(z*0.013)*6 + sin((x+z)*0.007)*4.
        #     - y = base + noise + SEAFLOOR_OFFSET.
        #     - Stocker (x, y, z) ; mettre à jour y_min/y_max.
        # - Stocker _mesh, _mesh_min_y (-20 marge), _mesh_max_y (+5 marge).
        raise NotImplementedError("À implémenter")

    def _init_camera(self) -> None:
        # - _camera = Camera3D(target=(0,0,0), distance=max(scene_extent * 2.0, 800)).
        raise NotImplementedError("À implémenter")

    def _load_sprites(self) -> None:
        # - Si ASSETS_DIR n'est pas un dossier → _sprites = [] ; return.
        # - Lister les fichiers triés dont l'extension est dans SPRITE_EXTENSIONS.
        # - Pour chaque path: try pg.image.load(...).convert_alpha() ; append.
        #     - Catch pg.error / OSError → skip.
        # - Stocker _sprites.
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        # - _pygame = self._import_pygame().
        # - try: _setup() ; _loop().
        # - finally: _pygame.quit().
        raise NotImplementedError("À implémenter")

    # --------------------------------------------------------- snapshots

    def _build_snapshots(self) -> List[Dict[int, Vec3]]:
        # - start_pos = _world[graph.start.name] ; n = nb_drones.
        # - positions = {i: _fan_offset(start_pos, i, n) for i in 1..n}.
        # - snapshots = [dict(positions)].
        # - Pour chaque report (turn):
        #     - new_positions = dict(positions).
        #     - Pour chaque move: extraire drone_id depuis "Dxx" ;
        #         target = _resolve_destination(move.destination).
        #         Si non None → new_positions[drone_id] = target.
        #     - positions = new_positions ; snapshots.append(dict(positions)).
        # - Retourner snapshots.
        raise NotImplementedError("À implémenter")

    def _resolve_destination(self, destination: str) -> Optional[Vec3]:
        # - Si "-" dans destination:
        #     - parts = split("-", 2 parts) ; si les deux sont des zones connues → midpoint
        #       (avec +DRONE_ALTITUDE en Y) ; retourner cette position.
        # - Sinon si graph.has_zone(destination):
        #     - base = _world[destination] ; retourner (x, y + DRONE_ALTITUDE, z).
        # - Sinon retourner None.
        raise NotImplementedError("À implémenter")

    def _fan_offset(self, base: Vec3, index: int, total: int) -> Vec3:
        # - Si total <= 1 → (x, y + DRONE_ALTITUDE, z).
        # - Sinon radius = 30 ; angle = 2π * (index - 1) / total.
        # - Retourner (x + radius*cos, y + DRONE_ALTITUDE, z + radius*sin).
        raise NotImplementedError("À implémenter")

    # --------------------------------------------------------- main loop

    def _loop(self) -> None:
        # - playing = False ; turn_index = 0 ; frame_in_turn = 0.
        # - snapshots = _build_snapshots() ; total_turns = len(reports).
        # - dragging_orbit/dragging_pan = False ; last_mouse = None.
        # - running = True ; tant que running:
        #     - Pour chaque event pg.event.get():
        #         QUIT → running=False.
        #         KEYDOWN:
        #             ESC → quit ; SPACE → toggle play ; LEFT/RIGHT → step ;
        #             R → restart ; +/- → ajuster frames_per_turn ;
        #             G → toggle grid ; C → cycle contour_density (%3).
        #         MOUSEBUTTONDOWN: bouton 1 → orbit ; bouton 2 → pan ;
        #             wheel up/down → camera.zoom(0.9/1.1).
        #         MOUSEBUTTONUP → arrêter le drag.
        #         MOUSEMOTION + drag → camera.rotate(dx*0.008, -dy*0.008) ou pan(-dx, dy).
        #     - Si playing et turn_index < total: frame_in_turn += 1 ;
        #         si == frames_per_turn → tick turn (avec clamp final).
        #     - _render_frame(...) ; _clock.tick(FPS).
        raise NotImplementedError("À implémenter")

    # ----------------------------------------------------------- rendering

    def _scene_centre(self) -> Tuple[float, float]:
        # - cx = (WIN_W - SIDEBAR_W) / 2.
        # - cy = HUD_H + (WIN_H - HUD_H) / 2.
        # - Retourner (cx, cy).
        raise NotImplementedError("À implémenter")

    def _render_frame(
        self,
        snapshots: List[Dict[int, Vec3]],
        turn_index: int,
        frame_in_turn: int,
        playing: bool,
    ) -> None:
        # - _screen.fill(WATER_BOTTOM) ; _draw_water_column().
        # - prims = _collect_terrain_primitives() + _collect_scene_primitives(...).
        # - prims.sort(key=lambda p: -p[0]) — far first (depth-sort manuel).
        # - Pour chaque (_, draw) → draw().
        # - _draw_hud(turn_index, playing) ; _draw_sidebar(turn_index) ; _draw_compass().
        # - pg.display.flip().
        raise NotImplementedError("À implémenter")

    def _draw_water_column(self) -> None:
        # - h = WIN_H - HUD_H ; w = WIN_W - SIDEBAR_W.
        # - Pour i dans [0, h):
        #     - t = i / (h-1).
        #     - colour = _lerp_colour(WATER_TOP, WATER_BOTTOM, t).
        #     - pg.draw.line(_screen, colour, (0, HUD_H+i), (w, HUD_H+i)).
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------- terrain primitives

    def _collect_terrain_primitives(self) -> List[Tuple[float, Callable[[], None]]]:
        # - Si _mesh vide ou _camera None → [].
        # - prims = [] ; cx, cy = _scene_centre() ; res = TERRAIN_RES.
        # - Pour chaque cellule du heightfield (ix, iz):
        #     - quad = a, b, c, d (4 coins).
        #     - _maybe_add_triangle(prims, a, b, c, ...) et (a, c, d, ...).
        # - Si show_grid: ajouter chaque ligne du quad comme _line_primitive(GRID_COLOUR, 1).
        # - Si contour_density > 0: prims.extend(_collect_contours()).
        # - Retourner prims.
        raise NotImplementedError("À implémenter")

    def _maybe_add_triangle(
        self,
        out: List[Tuple[float, Callable[[], None]]],
        a: Vec3,
        b: Vec3,
        c: Vec3,
        cx: float,
        cy: float,
    ) -> None:
        # - pa/pb/pc = _camera.project(...) ; si l'un est None → return.
        # - u = b - a ; v = c - a ; n = _cross(u, v).
        # - Si n[1] < 0 → flip n pour orienter "up".
        # - avg_y = (a[1]+b[1]+c[1]) / 3.
        # - base = _depth_colour(avg_y, _mesh_min_y, _mesh_max_y).
        # - colour = _shade(n, base).
        # - avg_depth = (pa[2]+pb[2]+pc[2]) / 3.
        # - points = [(pa[0], pa[1]), ...].
        # - draw closure: pg.draw.polygon(_screen, colour, points).
        # - out.append((avg_depth, draw)).
        raise NotImplementedError("À implémenter")

    def _line_primitive(
        self,
        a: Vec3,
        b: Vec3,
        colour: ColourRGB,
        width: int,
    ) -> Tuple[float, Callable[[], None]]:
        # - cx, cy = _scene_centre().
        # - pa = camera.project(a, ...) ; pb = camera.project(b, ...).
        # - draw closure: si pa/pb None → return ; sinon pg.draw.line(...).
        # - Si pa ou pb None → retourner (0.0, draw).
        # - Sinon retourner ((pa[2]+pb[2])/2 - 1.0, draw) — léger biais pour passer DEVANT les triangles.
        raise NotImplementedError("À implémenter")

    def _collect_contours(self) -> List[Tuple[float, Callable[[], None]]]:
        # - Si _mesh vide → [].
        # - res = TERRAIN_RES ; span = max(max_y - min_y, ε).
        # - n_levels = (0, 6, 14)[contour_density].
        # - Pour chaque k dans [1, n_levels):
        #     - level = min_y + span * (k / n_levels).
        #     - major = (k % 2 == 0) → couleur/largeur ajustés (CONTOUR_COLOUR/2 sinon CONTOUR_DIM/1).
        #     - Pour chaque cellule (ix, iz) du mesh:
        #         - segs = _marching_square(a, b, c, d, level).
        #         - Pour chaque (p, q) → prims.append(_line_primitive(p, q, colour, width)).
        # - Retourner prims.
        raise NotImplementedError("À implémenter")

    @staticmethod
    def _marching_square(
        a: Vec3, b: Vec3, c: Vec3, d: Vec3, level: float
    ) -> List[Tuple[Vec3, Vec3]]:
        # - Calculer code 0..15 selon quels coins (ABCD) sont au-dessus de level (bit 1,2,4,8).
        # - Si code in (0, 15) → [] (pas d'intersection).
        # - Helper interp(p, q): t = (level - yp) / (yq - yp) (0.5 si plat) ;
        #     retourner (interp x, level, interp z).
        # - ab, bc, cd, da = interpolations sur les 4 arêtes.
        # - Table des 16 cas standards de marching squares:
        #     1: [(da, ab)] / 2: [(ab, bc)] / 3: [(da, bc)] / 4: [(bc, cd)] / ...
        #     14: [(da, ab)] (complément du cas 1).
        # - Retourner table.get(code, []).
        raise NotImplementedError("À implémenter")

    # --------------------------------------------- scene-object primitives

    def _collect_scene_primitives(
        self,
        snapshots: List[Dict[int, Vec3]],
        turn_index: int,
        frame_in_turn: int,
    ) -> List[Tuple[float, Callable[[], None]]]:
        # - Si turn_index == 0 → current = target = snapshots[0] ; t = 0.
        # - Sinon current = snapshots[turn_index-1] ; target = snapshots[turn_index] ;
        #     t = min(1, frame_in_turn / frames_per_turn).
        # - Connexions: pour chaque conn, calculer midpoint et profondeur ;
        #     ajouter (depth + 1, _make_connection_drawer(...)).
        # - Zones: pour chaque zone, profondeur de sa position ;
        #     ajouter (depth - 5, _make_zone_drawer(...)).
        # - Drones: pour drone_id de 1 à nb_drones:
        #     - Interpoler position entre current[id] et target[id] selon t.
        #     - depth = _depth_of(world).
        #     - shadow_depth pour le sol → ajouter shadow_drawer.
        #     - drone_drawer avec (depth - 8, ...).
        # - Retourner prims.
        raise NotImplementedError("À implémenter")

    def _depth_of(self, world: Vec3) -> Optional[float]:
        # - Si _camera None → None.
        # - cx, cy = _scene_centre() ; proj = camera.project(...).
        # - Retourner None si proj None sinon proj[2] (z_eye).
        raise NotImplementedError("À implémenter")

    # --------------------------------------------------------- factories

    def _make_connection_drawer(
        self, conn: Any, pa: Vec3, pb: Vec3,
    ) -> Callable[[], None]:
        # Retourner une closure draw():
        # - Projeter pa/pb ; si None → return.
        # - width = 1 + min(conn.max_link_capacity, 4).
        # - Tracer 2 lignes superposées (base + highlight) pour effet luminescent.
        raise NotImplementedError("À implémenter")

    def _make_zone_drawer(self, zone: Zone, pos: Vec3) -> Callable[[], None]:
        # Retourner une closure draw():
        # - anchor_y = _terrain_height_at(pos[0], pos[2]) ; anchor = (x, anchor_y, z).
        # - Projeter anchor et pos ; si l'un None → return.
        # - Tracer le pylon (line PYLON_COLOUR).
        # - Dessiner halo + cercle de la bouée (taille proportionnelle à 700/depth).
        # - Couleur de remplissage via _zone_fill ; contour blanc si terminal sinon sombre.
        # - Disc d'ancrage au sol, name plate centré, capacité si > 1, depth read-out tiny.
        # - Badge "START" / "END" si applicable.
        raise NotImplementedError("À implémenter")

    def _make_drone_drawer(
        self, drone_id: int, world: Vec3
    ) -> Callable[[], None]:
        # Retourner une closure draw():
        # - proj = camera.project(world, ...) ; si None → return.
        # - scale = clamp(700 / depth, 0.4, 2.2).
        # - Si self._sprites: prendre sprite[(id-1) % len], scaler à 36*scale, blit.
        # - Sinon _draw_submarine(drone_id, x, y, scale) (fallback).
        raise NotImplementedError("À implémenter")

    def _make_shadow_drawer(self, world: Vec3) -> Callable[[], None]:
        # Retourner une closure draw():
        # - ground_y = _terrain_height_at(world[0], world[2]).
        # - Projeter (x, ground_y + 1, z) ; si None → return.
        # - scale comme pour le drone ; r = 16 * scale.
        # - Créer surface SRCALPHA et dessiner une ellipse noire semi-transparente.
        # - Blit centrée.
        raise NotImplementedError("À implémenter")

    def _draw_submarine(
        self, drone_id: int, x: int, y: int, scale: float,
    ) -> None:
        # - body_w/body_h proportionnels à scale.
        # - body_colour = DRONE_FALLBACK_COLOURS[(id-1) % len].
        # - Halo doux SRCALPHA derrière (effet luminescent).
        # - Hull = ellipse body_colour + contour sombre.
        # - Conning tower (petite ellipse au-dessus).
        # - Running lights: blanc à l'avant, rouge à l'arrière.
        # - Label "D<id>" centré.
        raise NotImplementedError("À implémenter")

    # ------------------------------------------------- helpers / lookups

    def _terrain_height_at(self, x: float, z: float) -> float:
        # Bilinéaire sur le heightfield:
        # - Si _mesh vide → SEAFLOOR_OFFSET.
        # - res = TERRAIN_RES ; half = scene_extent*0.95 ; step = 2*half/res.
        # - fx = (x + half) / step ; fz = (z + half) / step.
        # - ix/iz = floor clampé dans [0, res-1] ; tx/tz = fraction clampée [0,1].
        # - a/b/c/d = mesh[ix][iz][1] etc. (4 hauteurs aux coins).
        # - ab = a + (b - a)*tx ; dc = d + (c - d)*tx.
        # - Retourner ab + (dc - ab)*tz.
        raise NotImplementedError("À implémenter")

    def _zone_fill(self, zone: Zone) -> ColourRGB:
        # - Si zone.color en lowercase est dans NAMED_COLOURS → retourner cette couleur.
        # - Sinon retourner DEFAULT_ZONE_FILL[zone.zone_type].
        raise NotImplementedError("À implémenter")

    @staticmethod
    def _world_depth_label(world_y: float) -> str:
        # - depth = -int(world_y * 0.5) (pseudo-mètres).
        # - Si depth >= 0 → f"-{depth} m" sinon f"+{-depth} m".
        raise NotImplementedError("À implémenter")

    # ---------------------------------------------------- HUD / sidebar

    def _badge(
        self, text: str, x: int, y: int, colour: ColourRGB,
    ) -> None:
        # - label = font_small.render(text, True, colour).
        # - blit centré horizontalement à (x, y).
        raise NotImplementedError("À implémenter")

    def _draw_hud(self, turn_index: int, playing: bool) -> None:
        # - bar = Rect(0, 0, WIN_W, HUD_H) ; remplir en (16,28,40) avec ligne séparatrice (50,95,130).
        # - info = "Turn X/Y  Drones N  Speed F f/turn  [PLAYING|PAUSED]".
        # - Blit info en (16, 14).
        # - keys = "SPACE play/pause ... ESC quit" en font_small en bas du HUD.
        raise NotImplementedError("À implémenter")

    def _draw_compass(self) -> None:
        # - Si _camera None → return.
        # - Centre = (WIN_W - SIDEBAR_W - 70, HUD_H + 70) ; radius = 42.
        # - Dessiner cercle de fond + 2 cercles concentriques.
        # - yaw = camera.yaw.
        # - Cardinaux N/E/S/W positionnés selon (angle - yaw) ; N en jaune, autres bleu pâle.
        # - Aiguille nord: ligne (cx, cy) → (cx + sin(-yaw)*r, cy - cos(-yaw)*r) en jaune.
        raise NotImplementedError("À implémenter")

    def _draw_sidebar(self, turn_index: int) -> None:
        # - x0 = WIN_W - SIDEBAR_W ; remplir la bande de droite en (12,22,34).
        # - write helper qui blit ligne par ligne et avance y.
        # - Bloc "Chart": drones / zones / edges / total turn.
        # - Bloc "Depth scale": 40 bandes de couleurs (du max vers le min) + labels en haut/bas.
        # - Bloc "Last moves": render du report turn_index-1 avec _render_wrapped,
        #     ou "(start of sim)" si turn_index == 0.
        raise NotImplementedError("À implémenter")

    def _render_wrapped(
        self,
        text: str,
        x: int,
        y: int,
        max_width: int,
        colour: ColourRGB,
    ) -> None:
        # - tokens = text.split(" ") ; line = "" ; cur_y = y.
        # - Pour chaque token:
        #     - attempt = (line + " " + tok).strip().
        #     - Si attempt rendu dépasse max_width ET line non vide:
        #         - Blit ligne courante ; cur_y += hauteur + 2 ; line = tok.
        #     - Sinon line = attempt.
        # - Blit la dernière ligne.
        raise NotImplementedError("À implémenter")
