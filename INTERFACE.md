# Module contract (stdlib only, Python 3.13, runtime ≤ 50 ms/decision, 1 CPU)
Bot files live at repo root (Dockerfile copies `*.py`). Tests in `tests/`, eval tooling in `eval/`.
Never print to stdout (protocol channel). Log to stderr only. No threads/subprocess. Read all numbers from hello["config"].

## nav.py  (owner: Sonnet-1)
class Nav:
  __init__(self, map_dir: str)            # parse world.json + terrain.i16 once (<2 s load budget; hello budget 20 s)
  ground(x, y) -> float                   # bilinear terrain height
  blocked(x, y, z=None) -> bool           # inside prism/too-steep, for a mech radius 2.5
  los(a, b) -> bool                       # building line of sight (eye->target), canopy ignored
  steer(pos, goal_xy, cfg, vel=None) -> (move:[x,y], jump:bool, boost:bool)   # one-step obstacle-aware direction toward goal; <3 ms
  path(pos, goal_xy) -> list[(x,y)]|None  # coarse grid A* (cached/limited), optional
  stuck update: Nav.note_progress(pos, tick) -> bool (True when stuck) and recovery via steer()
  safe_point(center, radius, from_pos) -> (x,y)  # reachable walkable point inside circle, away from walls

## policy.py (owner: Sonnet-2)
class Policy:
  __init__(self, hello, nav)              # nav is nav.Nav (import lazily; fall back if None)
  act(self, obs) -> dict                  # schema-valid action incl. "tick"; never raises (wrap + fallback)
Covers: state tracking across obs (last seen enemies, memory), weapon loot/take/drop, offers (`pick`), aiming w/ lead,
fire discipline, reload, energy/boost mgmt, supply drops, zone retreat, survival-first utility scoring.

## bot.py (owner: orchestrator)  wires mechfight.run(Bot) -> Policy(hello, Nav(hello["map"]["dir"]))
## eval/ , tests/ (owner: Terra) — sim harness, replay tests, latency profiler. Must not edit nav.py/policy.py/bot.py.
