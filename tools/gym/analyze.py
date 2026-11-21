"""Summarise gym results: python3 -I tools/gym/analyze.py RESULTS_DIR [baseline_arm]
Per arm: mean points (16 - place, mean over our slots in a match, then over matches) +- se, and the paired
difference vs the baseline on shared seeds (se from the per-seed differences)."""
import collections
import glob
import json
import math
import os
import sys

d = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else "default"
arms = collections.defaultdict(dict)
extra = collections.defaultdict(lambda: collections.defaultdict(list))
for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
    for l in open(f):
        r = json.loads(l)
        arms[r["arm"]][r["seed"]] = r["ours_mean"]
        extra[r["arm"]]["early"].append(r["early_deaths_20s"])
        extra[r["arm"]]["miss"].append(r["misses"])
        extra[r["arm"]]["t"].append(r["t"])
        for k, v in r["by_label"].items():
            extra[r["arm"]]["L:" + k].append(v)


def ms(x):
    n = len(x)
    m = sum(x) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / max(1, n - 1))
    return m, sd / math.sqrt(n)


print("%-12s %4s %14s %22s   early<=20s  miss/match" % ("arm", "n", "mean pts +-se", "paired vs " + base))
for a, s in arms.items():
    m, se = ms(list(s.values()))
    line = "%-12s %4d %7.2f +- %.2f" % (a, len(s), m, se)
    if a != base and base in arms:
        sh = sorted(set(s) & set(arms[base]))
        if len(sh) > 1:
            dm, dse = ms([s[k] - arms[base][k] for k in sh])
            line += "   %+6.2f +- %.2f (n=%d)" % (dm, dse, len(sh))
    e = extra[a]
    line += "   %.1f   %.1f" % (sum(e["early"]) / len(e["early"]), sum(e["miss"]) / len(e["miss"]))
    print(line)
print("\nfield mean points by label (all arms pooled):")
pool = collections.defaultdict(list)
for a in extra:
    for k, v in extra[a].items():
        if k.startswith("L:"):
            pool[k[2:]] += v
for k, v in sorted(pool.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
    print("  %-11s %5.2f" % (k, sum(v) / len(v)))
