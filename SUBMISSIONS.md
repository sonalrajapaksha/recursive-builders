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
| 19 | 5c2de260212c92cca576b2472fd4b28fd1bce13f (bold-pred-kill-engine) | docker PASS | scored, receipt BB-06D95D2B | 5.71 (-0.39 vs base; dropped) |
| 20 | 66d5191ac43b7b4d5afb63a6d7e42e9f9d6b89b4 (tv-lr160: giddy-base + LaserRange 160 via tune.json) | docker PASS | received, receipt BB-338F7658-ish, scoring | pending |
| 20 result | tv-lr160 66d5191 | 5.96 (receipt BB-3B8F7658): -0.14 vs base, dropped |
| 21 | 24fe8a48a028f5ce7eb1ac3d83f639c75dacdb54 (probe-tmp: idles if /tmp marker persists) | docker PASS | received, receipt BB-F72A5C72-ish, scoring | pending; ~1.x = /tmp persists, ~6.1 = fresh container per match |
| 21 result | probe-tmp 24fe8a4 | 6.10 (BB-F72A5C72): same as base => scorer uses a fresh container per match; cross-match learning impossible |
| 22 | e31d3b8e66c96da8ac58811fef3f70adf89df784 (tv-lseek320) | 6.10 (BB-7AA9E919): knob has no effect |
| 23 | 7a64e1596aabbdd092bd6e8c4a19d6acf3a284c3 (tv-floot110) | scored, receipt BB-16E0129E | 5.81 (-0.29 vs base; dropped) |
| 24 | 9f7a9107346d73aaf1920f197cc158fbf535474b (tv-maxt320) | docker PASS | scored, receipt BB-F2B36F1E | 6.10 (no effect) |
| 25 | 52d923ed83c9ca54ecca81b296656716a1c4d647 (mpc-combat: sampling MPC dodge/combat movement in squad profile) | docker PASS p99 5.5ms | scored, receipt BB-01F713E5 | 5.15 (-0.95 vs base; guessed model hurts; dropped) |
| 26 | da818512377cca91eeb59f4966f01dae79d091ec (mpc-combat-lite: MPC only on laser/bullet triggers) | docker PASS | scored, receipt BB-6742FA62 | 5.35 (-0.75 vs base; dropped) |
| 27 | cbc30a1fb24587ee19ba0854d71a7d69b3265d7d (wpn-ambush: hidden pre-charged laser ambush) | docker PASS | scored, receipt BB-02808AD2 | 5.85 (-0.25 vs base; dropped) |
| 28 | f1999a24f30ecc0977419c61490c706412d4284a (wpn-lightning-counter) | docker PASS | scored, receipt BB-4F4F41BA | 6.10 (trigger never fires in practice; no effect) |
| 29 | 84241ddf547867af7ebdd7f2263c1019e356470a (wpn-mortar) | docker PASS | scored, receipt BB-22D61D99 | 5.83 (-0.27 vs base; dropped) |
| 30 | 3246db203f89c2fd8c58cda1a288a410737f31ab (gx-cube-upgrade: armor/HP upgrade pick by offer effects) | docker PASS | scored, receipt BB-C83FF009 | 6.10 (no effect) |
| 31 | 0984e87ad2b0c297fbac8e9500ef212b6af1b302 (gx-cube-drops: UseDrops true) | docker PASS | scored, receipt BB-CD1778F5 | **6.21 (+0.11 vs base 6.10): NEW BEST, shown as final pick** |
| 32 | f2e0c1395f5b1eadd3f7e37caa88b27e75ec731a (tv-dv400: dtune-base 4a16f10 + DropV1 300/DropV2 400) | docker PASS | scored, receipt BB-0FE9EAD0 | 6.21 (identical to gx-cube-drops: DropV values no effect) |
| 33 | 2616995f18133262d4500e8b6ad95e332ccf123f (tv-dwin45: dtune-base + DropWin 45) | docker PASS | scored, receipt BB-BE0C77AD | 6.21 (identical to gx-cube-drops: arrival window no effect) |
| 34 | 863fa4e85d7fefb93fec4d0bbaaa8a4b61cad967 (tv-dv600: DropV 450/600 + DropWin 40) | docker PASS | scored, receipt BB-64EFB59E | **6.25 (+0.04): NEW BEST, shown as final pick** |
| 35 | 318edef23b7563eb9304705712356edbbec4a543 (tv-dv1000: DropV 1000/1500 + DropWin 60) | docker PASS | scored, receipt BB-09803706 | 6.23 (below dv600 6.25) |
| 36 | cc3bb52862939ca4aa52ec94d352f6e988a86fa5 (tv-dv600w80: DropV 450/600 + DropWin 80) | docker PASS | scored, receipt BB-98623ABA | 6.25 (tie with dv600; earlier submission keeps the pick) |
| 37 | 9b7d6fd1363ff37a12bdb6920ac9afc76fdc32c0 (tv-dfarm35: dv600 drops + FarmHP 0.35) | docker PASS | scored, receipt BB-C2A8AEF5 | 6.25 (no change vs dv600) |
| 38 | waiprotein/mech-royale-bot 42c594fc51f2fecd457c984cb18f0ede9d3cf306 (third-party MIT giddy fork, scored as a reference only, not our code) | not built locally | scored, receipt BB-74AA3615 | 6.19 (about base, as predicted) |
| 39 | 881288a9d3d0a3cb8ac5678b13367a8b1895ae65 (struct-ghost: dv600 + Practice=false, keep Ghost/sneak profile all match) | docker PASS | scored, receipt BB-BB2C3B11 | 5.23 (-1.02 vs dv600; FALSIFIED) |
| 40 | cbaaf04380e111791067d5e198a13528bda5ab1f (tv-dloot220: dv600 drops + LootRadius 220) | docker PASS | scored, receipt BB-708261B0 | 6.06 (-0.19 vs dv600; dropped) |
| 41 | b89c083b87a132b1b76f77c3a05591a7829a9b6f (dv600-regen: tv-dv600 + gx-kill-regen) | docker PASS | scored, receipt BB-27E79305 | 6.25 (ties dv600; regen no effect) |
| 42 | e22f91187ab965686ee92f3d04e4dc113c63c554 (dv600-healdrop: Opus design, retreat to landing supply drop) | docker PASS | scored, receipt BB-3B48C147 | 6.19 (-0.06 vs dv600; dropped) |
| 43 | b0ce21dae94fde4c795391f39c4a8128626a2fd1 (dv600-predrop: walk to next_center before each drop call) | docker PASS | scored, receipt BB-8F12CD09 | 5.71 (-0.54 vs dv600; FALSIFIED) |
| 44 | 829200b919ec9591c2016a9b26ece9bc677a3b05 (dv600-zonecover: inward cover once next_radius<=140) | docker PASS | scored, receipt BB-2D094C73 | 6.19 (-0.06 vs dv600; dropped) |
| 45 | 9515faa1f1a03b0b41e3e577f68958856e314247 (tv-s1: salt-base 2b6fa16, dv600 values, Salt 1) | docker PASS | scored, receipt BB-4FFCCD94 | 5.65 (salt draw; big spread) |
| 46 | 16e14ea95145424f29735e7753bc712a94d7a239 (tv-s2: Salt 2) | docker PASS | scored, receipt BB-9CE0F27F | 5.54 (salt draw) |
| 47 | 40a1791d9b144a1937c9e0696cab7db96f9638f8 (tv-s3: Salt 3) | docker PASS | scored, receipt BB-27D6721D | 5.38 (salt draw) |
| 48 | 477ce204451a51325467150b8cfcdc1fcd6cb673 (dv600-roof: rooftop fortress, Roof=1) | docker PASS | scored, receipt BB-521E15CE | 4.69 (-1.56 vs dv600; FALSIFIED) |
| 49 | 2cd669ff2155b19b7d20f810edd174663149e680 (dv600-roof-lite: Roof=2, climbs only after contact) | docker PASS | scored, receipt BB-1CE6B233 | 4.58 (-1.67 vs dv600; FALSIFIED) |
| 50 | 54a8db93c9ffaff677bd49e981f17b5fece4f872 (dv600-drone: DroneLaser) | docker PASS | scored, receipt BB-5E6CF520 | **6.29 (+0.04 vs dv600): NEW BEST** |
| 51 | b67834990a65c9932e211e1d05d1af306b5fbf48 (dv600-kite: zone kiting) | docker PASS | scored, receipt BB-F72C08F5 | 5.98 (-0.27 vs dv600; dropped) |
