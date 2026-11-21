"""Run free-for-all league matches and compare bot versions inside the same matches.

    uv run python tools/league.py --matches 12 \
        --entry new=bot:bot.py=8 --entry old=bot:../scratch/bot_v5.py=8

    --entry LABEL=SPEC=COUNT   (COUNTs must sum to 16; see tools/arena.py for SPEC)
    --start N                  seed offset (run chunks in parallel and merge with tools/league_merge.py)

Output: one JSON line per match with the mean points of every label, then a summary with the
paired difference (first label minus second) and its standard error.
"""
import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arena  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=6)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--kit", default="..")
    ap.add_argument("--entry", action="append", required=True)
    ap.add_argument("--max-t", type=float, default=480.0)
    ap.add_argument("--econ", action="store_true", help="model crates, NPC drones, supply drops, cube upgrades")
    args = ap.parse_args()

    cfg = arena.load_cfg(args.kit)
    world = None
    entries = []
    labels = []
    for e in args.entry:
        label, rest = e.split("=", 1)
        spec, count = rest.rsplit("=", 1)
        labels.append(label)
        fac = arena.make_factory(spec, args.kit)
        entries += [(label, fac)] * int(count)
    assert len(entries) == 16, "entry counts must sum to 16 (got %d)" % len(entries)
    sample_mod = next((m for m in arena._MODS.values()), None)
    world = sample_mod._shared[0] if sample_mod is not None else None
    if world is None:
        import sim as S
        world = S.B.World(os.path.join(args.kit, "arena"))

    per_match = []
    agg = {}
    for k in range(args.matches):
        seed = 1 + args.start + k
        order = list(range(16))
        random.Random(seed * 31 + 7).shuffle(order)  # which slot gets which entry
        shuffled = [entries[i] for i in order]
        sim = arena.League(cfg, world, seed, shuffled, econ=args.econ)
        res = sim.run(args.max_t)
        for r in res:
            a = agg.setdefault(r["label"], {})
            a["n"] = a.get("n", 0) + 1
            a["alive_s"] = a.get("alive_s", 0.0) + r["alive_s"]
            for k2, v2 in r["stats"].items():
                a[k2] = a.get(k2, 0.0) + v2
        means = {}
        for lab in labels:
            pts = [r["points"] for r in res if r["label"] == lab]
            means[lab] = sum(pts) / len(pts)
        per_match.append(means)
        print(json.dumps({"seed": seed, "t": round(sim.t, 1), "means": {k2: round(v, 2) for k2, v in means.items()},
                          "act_p99": max(r["act_p99"] for r in res), "act_max": max(r["act_max"] for r in res),
                          "cpu_p99": max(r["cpu_p99"] for r in res), "cpu_max": max(r["cpu_max"] for r in res)}), flush=True)

    print("COMBAT " + json.dumps(agg))
    n = len(per_match)
    print("SUMMARY n=%d" % n + " " + " ".join("%s=%.2f" % (lab, sum(m[lab] for m in per_match) / n) for lab in labels))
    if len(labels) >= 2:
        diffs = [m[labels[0]] - m[labels[1]] for m in per_match]
        mu = sum(diffs) / n
        sd = math.sqrt(sum((d - mu) ** 2 for d in diffs) / max(1, n - 1))
        print("PAIRED %s-%s = %.2f  se %.2f" % (labels[0], labels[1], mu, sd / math.sqrt(n)))


if __name__ == "__main__":
    main()
