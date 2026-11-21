# PROGRESS (resume here)
Goal: Mech Royale. Score=mean(16-place). Need top 20 (~5.1+). Best so far: aggressor2 a6eb860 = 4.31 (audit-aggressor 4.25).
Layout: bot.py -> policy.py -> nav.py. INTERFACE.md contract. Branches on origin: audit-fixes, aggressor, audit-aggressor, aggressor2, survival-hider.
Learned: passivity LOSES (2.15). Bug fixes + aggression WIN (4.25). Site: one submission scoring at a time, 4/hr. Local sim unreliable.
Flow: worker branch -> docker amd64 sandbox check.py -> push branch -> submit commit via Chrome -> record SUBMISSIONS.md.
Next: read aggressor2 score (BB-FF691224); keep the best as base; iterate on combat quality.
