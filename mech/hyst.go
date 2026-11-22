package mech

// droneGateDist (Params.DroneHyst, squad profile only via tune.json): the bot
// holds drones at prefRange 58 m (fightMove), just outside the strict laser
// gate (DroneRange 55), so strafing and drone wander flick the gate open and
// shut. When it shuts mid-charge the laser case breaks with Fire=false, which
// releases the trigger: a partial-charge beam (35% at min charge) plus the
// 1.65 s cooldown. Once a charge is in progress, let it finish within
// DroneRange+DroneHyst; starting a charge still needs DroneRange, and the HP
// and quiet gates are unchanged.
func (b *Brain) droneGateDist(dist, charge float64) float64 {
	if charge > 0 && b.P.DroneHyst > 0 {
		return dist - b.P.DroneHyst
	}
	return dist
}
