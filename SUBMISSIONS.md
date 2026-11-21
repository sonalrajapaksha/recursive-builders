# SUBMISSIONS (quota: 4/hour; never overwrite best validated)
| # | commit | time | status | official score |
|---|--------|------|--------|----------------|
| 1 | 5f096bc763aec0673d0583dc69fdf23859520931 | 2026-11-21 20:06 NZDT | scored (receipt BB-C9FF47AA) | 3.56 |
| 2 | 7da19284a26b2e1f838a6a951d10240deecc7cab (branch survival-hider) | 2026-11-21 21:51 NZDT | scored (BB-D12A7DF6) | 2.15 (WORSE than v1) |
| 3 | 74bbadc8e73314a1e0ef4528d5f0c5e697b83bb5 (branch aggressor) | 2026-11-21 21:55 NZDT | scored (BB-673700B0) | 3.88 (BEST so far) |
Note: site allows only ONE submission in scoring at a time; wait for the current to finish. audit-fixes (6802a4b) validated, pushed, queued next.
| 4 | d315858d917166e69cb923a667caf92866447f5e (branch audit-aggressor = audit-fixes + aggressor + mortar arc fix) | 2026-11-21 21:58 NZDT | scored (BB-0EFB25CD) | 4.25 (BEST) |
| 5 | a6eb860b088be91711f0789a8d603ab767d24b90 (branch aggressor2 = audit-aggressor + faster/wider loot, cubes, drops) | 2026-11-21 22:00 NZDT | scored (BB-FF691224) | 4.31 (BEST) |
| 6 | 24f35d6752b20776e91f1dce0a2b51cfa7babaab (branch combo1 = aggressor2 + fight-quality) | 2026-11-21 22:53 NZDT | scored (BB-74B78296) | 4.25 (noise vs 4.31) |
| 7 | 5a8d567f2ca46e03c3bf1af190926bdb7687c059 (branch duelist = combo1 + peek-and-heal) | 2026-11-21 22:56 NZDT | scored (BB-BE687122) | 4.10 (worse than combo1 4.25) |
| 8 | bff00824a32cc2c4f275281839cc2d9e0a0874f5 (branch combo2 = combo1 + aggressor3 + gearup) | 2026-11-21 22:58 NZDT | scored (BB-E97BDD84) | 4.54 (BEST) |
| 9 | 627c6156e83a5b47879e01ff037381b3500a51ac (branch combo3 = combo2 + laser sidestep commit + shoot-back while fleeing + reload fix + quiet hide) | 2026-11-21 23:02 NZDT | scored (BB-2A8D6D84) | 4.27 (worse than combo2 4.54; score provided by user) |
| 10 | 430547c93ff48a651d38574749092e2b3a182755 (branch laser-cover = combo2 + cover/committed-sidestep laser defence) | 2026-11-22 00:00 NZDT | scored (BB-07D57AE8) | 4.44 (vs combo2 4.54: noise, no gain; score provided by user) |
| 11 | b5bcf62816f9ee184e6cdbd20ab6b57d7db8c9ee (branch abl-shootback = combo2 + shoot-back-while-fleeing only) | 2026-11-22 00:02 NZDT | scored (BB-8B5C5715) | 4.31 (-0.23 vs combo2; shoot-back likely hurt) |
| 12 | 3f03885c456f5e6482b715ef4a8846084ce64171 (branch lightning-rush = combo2 + lightning-first doctrine, close to <=31m) | 2026-11-22 00:07 NZDT | scored (BB-015EF900) | 4.13 (worse than combo2 4.54) |
| 13 | bff00824a32cc2c4f275281839cc2d9e0a0874f5 (combo2 REPEAT to measure run-to-run noise) | 2026-11-22 00:09 NZDT | received, receipt BB-4EB38F11, scoring | pending |
| 14 | 3734583f2d8082be2379722c0743aab9aecd3e08 (abl-reload) | single-change ablation of combo2 | received, receipt BB-07B91792, scoring | pending |
| 14 result | abl-reload 3734583 | 4.50 (receipt BB-D7B91790, took ~30 min stuck in Fetching) | neutral vs combo2 ~4.58 |
| 15 | 74472114cef8bea5ee11a6ed37f924b46cd13127 (giddy-base: MIT Go bot justnau/giddygiddyboy-mech-royale@edbdb6b, unchanged, license kept) | user chose it as new strategy base; docker amd64 check PASS p99 5.8ms | scored, receipt BB-31B21D8B | 6.10 (now final entry) |
| 16 | 53e6cd3867d2819ef88d388d906d7366b6eaccc2 (gx-kill-zonecenter, giddy-base + late-game zone-center bias) | docker PASS | scored, receipt BB-0A6AABA8 | 6.10 (identical to giddy-base: no practice effect) |
| 17 | 617ea065014b4a8720a24c4957c4b47590058394 (gx-cube-radius, giddy-base + visible-cube chase radius 63->110m, cubeV 100) | docker PASS | scored, receipt BB-2B752C79 | 6.04 (slightly below base; dropped) |
| 18 | f92c6fdf1aedbac6e2ea0e2122277d14d56cf1db (bold-cube-lord: Econ loot, drops, 90s farming tour, armor-first upgrades) | docker PASS | scored, receipt BB-78FA0F43 | 5.46 (-0.64 vs base; dropped) |
| 19 | 5c2de260212c92cca576b2472fd4b28fd1bce13f (bold-pred-kill-engine) | docker PASS | received, receipt BB-36D95028-ish, scoring | pending |
