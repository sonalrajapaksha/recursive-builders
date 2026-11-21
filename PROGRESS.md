# PROGRESS (resume here)
Goal: Mech Royale (mechfight/1). Score = mean(16-place) over FFA matches; top 32 practice -> qualification -> 16 finals.
Limits (protocol.md §3): 1 CPU, 512MB, 50ms/decision, RO root, 64MB /tmp, 20MB repo, 10min build, linux/amd64.

## Layout
bot.py (entry) -> policy.py (decisions) -> nav.py (map/A*/stuck). mechfight.py = starter wrapper. INTERFACE.md = contract.
tests/ (unittest: `python3 -I -m unittest discover -s tests`), eval/ (sim approximation, latency, synthetic, STRATEGY.md).

## Status
- v1 baseline built by 3 workers (Sonnet nav, Sonnet policy, Terra eval). All local tests pass.
- Official check.py: PASS native (p99 1.5ms) and in Docker sandbox amd64 (p99 3.2ms emulated).
- eval/sim.py is a crude approximation, NOT a real match. Real scores only come from the site.
## Next
1. Submit v1 via joinbuilders.org (Chrome ext), record in SUBMISSIONS.md. Quota 4/hour.
2. Read score + leaderboard; target weakest area (see EXPERIMENTS.md, eval/STRATEGY.md).
