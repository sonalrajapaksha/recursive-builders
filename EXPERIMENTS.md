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
| E17 | official combo2 (bff0082) = combo1 + aggressor3 (early zone exit, chase weak) + gearup (loot memory, boost >60m) | 4.54 BEST (+0.23 vs combo1). Leaderboard now >200 teams, top ~5.96; we are ~65th-70th; top-20 line likely ~5.5-5.6 (moving). Small merged gains stack. |
| E18 | diag-bots (108a18b) on recorded stream | Hunter id10 (gun+laser) held ~140m, strafed 7.8 m/s, aim err median 1.1deg (0.2deg vs standing). 76% of our damage = 4 full-charge lasers at ~149m, 0% rear. In 3/4 charges our sidestep side flipped per tick so beams hit. Fix: commit one side per charge. |
| E19 | diag-self (1947c57) replay | enemy visible 169 ticks, fired 32: no-LOS 52, reloading 27, flee-no-target 23, aim-not-ready 17. hide 34.7% of time, boost 70% of ticks. Fixes: pickup memory (dup of gearup), no preemptive reload with enemy in view. Open: shoot back while fleeing; boost noise in hide. |
| E20 | official combo3 (627c615) = combo2 + sidestep-commit + shoot-back-while-fleeing + reload fix + quiet hide | 4.27 vs combo2 4.54: WORSE. One of 4 changes hurt (suspects: full-weight dodge overriding movement, shoot-back, quiet hide). Plan: ablate. Next: diag-bots 108a18b (combo2 + sidestep-commit ONLY); also resubmit combo2 once to measure run-to-run noise. |
| E21 | diag-bots 108a18b (combo2 + sidestep-commit only) docker check PASS p99 6.0ms | submit at next slot (5:53 AM EST) as ablation |
