# Drone sprites

Drop your drone images in this folder — they will be picked up automatically
by the pygame view.

## Format

- PNG with transparency is recommended (alpha channel is preserved).
- JPG / BMP also work.
- Square images render best. They are resized to the simulation's drone
  diameter at load time, so any reasonable resolution works (64×64 or
  128×128 are good defaults).

## Naming

Any filename ending in `.png`, `.jpg`, `.jpeg` or `.bmp` is accepted. Files
are loaded sorted alphabetically. Drones D1, D2, D3, … get assigned sprites
in that order, cycling back to the start if there are more drones than
sprites.

Examples:

```
assets/drones/
├── drone_a.png        # used by D1, D5, D9, …
├── drone_b.png        # used by D2, D6, D10, …
└── drone_red.png      # used by D3, D7, D11, …
```

## Fallback

If this folder is empty, the pygame view falls back to coloured circles
with the drone label drawn on top (D1, D2, …). The simulation works the
same way either way — only the visuals differ.
