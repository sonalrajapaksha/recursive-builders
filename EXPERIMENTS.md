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
| E22 | ablation branches from combo2: abl-reload 3734583, abl-shootback b5bcf62, abl-quiet 520c57f (single change each) | pushed; submit one per slot after diag-bots(108a18b, sidestep-only) |
| E23 | laser-cover 430547c (combo2 + cover/committed-sidestep laser defence); docker amd64 checks PASS for laser-cover(p99 10.0), abl-shootback(5.2), abl-quiet(3.6), abl-reload(4.0) | queue ready |
| E24 | official laser-cover (430547c) | 4.44 vs combo2 4.54: no gain. Laser defence alone is not the lever (or sim of beam-line trigger too wide). Next: abl-shootback. |
| E25 | plan | Structural round: A 'lightning-rush' (weapon doctrine: close to <=45m, lightning beats laser, DPS math), B 'cover-routes' (exposure-weighted nav using static map). Ablations (abl-shootback running; abl-quiet, abl-reload, diag-bots queued) continue in parallel. |
| E26 | official abl-shootback (b5bcf62) | 4.31 vs combo2 4.54: -0.23. Shoot-back-while-fleeing likely the cause of combo3's drop; DROP it. |
| E27 | lightning-rush 3f03885 docker check PASS p99 2.0ms | submitted as #12 |
| E28 | official lightning-rush (3f03885) | 4.13: worse. Rushing/closing hurts. All 8 variants since aggressor2 sit 4.1-4.5 (mean ~4.3): combo2 4.54 may be partly lucky; run-to-run noise ~±0.2. Micro-ablation exhausted. |
| E29 | cover-routes 946014f docker PASS (load 2.6s ready, p99 7.8ms); worker says effect modest (~0.05 less exposure, +1.5% path) | not submitted yet; low expected gain |
| E30 | repeat-run of combo2 submitted (#13) | measures noise; if ~4.3 then true level ~4.3 and 4.54 was partly luck |
| E31 | official combo2 repeat (#13, bff0082) | 4.63 vs 4.54 first run: run-to-run noise only ~±0.05, so differences >=0.15 are real. Combo2 true level ~4.58. Submission quota gives ~4/hr until cutoff => hill-climbing with single changes is viable. |
| E32 | decision | User chose to adopt the public MIT bot giddygiddyboy (reported 6.19 on board) as base on branch giddy-base; our Python bot kept on other branches. Improve it step by step with single-change ablations; scores deterministic for that bot per its README. |
| E33 | official giddy-base (7447211) | 6.10: ~top 10-12 on board; 6.0 target reached on practice. Now best entry and final pick. Next: gx-cube, gx-kill workers improve it with single-change branches; combo2 (4.63) demoted. |
| E34 | official gx-kill-zonecenter (53e6cd3) | 6.10 = identical to giddy-base. Neutral in practice (bot is deterministic per README). Queue: gx-cube-radius (scoring), gx-cube-drops 0984e87, gx-cube-upgrade 3246db2 (may no-op), gx-kill-regen bf188e0. |
| E35 | official gx-cube-radius (617ea06) | 6.04 vs 6.10: -0.06, dropped. Small cube tweaks do nothing. Quota 0/4 used up at ~2:15 PM; next slot 2:23 PM site time. Queue (bold first): bold-cube-lord f92c6fd, bold-cube-laser f08e0bf, then bold-pred / bold-param branches when workers report, then gx-cube-drops 0984e87, gx-cube-upgrade 3246db2, gx-kill-regen bf188e0. |
| E36 | bold-param branches pushed (docker PASS): aggro be0cfd2, defense 14076fd, mixed 9926a8f. KEY FINDING: practice mode swaps DefaultParams for squadParams after 20 s (brain.go ~336): the base already detects practice and plays a fight-everything squad profile; Ghost/sneak only runs first 20 s (and presumably in a free-for-all). Also bold-cube-lord f92c6fd / bold-cube-laser f08e0bf pushed. check.py needs --map-dir /arena. bold-pred still running. |
| E37 | bold-pred branches pushed (docker PASS): kill-engine 5c2de26, lategame f6c1218, full b13b049. Submission queue after bold-cube-lord: pred-kill-engine, param-aggro, pred-full, param-defense, param-mixed, cube-laser, pred-lategame, then small gx-* branches. |
