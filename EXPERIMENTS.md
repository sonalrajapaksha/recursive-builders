# EXPERIMENTS (real measurements only)
| id | what | result |
|----|------|--------|
| E1 | starter example_bot via check.py | PASS 300/300, p99 9.3ms |
| E2 | v1 bot.py native check.py | PASS 300/300, p50 0.2 p99 1.5 max 1.8 ms |
| E3 | v1 Docker amd64 + full sandbox flags, check.py --map-dir /arena | PASS 300/300, p50 0.8 p99 3.2 max 7.6 ms (arm host emulating amd64) |
| E4 | unit tests nav(11)/policy(19)/replay(2) | pass |
Known: nav A* replan can hit 12ms cap; replay latency tests fall back to no-nav because recorded hello map dir is not local.
| E5 | official v1 practice (48 matches vs house squad) | 3.56 (mean place ~12.4). rank-32 ~4.92, top ~5.6 |
| E6 | official survival-hider (7da1928): silent walk, cover hiding, flee-more, less loot/cubes | 2.15 vs v1 3.56. FALSIFIED: passivity/less loot loses badly vs hunting squad. Don't submit more passive variants. Best remains v1 (5f096bc). |
| E7 | official aggressor (74bbadc): boost-loot, engage more, damage upgrades | 3.88 vs v1 3.56. Direction confirmed: capability beats passivity. |
