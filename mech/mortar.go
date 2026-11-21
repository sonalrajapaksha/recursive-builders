package mech

import "math"

// Mortar battery (Params.MortarBattery): the mortar is only lobbed (high arc,
// led by flight time) at clustered or stationary / covered targets 35-200 m
// away. Never at mobile single targets, never when an enemy laser has line of
// sight to us (laser beats mortar), never when the impact could splash us.
func (b *Brain) mortarBattery(o *Obs, target *Track, aim *[2]float64, act *Action) {
	me := &o.Self
	now := b.now
	st := &me.Stats
	mi, w := hasWeapon(me.Weapons, "mortar")
	if w == nil || mi > 1 || w.Cooldown > 0.25 {
		return
	}
	var c []*Track
	for _, t := range b.tracks {
		age := now - t.Seen
		if age > 1.5 {
			continue
		}
		if age < 1 && t.LOS && holds(t.Weapons, "laser") && t.Dist < 280 {
			return // enemy laser sees us: do not stand and lob
		}
		if age < 1 && t.Dist < 30 {
			return // too close: base fight logic
		}
		d := hyp(t.Pos[0]-me.Pos[0], t.Pos[1]-me.Pos[1])
		if d >= 35 && d <= 200 {
			c = append(c, t)
		}
	}
	var imp, vel Vec3
	found, cluster := false, false
	bestD := math.Inf(1)
	for i, a := range c {
		for _, e := range c[i+1:] {
			if hyp(a.Pos[0]-e.Pos[0], a.Pos[1]-e.Pos[1]) > 8 {
				continue
			}
			m := Vec3{(a.Pos[0] + e.Pos[0]) / 2, (a.Pos[1] + e.Pos[1]) / 2, (a.Pos[2] + e.Pos[2]) / 2}
			if d := hyp(m[0]-me.Pos[0], m[1]-me.Pos[1]); d < bestD {
				bestD, found, cluster = d, true, true
				imp = m
				vel = Vec3{(a.Vel[0] + e.Vel[0]) / 2, (a.Vel[1] + e.Vel[1]) / 2, 0}
			}
		}
	}
	if !found {
		for _, t := range c {
			if hyp(t.Vel[0], t.Vel[1]) >= 1.2 || t.Dist < 40 {
				continue
			}
			if d := hyp(t.Pos[0]-me.Pos[0], t.Pos[1]-me.Pos[1]); d < bestD {
				bestD, found = d, true
				imp, vel = t.Pos, Vec3{}
			}
		}
	}
	if !found || hyp(imp[0]-me.Pos[0], imp[1]-me.Pos[1]) < 16 {
		return
	}
	if target != nil && !cluster {
		return // a visible mobile/closer fight is handled by the base logic
	}
	if target != nil && target.Dist < 60 {
		return
	}
	tube := Vec3{me.Pos[0] + me.Vel[0]*lat, me.Pos[1] + me.Vel[1]*lat, me.Pos[2] + st.Height + 0.5}
	yaw, pitch, ok := b.mortarArc(tube, imp, vel, w.Stats.Speed, w.Stats.Gravity, st, true)
	if !ok {
		yaw, pitch, ok = b.mortarArc(tube, imp, vel, w.Stats.Speed, w.Stats.Gravity, st, false)
	}
	if !ok {
		return
	}
	*aim = [2]float64{yaw, pitch}
	ey := math.Max(0, math.Abs(angDiff(yaw, me.Aim[0]))-st.TurnRate*0.05)
	ep := math.Max(0, math.Abs(pitch-me.Aim[1])-st.PitchRate*0.05)
	if ey < 0.04 && ep < 0.03 {
		act.Fire[mi] = true
	}
}
