"""Map file parser.

Parses files of the form:

    nb_drones: 5

    start_hub: start 0 0 [color=green]
    end_hub: goal 10 10 [color=yellow]
    hub: roof1 3 4 [zone=restricted color=red]
    ...
    connection: hub-roof1
    connection: corridorA-tunnelB [max_link_capacity=2]

Comments start with '#' and are ignored. Blank lines are skipped. Any syntax
or semantic error stops parsing with an explanatory message including the
line number.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from flyin.graph import Graph
from flyin.network import Connection, Zone, ZoneType


class MapParseError(Exception):
    """Raised when a map file cannot be parsed or fails validation."""

    def __init__(self, message: str, line_no: Optional[int] = None) -> None:
        if line_no is not None:
            super().__init__(f"line {line_no}: {message}")
        else:
            super().__init__(message)
        self.line_no = line_no


_NAME_RE = re.compile(r"^[^\s\-]+$")
_METADATA_TOKEN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(\S+)$")


class MapParser:
    """Stateful parser that builds a Graph from a map file."""

    def __init__(self) -> None:
        self._nb_drones: Optional[int] = None
        self._graph: Optional[Graph] = None
        self._pending_zones: List[Tuple[int, str, List[str]]] = []
        self._pending_connections: List[Tuple[int, str, str, str]] = []

    def parse_file(self, path: Union[str, Path]) -> Graph:
        """Read the file at ``path`` and parse it into a validated ``Graph``."""
        file_path = Path(path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MapParseError(
                f"cannot read map file {file_path!s}: {exc}"
            ) from exc
        return self.parse_text(content)

    def parse_text(self, text: str) -> Graph:
        """Parse map text line by line and return a validated ``Graph``.

        Zones and connections are queued first so they can be built in two
        passes, letting connections reference zones declared further down.
        """
        self._reset()
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = self._strip_comment(raw).strip()
            if not line:
                continue
            self._dispatch(line_no, line)
        if self._nb_drones is None:
            raise MapParseError("missing 'nb_drones:' directive")
        self._graph = Graph(self._nb_drones)
        self._build_zones()
        self._build_connections()
        self._graph.validate()
        return self._graph

    def _reset(self) -> None:
        """Clear all parser state so the instance can be reused."""
        self._nb_drones = None
        self._graph = None
        self._pending_zones = []
        self._pending_connections = []

    @staticmethod
    def _strip_comment(line: str) -> str:
        """Return ``line`` truncated at the first ``#`` comment marker."""
        idx = line.find("#")
        if idx == -1:
            return line
        return line[:idx]

    def _dispatch(self, line_no: int, line: str) -> None:
        """Route a non-empty line to the handler for its directive keyword."""
        if line.startswith("nb_drones:"):
            self._parse_nb_drones(line_no, line)
        elif line.startswith("start_hub:"):
            self._queue_zone(line_no, line, prefix="start_hub:", role="start")
        elif line.startswith("end_hub:"):
            self._queue_zone(line_no, line, prefix="end_hub:", role="end")
        elif line.startswith("hub:"):
            self._queue_zone(line_no, line, prefix="hub:", role="hub")
        elif line.startswith("connection:"):
            self._queue_connection(line_no, line)
        else:
            raise MapParseError(f"unrecognized directive: {line!r}", line_no)

    def _parse_nb_drones(self, line_no: int, line: str) -> None:
        """Parse the ``nb_drones:`` directive into a positive integer."""
        if self._nb_drones is not None:
            raise MapParseError("duplicate 'nb_drones:'", line_no)
        payload = line[len("nb_drones:"):].strip()
        if not payload:
            raise MapParseError("nb_drones is missing a value", line_no)
        try:
            value = int(payload)
        except ValueError as exc:
            raise MapParseError(
                f"nb_drones is not an integer: {payload!r}", line_no
            ) from exc
        if value <= 0:
            raise MapParseError("nb_drones must be positive", line_no)
        elif value >= 1000:
            raise MapParseError("nb_drones must be less than 1000", line_no)
        self._nb_drones = value

    def _queue_zone(
        self, line_no: int, line: str, prefix: str, role: str
    ) -> None:
        """Validate a hub directive and queue it for the zone-building pass."""
        payload = line[len(prefix):].strip()
        tokens, metadata = self._split_metadata(line_no, payload)
        if len(tokens) != 3:
            raise MapParseError(
                f"{prefix} expects '<name> <x> <y>'", line_no
            )
        name, x_raw, y_raw = tokens
        self._validate_name(line_no, name)
        try:
            int(x_raw)
            int(y_raw)
        except ValueError as exc:
            raise MapParseError(
                f"zone coordinates must be integers: {x_raw!r} {y_raw!r}",
                line_no,
            ) from exc
        self._pending_zones.append(
            (line_no, role, [name, x_raw, y_raw, *metadata])
        )

    def _build_zones(self) -> None:
        """Turn queued zone directives into ``Zone`` objects on the graph."""
        assert self._graph is not None
        for line_no, role, fields in self._pending_zones:
            name = fields[0]
            x = int(fields[1])
            y = int(fields[2])
            meta = self._metadata_dict(line_no, fields[3:])
            zone_type = ZoneType.NORMAL
            if "zone" in meta:
                try:
                    zone_type = ZoneType.from_string(meta["zone"])
                except ValueError as exc:
                    raise MapParseError(str(exc), line_no) from exc
            color = meta.get("color")
            max_drones = self._parse_positive_int(
                line_no, meta.get("max_drones"), default=1, key="max_drones"
            )
            zone = Zone(
                name,
                x,
                y,
                zone_type=zone_type,
                color=color,
                max_drones=max_drones,
                is_start=(role == "start"),
                is_end=(role == "end"),
            )
            try:
                self._graph.add_zone(zone)
            except ValueError as exc:
                raise MapParseError(str(exc), line_no) from exc

    def _queue_connection(self, line_no: int, line: str) -> None:
        """Validate a ``connection:`` directive and queue it for building."""
        payload = line[len("connection:"):].strip()
        tokens, metadata = self._split_metadata(line_no, payload)
        if len(tokens) != 1:
            raise MapParseError(
                "connection expects '<zone1>-<zone2>'", line_no
            )
        parts = tokens[0].split("-")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise MapParseError(
                "invalid connection syntax (expected 'zone1-zone2')", line_no
            )
        name_a, name_b = parts
        self._validate_name(line_no, name_a)
        self._validate_name(line_no, name_b)
        if name_a == name_b:
            raise MapParseError("a connection cannot loop on itself", line_no)
        self._pending_connections.append(
            (line_no, name_a, name_b, " ".join(metadata))
        )

    def _build_connections(self) -> None:
        """Turn queued connections into edges, checking endpoints exist."""
        assert self._graph is not None
        for line_no, name_a, name_b, meta_str in self._pending_connections:
            for endpoint in (name_a, name_b):
                if not self._graph.has_zone(endpoint):
                    raise MapParseError(
                        f"connection references unknown zone {endpoint!r}",
                        line_no,
                    )
            zone_a = self._graph.get_zone(name_a)
            zone_b = self._graph.get_zone(name_b)
            meta_tokens = meta_str.split() if meta_str else []
            meta = self._metadata_dict(line_no, meta_tokens)
            max_link_capacity = self._parse_positive_int(
                line_no,
                meta.get("max_link_capacity"),
                default=1,
                key="max_link_capacity",
            )
            connection = Connection(zone_a, zone_b, max_link_capacity)
            try:
                self._graph.add_connection(connection)
            except ValueError as exc:
                raise MapParseError(str(exc), line_no) from exc

    @staticmethod
    def _validate_name(line_no: int, name: str) -> None:
        """Ensure a zone name is non-empty and free of spaces and dashes."""
        if not name:
            raise MapParseError("empty zone name", line_no)
        if not _NAME_RE.match(name):
            raise MapParseError(
                f"invalid zone name {name!r} (no spaces or dashes allowed)",
                line_no,
            )

    @staticmethod
    def _split_metadata(
        line_no: int, payload: str
    ) -> Tuple[List[str], List[str]]:
        """Split a payload into positional tokens and ``[...]`` metadata tokens."""
        open_idx = payload.find("[")
        if open_idx == -1:
            return (payload.split(), [])
        close_idx = payload.find("]", open_idx)
        if close_idx == -1:
            raise MapParseError("unterminated metadata block", line_no)
        if payload.find("[", open_idx + 1) != -1:
            raise MapParseError("nested metadata blocks", line_no)
        head = payload[:open_idx].strip()
        body = payload[open_idx + 1:close_idx].strip()
        tail = payload[close_idx + 1:].strip()
        if tail:
            raise MapParseError("unexpected text after metadata block", line_no)
        return (head.split(), body.split())

    @staticmethod
    def _metadata_dict(line_no: int, tokens: List[str]) -> Dict[str, str]:
        """Parse ``key=value`` metadata tokens into a dict, rejecting duplicates."""
        result: Dict[str, str] = {}
        for token in tokens:
            match = _METADATA_TOKEN_RE.match(token)
            if match is None:
                raise MapParseError(
                    f"expected 'key=value' metadata, got {token!r}", line_no
                )
            key, value = match.group(1), match.group(2)
            if key in result:
                raise MapParseError(f"duplicate metadata key {key!r}", line_no)
            result[key] = value
        return result

    @staticmethod
    def _parse_positive_int(
        line_no: int,
        raw: Optional[str],
        default: int,
        key: str,
    ) -> int:
        """Parse an optional positive-int metadata value, or return ``default``."""
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise MapParseError(
                f"{key} must be an integer, got {raw!r}", line_no
            ) from exc
        if value <= 0:
            raise MapParseError(f"{key} must be a positive integer", line_no)
        return value
