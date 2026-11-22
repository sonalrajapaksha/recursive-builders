package mech

import "math"

// Zone kiting (Params.Kite, practice profile only via tune.json).
// While a hunter closes on us and the zone is shrinking, walk tangentially
// just inside the shrinking edge so the edge sweeps over a chaser that
// follows from outside our radius. Every check failing returns false and the
// base logic runs unchanged.
type kiteState struct {
	on           bool
	since, hp0   float64
	sign         float64
	coolUntil    float64
	progAt       float64
	progX, progY float64
	chaserOutAt  float64
}

// kiteDir returns the unit tangential direction at (x,y) around centre (cx,cy)
// with sign +1 = counter-clockwise, plus a radial correction toward radius r.
func kiteDir(x, y, cx, cy, r, sign float64) (float64, float64) {
	dx, dy := x-cx, y-cy
	d := hyp(dx, dy)
	if d < 1 {
		return 0, 0
	}
	ux, uy := dx/d, dy/d
	tx, ty := -uy*sign, ux*sign
	k := clamp((r-d)/10, -1, 1) // push outward if inside r, inward if beyond
	mx, my := tx+ux*k*0.6, ty+uy*k*0.6
	l := hyp(mx, my)
	return mx / l, my / l
}

func (b *Brain) kite(o *Obs, seen []*Track, hpFrac float64, mx, my *float64) bool {
	k := &b.kiteS
	me := &o.Self
	z := &o.Zone
	now := b.now
	x, y := me.Pos[0], me.Pos[1]
	stop := func(cool float64) bool {
		if k.on {
			k.on = false
			k.coolUntil = now + cool
		}
		return false
	}
	if !b.P.Kite || now < k.coolUntil || !me.InZone || z.NextRadius < 140 || o.Alive <= 4 {
		return stop(0)
	}
	shrinking := now >= z.ShrinkStart-8 && now < z.ShrinkEnd
	if !shrinking || hpFrac < 0.55 || now-b.lastHurt < 2.5 {
		return stop(15)
	}
	cur := b.curZone(z)
	fut := b.zoneAt(z, now+5)
	myR := hyp(x-cur.X, y-cur.Y)
	var ch *Track
	near := 0
	for _, t := range seen {
		if t.Seen != now {
			continue
		}
		if t.Dist < 160 {
			near++
		}
		if t.Dist < 120 && t.Closing > 1 && (ch == nil || t.Dist < ch.Dist) {
			ch = t
		}
	}
	if ch == nil || near > 1 || ch.Dist < 40 || now-ch.HitMe < 4 {
		return stop(10)
	}
	chR := hyp(ch.Pos[0]-cur.X, ch.Pos[1]-cur.Y)
	// Chaser must be on the outer side of us: the edge reaches it first.
	if chR < myR-5 {
		return stop(10)
	}
	if !k.on {
		k.on, k.since, k.hp0 = true, now, hpFrac
		k.progAt, k.progX, k.progY, k.chaserOutAt = now, x, y, -1
		// Run away from the chaser around the circle.
		a := math.Atan2(y-cur.Y, x-cur.X)
		c := math.Atan2(ch.Pos[1]-cur.Y, ch.Pos[0]-cur.X)
		k.sign = 1
		if angDiff(a, c) < 0 {
			k.sign = -1
		}
	}
	if chR > cur.R {
		k.chaserOutAt = now
	}
	// Abort: too long, hp falling, no progress, or chaser never in the zone damage.
	if now-k.since > 14 || hpFrac < k.hp0-0.08 {
		return stop(25)
	}
	if now-k.since > 7 && (k.chaserOutAt < 0 || now-k.chaserOutAt > 4) {
		return stop(25)
	}
	if now-k.progAt > 1.5 {
		if hyp(x-k.progX, y-k.progY) < 3 {
			return stop(20)
		}
		k.progAt, k.progX, k.progY = now, x, y
	}
	rT := math.Min(cur.R, fut.R) - 10
	if hyp(x-fut.X, y-fut.Y) > fut.R-4 {
		return stop(20) // about to be caught by the edge ourselves
	}
	for try := 0; try < 2; try++ {
		dx, dy := kiteDir(x, y, fut.X, fut.Y, rT, k.sign)
		gx, gy := x+dx*16, y+dy*16
		if b.W.LineWalkable(x, y, gx, gy) && hyp(gx-fut.X, gy-fut.Y) < fut.R-6 &&
			b.W.LineWalkable(gx, gy, gx+dx*10, gy+dy*10) {
			q := math.Min(1, 4.6/math.Max(1, me.Stats.WalkSpeed))
			*mx, *my = dx*q, dy*q
			return true
		}
		if try == 0 && now-k.since > 1 {
			break // only choose direction at the start; a wall later means a dead end
		}
		k.sign = -k.sign
	}
	return stop(20)
}
