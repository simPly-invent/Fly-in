"""Interactive map-selector menu for Fly-in.

Mirrors the numbered-options / screen-refresh idiom of the earlier A-MAZE-ING
project: clear the screen with ``\\033c`` between actions, prompt with letters
and numbers, return a sentinel so the caller can decide what to do next.

Two helpers are exposed:

* :func:`discover_maps`  -- walk the ``maps/`` directory and group ``.txt``
  files by their tier subfolder (``easy``, ``medium``, ``hard``, ...).
* :class:`Menu`          -- render the interactive selector and return either
  the chosen map ``Path`` or ``None`` when the user quits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAR_SCREEN = "\033c"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_CYAN = "\033[36m"
ANSI_YELLOW = "\033[33m"

_TIER_ORDER = ("easy", "medium", "hard", "challenger")


def _tier_sort_key(tier: str) -> Tuple[int, str]:
    """Sort known tiers by difficulty; unknown tiers come last."""
    try:
        return (_TIER_ORDER.index(tier), tier)
    except ValueError:
        return (len(_TIER_ORDER), tier)


def discover_maps(root: Path) -> Dict[str, List[Path]]:
    """Return ``.txt`` map files grouped by their immediate parent directory.

    Files at the top level of *root* are grouped under the key ``"."``. Within
    each group, files are sorted alphabetically so the menu numbering stays
    stable across runs.
    """
    grouped: Dict[str, List[Path]] = {}
    try:
        candidates = sorted(root.rglob("*.txt"))
    except OSError as exc:
        raise RuntimeError(
            f"cannot read maps directory '{root}': {exc}"
        ) from exc

    for path in candidates:
        try:
            tier = (
                path.relative_to(root).parts[0]
                if path.parent != root
                else "."
            )
        except ValueError:
            tier = "."
        if path.parent == root:
            tier = "."
        grouped.setdefault(tier, []).append(path)
    return grouped


class Menu:
    """Interactive text menu to pick a map file."""

    def __init__(self, maps_root: Path, use_colour: bool = True) -> None:
        self.maps_root = maps_root
        self.use_colour = use_colour

    def _styled(self, text: str, *codes: str) -> str:
        """Wrap ``text`` in the given ANSI codes, unless colour is disabled."""
        if not self.use_colour or not codes:
            return text
        return "".join(codes) + text + ANSI_RESET

    def _render(
        self, ordered: List[Path], grouped: Dict[str, List[Path]]
    ) -> None:
        """Clear the screen and draw the numbered, tier-grouped map list."""
        print(CLEAR_SCREEN, end="")
        bar = "=" * 42
        print(self._styled(bar, ANSI_BOLD))
        print(self._styled("       Fly-in :: Map selector", ANSI_BOLD))
        print(self._styled(bar, ANSI_BOLD))
        print()

        index = 1
        for tier in sorted(grouped.keys(), key=_tier_sort_key):
            label = "root" if tier == "." else tier.upper()
            print(self._styled(label, ANSI_BOLD, ANSI_CYAN))
            for path in grouped[tier]:
                name = path.stem
                print(f"  {self._styled(f'{index:>2})', ANSI_YELLOW)} {name}")
                index += 1
            print()

        print(f"  {self._styled(' q)', ANSI_YELLOW)} Quit")
        print(f"  {self._styled(' r)', ANSI_YELLOW)} Reload maps")
        print()
        total = len(ordered)
        summary = f"({total} map(s) found in {self.maps_root})"
        print(self._styled(summary, ANSI_DIM))

    def prompt(self) -> Optional[Path]:
        """Display the menu; return the chosen path or ``None``."""
        while True:
            try:
                grouped = discover_maps(self.maps_root)
            except RuntimeError as exc:
                print(exc)
                return None

            ordered: List[Path] = []
            for tier in sorted(grouped.keys(), key=_tier_sort_key):
                ordered.extend(grouped[tier])

            if not ordered:
                print(CLEAR_SCREEN, end="")
                print(self._styled(
                    f"No .txt map file found under {self.maps_root}.",
                    ANSI_BOLD,
                ))
                return None

            self._render(ordered, grouped)

            try:
                raw = input("\nChoice: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return None

            if raw in {"q", "quit", "exit"}:
                return None
            if raw in {"r", "reload"}:
                continue
            if not raw:
                continue

            try:
                choice = int(raw)
            except ValueError:
                self._wait(f"Invalid choice: {raw!r}")
                continue

            if 1 <= choice <= len(ordered):
                return ordered[choice - 1]

            self._wait(f"Out of range: {choice} (expected 1..{len(ordered)})")

    def _wait(self, message: str) -> None:
        """Show an error ``message`` and pause until the user presses Enter."""
        print(self._styled(message, ANSI_BOLD))
        try:
            input("Press Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            pass
