package mech

import "math"

// Laser ambush (Params.LaserAmbush): when 1-2 hunters are approaching and we
// hold a ready laser, hide beside the hunter's predicted route, begin the
// charge just before it enters our line of sight, and release the instant it
// steps into the lane (hitscan, aimed at the predicted crossing point).
// Everything here is inert unless the trigger fires; otherwise the base
// behaviour is unchanged.

type ambushSt struct {
	on         bool
	hid        int
	cx, cy     float64 // waiting cell
	ex, ey, ez float64 // lane entry point
	tteBase    float64 // seconds from hunter (at planAt) to entry
	hx, hy     float64 // hunter position at planAt
	since      float64
	planAt     float64
	charging   bool
	chargeAt   float64
	doneAt     float64
	mx, my     float64
}

func (b *Brain) ambushEnd(now, cool float64) {
	b.amb.on, b.amb.charging = false, false
	b.amb.doneAt = now + cool
}

// ambushUpdate advances the ambush state machine; returns true while active.
func (b *Brain) ambushUpdate(o *Obs, seen []*Track, target *Track, hpFrac float64, late bool) bool {
	a := &b.amb
	me := &o.Self
	now := b.now
	li, laser := hasWeapon(me.Weapons, "laser")
	_ = li
	if !b.P.LaserAmbush || laser == nil || late {
		a.on = false
		return false
	}
	// hunters: recently seen mechs within 170 m.
	n := 0
	var prim *Track
	var px, py float64
	for _, t := range b.tracks {
		if now-t.Seen > 3 {
			continue
		}
		ex, ey := t.Pos[0]+t.Vel[0]*(now-t.Seen), t.Pos[1]+t.Vel[1]*(now-t.Seen)
		d := hyp(ex-me.Pos[0], ey-me.Pos[1])
		if d > 170 {
			continue
		}
		n++
		sp := hyp(t.Vel[0], t.Vel[1])
		toward := -((t.Vel[0])*(ex-me.Pos[0]) + t.Vel[1]*(ey-me.Pos[1])) / math.Max(d, 1)
		if sp > 2 && toward > 1.5 && d > 40 && (prim == nil || d < hyp(px-me.Pos[0], py-me.Pos[1])) {
			prim, px, py = t, ex, ey
		}
	}
	if a.on {
		t := b.tracks[a.hid]
		abort := t == nil || now-t.Seen > 5 || n > 2 || n == 0 || now-a.since > 14 || hpFrac < 0.5 || b.retreat ||
			laser.Cooldown > 0.6 || laser.Charge > laser.Stats.Charge+laser.Stats.HoldS-0.3
		if !abort {
			for _, s := range seen {
				if s.Seen == now && s.LOS && s.Dist < 22 {
					abort = true
				}
				if s.Seen == now && s.LOS && s.Charging && math.Abs(angDiff(s.Aim[0], math.Atan2(me.Pos[1]-s.Pos[1], me.Pos[0]-s.Pos[0]))) < 0.2 {
					abort = true
				}
			}
		}
		if a.charging && laser.Charge <= 0 && laser.Cooldown > 0.3 {
			b.ambushEnd(now, 6) // fired
			return false
		}
		if abort {
			b.ambushEnd(now, 4)
			return false
		}
		return true
	}
	if now < a.doneAt || prim == nil || n < 1 || n > 2 || hpFrac < 0.65 || target != nil || b.retreat ||
		laser.Cooldown > 0.1 || me.Energy < 5 {
		return false
	}
	if prim.Seen == now && prim.LOS && prim.Dist < 100 {
		return false
	}
	if now-a.planAt < 0.5 {
		return false
	}
	a.planAt = now
	if !b.ambushPlan(o, prim, px, py) {
		return false
	}
	a.on, a.hid, a.since, a.charging = true, prim.ID, now, false
	return true
}

func (b *Brain) ambushPlan(o *Obs, h *Track, hx, hy float64) bool {
	me := &o.Self
	a := &b.amb
	W := b.W
	x, y := me.Pos[0], me.Pos[1]
	path, _ := W.Path(hx, hy, x, y, 6000)
	if len(path) < 4 {
		return false
	}
	type rp struct{ x, y, z, s float64 }
	pts := make([]rp, 0, len(path))
	cum := 0.0
	th := b.Cfg.Mech.Height * b.scaleOf(h.Cubes)
	for i, c := range path {
		cx, cy := W.CellPos(int(c))
		if i > 0 {
			cum += hyp(cx-pts[i-1].x, cy-pts[i-1].y)
		}
		pts = append(pts, rp{cx, cy, W.GroundAt(cx, cy) + th*0.5, cum})
	}
	spd := math.Max(hyp(h.Vel[0], h.Vel[1]), 6)
	walk := me.Stats.WalkSpeed
	if walk <= 0 {
		walk = 10
	}
	zc := b.curZone(&o.Zone)
	best, bestScore := -1, 1e18
	var bc [5]float64
	for _, r := range []float64{5, 10, 17, 25} {
		for k := 0; k < 12; k++ {
			ang := float64(k) * math.Pi / 6
			cx, cy := x+r*math.Cos(ang), y+r*math.Sin(ang)
			if !W.InBounds(cx, cy) || !W.Free(cx, cy) || hyp(cx-zc.X, cy-zc.Y) > zc.R-10 {
				continue
			}
			if r > 6 && !W.LineWalkable(x, y, cx, cy) {
				continue
			}
			mz := Vec3{cx, cy, W.GroundAt(cx, cy) + me.Stats.MuzzleHeight}
			entry := -1
			for i := 0; i < len(pts); i++ {
				d := hyp(pts[i].x-cx, pts[i].y-cy)
				if d > 70 {
					continue
				}
				if W.ShotClear(mz, Vec3{pts[i].x, pts[i].y, pts[i].z}) {
					entry = i
					break
				}
			}
			if entry < 1 {
				continue
			}
			ed := hyp(pts[entry].x-cx, pts[entry].y-cy)
			if ed < 12 || ed > 60 {
				continue
			}
			tte := pts[entry].s / spd
			travel := r/walk + 0.8
			if tte < travel+1.0 {
				continue
			}
			lane := 0
			for i := entry; i < len(pts) && lane < 6; i++ {
				if !W.ShotClear(mz, Vec3{pts[i].x, pts[i].y, pts[i].z}) {
					break
				}
				lane++
			}
			s := r*0.5 + math.Abs(ed-30) + 3*float64(lane)
			if s < bestScore {
				bestScore, best = s, entry
				bc = [5]float64{cx, cy, pts[entry].x, pts[entry].y, pts[entry].z}
			}
		}
	}
	if best < 0 {
		return false
	}
	a.cx, a.cy, a.ex, a.ey, a.ez = bc[0], bc[1], bc[2], bc[3], bc[4]
	a.tteBase, a.hx, a.hy = pts[best].s/spd, hx, hy
	return true
}

// ambushMove returns the movement for the active ambush.
func (b *Brain) ambushMove(me *Self) (float64, float64) {
	a := &b.amb
	if hyp(a.cx-me.Pos[0], a.cy-me.Pos[1]) > 1.2 {
		return b.travel(me, a.cx, a.cy)
	}
	return 0, 0
}

// ambushFire overrides aim and the laser trigger while the ambush is active.
func (b *Brain) ambushFire(o *Obs, aim *[2]float64, act *Action) {
	a := &b.amb
	me := &o.Self
	now := b.now
	st := &me.Stats
	li, laser := hasWeapon(me.Weapons, "laser")
	t := b.tracks[a.hid]
	if laser == nil || t == nil || li > 1 {
		return
	}
	muzzle := Vec3{me.Pos[0] + me.Vel[0]*lat, me.Pos[1] + me.Vel[1]*lat, me.Pos[2] + st.MuzzleHeight}
	arrived := hyp(a.cx-me.Pos[0], a.cy-me.Pos[1]) <= 1.6
	full := laser.Stats.Charge
	lane := t.Seen == now && t.LOS && t.Dist < laser.Stats.Range*0.95
	if lane {
		sc := b.scaleOf(t.Cubes)
		th := b.Cfg.Mech.Height * sc
		dp := Vec3{t.Pos[0] + t.Vel[0]*(lat+0.05), t.Pos[1] + t.Vel[1]*(lat+0.05), t.Pos[2] + th*0.5}
		if !b.W.Clear(muzzle, dp) {
			dp[2] = t.Pos[2] + th*0.85
		}
		hy := math.Atan2(dp[1]-muzzle[1], dp[0]-muzzle[0])
		hp := math.Atan2(dp[2]-muzzle[2], hyp(dp[0]-muzzle[0], dp[1]-muzzle[1]))
		*aim = [2]float64{hy, hp}
		dist := hyp(dp[0]-muzzle[0], dp[1]-muzzle[1])
		ey := math.Abs(angDiff(hy, me.Aim[0]))
		ep := math.Abs(hp - me.Aim[1])
		tolY := math.Atan2(b.Cfg.Mech.Radius*sc*0.7, math.Max(dist, 1))
		tolP := math.Atan2(th*0.4, math.Max(dist, 1))
		if laser.Charge >= full-0.05 && ey < tolY && ep < tolP {
			act.Fire[li] = false // release
		} else {
			act.Fire[li] = true
			a.charging = true
		}
		return
	}
	// waiting out of sight: face the lane entry, charge when the hunter is close to it.
	if !arrived {
		act.Fire[li] = false
		return
	}
	hy := math.Atan2(a.ey-muzzle[1], a.ex-muzzle[0])
	hp := math.Atan2(a.ez-muzzle[2], hyp(a.ex-muzzle[0], a.ey-muzzle[1]))
	*aim = [2]float64{hy, hp}
	tte := a.tteBase - (now - a.planAt)
	// replan the arrival time from the freshest hunter sighting
	if t.Seen > a.planAt {
		d := hyp(t.Pos[0]-a.ex, t.Pos[1]-a.ey)
		tte = d/math.Max(hyp(t.Vel[0], t.Vel[1]), 6) - (now - t.Seen)
	}
	if tte <= full+0.3 || a.charging {
		act.Fire[li] = true
		if !a.charging {
			a.charging, a.chargeAt = true, now
		}
	} else {
		act.Fire[li] = false
	}
}
