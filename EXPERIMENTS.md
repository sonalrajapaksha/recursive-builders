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
| E8 | official audit-aggressor (d315858): bug fixes + aggressor + mortar arc fix | 4.25 (best). Bug fixes added +0.37 over aggressor 3.88. |
| E9 | eval-sim (Terra, 55ed33c) squad approximation | calibration FAILED (sim v1 0.0 vs real 3.56). Do not use for selection; official scores are the only signal. |
| E10 | official aggressor2 (a6eb860): faster/wider loot, cubes, drops | 4.31 vs 4.25 (within noise, still best). Gap to top-20 (~5.1): ~0.8 |
| E11 | combo1 (24f35d6) = aggressor2 + fight-quality; docker amd64 check PASS p99 5.5ms | submit when quota frees (next slot 4:51 AM EST) |
| E12 | aggressor3 (62e1234) = aggressor2 + early zone exit in late phases + chase weak mechs; docker check PASS | queued after combo1 |
| E13 | analysis (rules) | Practice = us vs 15 house bots that never fight each other => place ~= 16 - (#bots dead before us). Kills (and zone) are the only way to climb. Duel strength + gear/cube snowball is THE lever. Site gives no replays/per-match data (checked submission rows + status page). |
| E14 | official combo1 (24f35d6) = aggressor2 + fight-quality | 4.25 vs 4.31: no gain; tuning-level changes plateau ~4.3 (noise ~±0.1). Need structural gains. |
| E15 | combo2 (bff0082) = combo1 + aggressor3 + gearup; docker check run | queued next |
| E16 | official duelist (5a8d567) = combo1 + peek-and-heal | 4.10 vs 4.25: no gain (slightly worse). Retreat-to-heal not the lever; drop it. |
