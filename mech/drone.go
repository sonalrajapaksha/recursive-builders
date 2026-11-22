package mech

// droneLaserOK (Params.DroneLaser, squad profile only via tune.json): the base
// farms NPC drones with gun/lightning but never fires the laser at them. A
// full laser (315 dmg) takes most of a 350 HP drone, so the farm (and the time
// we stand in the open) is much shorter. Only when the drone is the current
// farm target, close, no mech is seen within 80 m (the charge is audible),
// and we are healthy; otherwise base behaviour.
func (b *Brain) droneLaserOK(farm *Track, seen []*Track, hpFrac, dist float64) bool {
	if !b.P.DroneLaser || farm == nil || farm.Kind != "npc" || hpFrac < b.P.DroneHP || dist > b.P.DroneRange {
		return false
	}
	for _, t := range seen {
		if b.now-t.Seen < 1.5 && t.Dist < b.P.DroneQuiet {
			return false
		}
	}
	return true
}
