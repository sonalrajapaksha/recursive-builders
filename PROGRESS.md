# PROGRESS (resume here)
Goal: Mech Royale. Score=mean(16-place). Top-20 line moving (~5.5+). Best: combo2 bff0082 = 4.54.
Layout: bot.py -> policy.py -> nav.py. INTERFACE.md contract. Branches on origin: audit-fixes, aggressor, audit-aggressor, aggressor2, survival-hider.
Learned: passivity LOSES (2.15). Bug fixes + aggression WIN (4.25). Site: one submission scoring at a time, 4/hr. Local sim unreliable.
Flow: worker branch -> docker amd64 sandbox check.py -> push branch -> submit commit via Chrome -> record SUBMISSIONS.md.
Next: read aggressor2 score (BB-FF691224); keep the best as base; iterate on combat quality.
Base for new work: branch combo2 (bff0082). Diagnostics running: diag-self (from combo1), diag-bots (from combo2).
Submit queue (one per free slot, record each): 1) laser-cover 430547c 2) abl-shootback b5bcf62 3) abl-quiet 520c57f 4) abl-reload 3734583 5) diag-bots 108a18b. All docker-validated. Next slot 5:53 AM EST. Base = combo2 bff0082 (4.54).
