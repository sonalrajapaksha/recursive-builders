"""FFA gym: paired 16-mech free-for-all leagues, our bot variants vs a field of other teams' bots.

    python3 -I tools/gym/gym.py --arm default --matches 20 --start 0 --out results/default.0.jsonl
    python3 -I tools/gym/gym.py --arm cover --params '{"RetreatHP":0.5}' ...

Field bots are cloned under FIELD (default /tmp/ext/field) and are only ever RUN, never copied here.
Same --start/--matches => same seeds, same spawn slots for every arm (paired).
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arena  # noqa: E402
from procbot import ProcBot  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
FIELD = os.environ.get("FIELD", "/tmp/ext/field")
ARENA = os.path.join(REPO, "arena")
PY = ["python3", "-B", "-u"]

# label -> (cmd, cwd, extra env)
BOTS = {
    "giddy":      ([FIELD + "/bin/giddy"], FIELD, {}),
    "waiprotein": ([FIELD + "/bin/waiprotein"], FIELD, {}),
    "lance":      (PY + ["bot.py"], "/tmp/ext/lance", {}),
    "charlie":    (PY + ["bot.py"], FIELD + "/charliescull_mech-royale-bot", {}),
    "nurdaulet":  (PY + ["bot.py"], FIELD + "/NurdauletZhalgas_Mech-Royale-Bot", {}),
    "kpfarn":     (PY + ["bot.py"], FIELD + "/kpfarn_osuhackathon", {}),
    "caio":       (PY + ["bot.py"], FIELD + "/caioplcerda_oval-pilot", {}),
    "ghostts":    (["node", "--expose-gc", "--disable-warning=ExperimentalWarning", "src/main.ts"], FIELD + "/Not-Ethan_oval-ghost-mech", {}),
    "anthonyts":  (["node", "--disable-warning=ExperimentalWarning", "bot.ts"], FIELD + "/anthonyteti_buildathon-mech-royale", {}),
}
# the 13 non-ours slots (ours takes --ours-k of the 16)
FIELD13 = ["giddy", "waiprotein", "lance", "nurdaulet", "kpfarn", "ghostts", "caio", "anthonyts",
           "hunter", "hunter", "hunter", "example", "example"]  # 8 subprocess opponents + 5 cheap in-process ones


def proc_factory(label, cmd, cwd, env, tag):
    def f(hello, world):
        h = dict(hello)
        h["map"] = {"dir": ARENA, "files": ["v2/world.json", "v2/terrain.i16"]}
        return ProcBot(cmd, cwd, h, env=env, name=label, errlog="/tmp/gym-%s-%s.err" % (tag, label))
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--params", default="{}", help="MR_PARAMS JSON for our Go bot (field names of mech.Params)")
    ap.add_argument("--ours-bin", default=FIELD + "/bin/ours_gym")
    ap.add_argument("--ours-k", type=int, default=3)
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-t", type=float, default=480.0)
    ap.add_argument("--econ", action="store_true", default=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = arena.load_cfg(REPO)
    import sim as S
    world = S.B.World(ARENA)
    entries = []
    ours_env = {"MR_PARAMS": args.params}
    for _ in range(args.ours_k):
        entries.append(("ours", proc_factory("ours", [args.ours_bin], FIELD, ours_env, args.arm)))
    field = (FIELD13 * 2)[: 16 - args.ours_k]
    for lab in field:
        if lab == "hunter":
            entries.append(("hunter", arena.make_factory("hunter", REPO)))
        elif lab == "example":
            entries.append(("example", arena.make_factory("example", REPO)))
        else:
            cmd, cwd, env = BOTS[lab]
            entries.append((lab, proc_factory(lab, cmd, cwd, env, args.arm)))
    assert len(entries) == 16
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "a") as fo:
        for k in range(args.matches):
            seed = 1 + args.start + k
            order = list(range(16))
            random.Random(seed * 31 + 7).shuffle(order)
            shuffled = [entries[i] for i in order]
            t0 = time.time()
            sim = arena.League(cfg, world, seed, shuffled, econ=args.econ)
            res = sim.run(args.max_t)
            early = sum(1 for t, _ in sim.deaths if t <= 20.0)
            for b in sim.bots:
                if hasattr(b, "close"):
                    b.close()
            ours = [r for r in res if r["label"] == "ours"]
            rec = {"arm": args.arm, "seed": seed, "t": round(sim.t, 1), "wall": round(time.time() - t0, 1),
                   "ours_pts": [r["points"] for r in ours], "ours_mean": sum(r["points"] for r in ours) / len(ours),
                   "ours_alive_s": [r["alive_s"] for r in ours], "early_deaths_20s": early,
                   "misses": sum(getattr(b, "misses", 0) for b in sim.bots),
                   "misses_by": {lab: sum(getattr(b, "misses", 0) for b, m in zip(sim.bots, sim.mechs) if m.label == lab) for lab in sorted(set(m.label for m in sim.mechs))},
                   "by_label": {lab: round(sum(r["points"] for r in res if r["label"] == lab) / sum(1 for r in res if r["label"] == lab), 2)
                                for lab in sorted(set(r["label"] for r in res))}}
            fo.write(json.dumps(rec) + "\n")
            fo.flush()
            print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
