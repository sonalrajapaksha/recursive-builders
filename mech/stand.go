package mech

import "math"

// droneStand (Params.DroneStand, squad profile only via tune.json): prefRange
// holds every drone at 58 m, but the strict drone-laser gate (DroneRange 55)
// only lets the laser fire inside 55 m, so the farm circles just outside the
// gate and the laser fires only when drift brings it in. When the laser gate
// would otherwise pass (laser ready or charging, HP and quiet gates as in
// droneLaserOK), stand at DroneRange-DroneStand instead (51 m: still outside
// the 45 m drone aggro range). Otherwise the base 58 m.
func (b *Brain) droneStand(me *Self, t *Track, laser *WeaponState) (float64, bool) {
	if b.P.DroneStand <= 0 || laser == nil || (laser.Cooldown > 0.5 && laser.Charge <= 0) {
		return 0, false
	}
	var seen []*Track
	for _, m := range b.tracks {
		seen = append(seen, m)
	}
	r := b.P.DroneRange - b.P.DroneStand
	if !b.droneLaserOK(t, seen, me.HP/math.Max(1, me.MaxHP), r) {
		return 0, false
	}
	return r, true
}
