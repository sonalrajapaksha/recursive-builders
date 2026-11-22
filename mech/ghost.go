package mech

import "math"

// npcGone (Params.DroneGhost, squad profile only via tune.json): the base never
// deletes a dead drone; its track stays in b.npcs, so chooseLoot keeps it as
// the loot target (value 85, x1.35 as the current target) for up to 12 s after
// it died. For the first second the bot even keeps shooting/charging at the
// empty spot (farm = ghost), then walks to it and stands there, ahead of the 2
// cubes (value 75) it dropped. A drone the server stopped listing while we
// could plainly see where it was is dead (live drones stay listed for
// memory_s after leaving view), and an unlisted one whose last spot is inside
// our proximity range with clear sight is not there: forget it.
func (b *Brain) npcGone(t *Track, me *Self, eye Vec3, now float64) bool {
	if t.Seen == now {
		return false
	}
	dx, dy := t.Pos[0]-me.Pos[0], t.Pos[1]-me.Pos[1]
	d := hyp(dx, dy)
	v := &b.Cfg.Vision
	in := d < v.NearRange-3
	if !in && now-t.Seen < 0.35 && d < v.Range-10 {
		in = math.Abs(angDiff(math.Atan2(dy, dx), me.Aim[0])) < v.FovDeg*math.Pi/360-0.17
	}
	return in && b.W.Clear(eye, b.center(t))
}
