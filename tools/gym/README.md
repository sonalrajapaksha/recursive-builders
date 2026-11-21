# FFA gym

Local 16-mech free-for-all, our Go bot (variants) against a field of other teams' public bots.

* `sim.py`, `arena.py`, `league.py`, `league_merge.py`, `lance/` : copied from github.com/LanceHuang245/mech-royale
  (MIT, see `lance/LICENSE`). Protocol-level vision wedge / line of sight / sound with bearing noise, gun, laser, lightning,
  zone, loot, crates, NPC drones, upgrades, supply drops. `arena.py` was changed so bots can be subprocesses and think in parallel.
* `procbot.py` : runs any `mechfight/1` bot (Go, Python, node) as a subprocess in lockstep.
* `gym.py` : one arm = 16 mechs: `--ours-k` copies of our bot (default 3) + 13 field slots
  (giddy, waiprotein, lance, nurdaulet, kpfarn, caio, ghost-ts, anthony-ts + 3 naive hunters + 2 kit examples).
  Same seed => same spawn assignment for every arm (paired). Output is one JSON line per match.
* `run_arms.sh` : the arms used (default + 3 param variants, 2 chunks x 32 matches). `analyze.py` : mean points +- se, paired diffs.

Field bots live under `/tmp/ext/field` (cloned, never copied here); `gym.py` has the clone-dir/command table.
Our gym binary is built from tune-base with a gym-only patch (not committed): `Practice=false` in the default profile,
`MR_PARAMS` env JSON overrides of `mech.Params` fields, and a `SneakSpd` param. With Practice on, the squad profile
would switch on after t>20 s whenever fewer than 5 other mechs have died (the gym had 1-3 early deaths per match).

Trust: uncalibrated for FFA. Combat model, aim noise, spawn and loot are approximations, field bots run with unlimited
CPU time, no mortar, no roof crates. Use it for gross sanity and relative ranking only; se per arm ~0.4-0.5.
