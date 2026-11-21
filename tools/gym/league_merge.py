"""Merge the JSON lines printed by several tools/league.py runs and print means and paired differences.

    uv run python tools/league_merge.py out1.txt out2.txt ...
"""
import json
import math
import sys

rows = []
for p in sys.argv[1:]:
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("{") and '"means"' in line:
            rows.append(json.loads(line)["means"])
if not rows:
    sys.exit("no match lines found")
labels = list(rows[0])
n = len(rows)
print("matches %d" % n)
for lab in labels:
    v = [r[lab] for r in rows]
    mu = sum(v) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in v) / max(1, n - 1))
    print("  %-10s mean %.2f  (se %.2f)" % (lab, mu, sd / math.sqrt(n)))
for i in range(len(labels)):
    for j in range(i + 1, len(labels)):
        d = [r[labels[i]] - r[labels[j]] for r in rows]
        mu = sum(d) / n
        sd = math.sqrt(sum((x - mu) ** 2 for x in d) / max(1, n - 1))
        print("  %s - %s = %+.2f  (se %.2f)" % (labels[i], labels[j], mu, sd / math.sqrt(n)))
