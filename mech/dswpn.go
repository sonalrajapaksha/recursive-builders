package mech

// droneLightOK (Params.DroneLight, squad profile only via tune.json).
//
// The base already lets lightning fire at any shootable target (the weapon
// switch in step() has no isMech check for "lightning"), but prefRange pins
// every NPC drone at 58 m and the crate branch holds us anywhere in 12-50 m,
// while lightning only fires inside Range-1.5 (43.5 m). So a lightning holder
// farms drones with the gun alone (~100 dps sustained incl. reloads) instead
// of lightning (60 dmg / 0.25 s = 240 dps, chaining to nearby drones/crates).
// The mortar is never held (NoMortar makes wantPickup refuse it), so a mortar
// change would be dead code. This gate only closes the farm range to
// DroneLightR when we hold lightning with spare energy (it costs 3/shot and
// boost energy is our escape), are healthy (DroneHP) and no mech has been seen
// within DroneQuiet in the last 1.5 s; otherwise the base 58 m / 12-50 m.
func (b *Brain) droneLightOK(me *Self) bool {
	if !b.P.DroneLight || me.HP < b.P.DroneHP*me.MaxHP || me.Energy < 40 {
		return false
	}
	if _, l := hasWeapon(me.Weapons, "lightning"); l == nil {
		return false
	}
	for _, t := range b.tracks {
		if b.now-t.Seen < 1.5 && t.Dist < b.P.DroneQuiet {
			return false
		}
	}
	return true
}
