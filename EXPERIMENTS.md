# EXPERIMENTS (real measurements only)
| id | what | result |
|----|------|--------|
| E1 | starter example_bot via check.py | PASS 300/300, p99 9.3ms |
| E2 | v1 bot.py native check.py | PASS 300/300, p50 0.2 p99 1.5 max 1.8 ms |
| E3 | v1 Docker amd64 + full sandbox flags, check.py --map-dir /arena | PASS 300/300, p50 0.8 p99 3.2 max 7.6 ms (arm host emulating amd64) |
| E4 | unit tests nav(11)/policy(19)/replay(2) | pass |
Known: nav A* replan can hit 12ms cap; replay latency tests fall back to no-nav because recorded hello map dir is not local.
