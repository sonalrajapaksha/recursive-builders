package mech

// farmReach (Params.FarmReach > 0, squad profile only via tune.json).
//
// Squad chooseLoot (non-econ path) considers cubes within max(60, 0.7*R),
// crates and remembered NPC drones within R = LootRadius (150). A flat R of 220
// lost (tv-loot220 6.06): the longer walks expose us. Here the reach for
// cubes/crates/drones (not weapon pickups, not drops) grows to FarmReach only
// while we are healthy (hp > FarmGateHP) and no mech has been seen within
// FarmQuiet of us in the last FarmQuietS seconds; any sighting or damage
// below the HP gate shrinks it straight back to LootRadius, so a long walk is
// abandoned (chooseLoot re-picks every tick) as soon as a mech shows up.
// consider() still caps every target at 260 m and keeps the zone checks.
func (b *Brain) farmReach(hpFrac float64) float64 {
	r := b.P.LootRadius
	if b.P.FarmReach <= r || hpFrac <= b.P.FarmGateHP {
		return r
	}
	for _, t := range b.tracks {
		if b.now-t.Seen < b.P.FarmQuietS && t.Dist < b.P.FarmQuiet {
			return r
		}
	}
	return b.P.FarmReach
}
