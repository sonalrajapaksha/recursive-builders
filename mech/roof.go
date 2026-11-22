package mech

import (
	"math"
	"time"
)

// Rooftop fortress (Params.Roof: 0 off, 1 full, 2 lite = climb only after a
// mech has been seen or has hurt us). Roof cells are the nav cells buildNav
// blocks as roofs; regions are 4-connected roof cells within step_up.

type RoofRegion struct {
	Z, Ground  float64
	Cells      int
	OnFoot     bool       // some edge steps down <= step_up onto walkable ground
	Open       int        // edge cells next to reachable ground (approaches)
	Hold       [2]float64 // interior point farthest from the edges
	HoldDepth  int        // cells from Hold to the nearest edge
	Launch     [][4]float64
	HigherNear int
}

type RoofMap struct {
	Of      []int32 // nav cell -> region index, -1 if none
	Depth   []uint8 // nav cell -> cells to region edge
	Regions []RoofRegion
}

var roofCache struct {
	w *World
	m *RoofMap
}

func (w *World) Roofs() *RoofMap {
	if roofCache.w == w {
		return roofCache.m
	}
	n := w.NNX * w.NNY
	m := &RoofMap{Of: make([]int32, n), Depth: make([]uint8, n)}
	roof := func(c int) bool {
		x, y := w.CellPos(c)
		return w.Blocked[c] && float64(w.Surf[c])-w.GroundAt(x, y) > 2.5
	}
	isRoof := make([]bool, n)
	for c := range isRoof {
		m.Of[c] = -1
		isRoof[c] = roof(c)
	}
	d4 := [4][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
	nb := func(c, k int) int {
		i, j := c%w.NNX+d4[k][0], c/w.NNX+d4[k][1]
		if i < 0 || j < 0 || i >= w.NNX || j >= w.NNY {
			return -1
		}
		return j*w.NNX + i
	}
	q := make([]int32, 0, 4096)
	edge := make([]int32, 0, 1024)
	for c0 := 0; c0 < n; c0++ {
		if !isRoof[c0] || m.Of[c0] >= 0 {
			continue
		}
		id := int32(len(m.Regions))
		r := RoofRegion{}
		q = append(q[:0], int32(c0))
		m.Of[c0] = id
		sz, sg := 0.0, 0.0
		for h := 0; h < len(q); h++ {
			c := int(q[h])
			x, y := w.CellPos(c)
			sz += float64(w.Surf[c])
			sg += w.GroundAt(x, y)
			for k := 0; k < 4; k++ {
				o := nb(c, k)
				if o >= 0 && isRoof[o] && m.Of[o] < 0 && math.Abs(float64(w.Surf[o]-w.Surf[c])) <= StepUp {
					m.Of[o] = id
					q = append(q, int32(o))
				}
			}
		}
		r.Cells = len(q)
		r.Z, r.Ground = sz/float64(r.Cells), sg/float64(r.Cells)
		// edges: multi-source BFS for interior depth, record launch pairs.
		edge = edge[:0]
		for _, c32 := range q {
			c := int(c32)
			isEdge := false
			for k := 0; k < 4; k++ {
				o := nb(c, k)
				if o < 0 || m.Of[o] != id {
					isEdge = true
					if o >= 0 && isRoof[o] {
						continue
					}
					for s := 0; s < 3 && o >= 0 && w.Blocked[o]; s++ {
						o = nb(o, k) // walls keep nav cells blocked ~1-2 cells out
					}
					if o >= 0 && !w.Blocked[o] && w.Comp[o] == w.MainComp {
						r.Open++
						if float64(w.Surf[c]-w.Surf[o]) <= StepUp {
							r.OnFoot = true
						}
						if len(r.Launch) < 48 && r.Open%3 == 1 {
							gx, gy := w.CellPos(o)
							ex, ey := w.CellPos(c)
							r.Launch = append(r.Launch, [4]float64{gx - (ex-gx)*0.5, gy - (ey-gy)*0.5, ex, ey})
						}
					}
				}
			}
			if isEdge {
				m.Depth[c] = 1
				edge = append(edge, c32)
			}
		}
		for h := 0; h < len(edge); h++ {
			c := int(edge[h])
			for k := 0; k < 4; k++ {
				if o := nb(c, k); o >= 0 && m.Of[o] == id && m.Depth[o] == 0 && m.Depth[c] < 250 {
					m.Depth[o] = m.Depth[c] + 1
					edge = append(edge, int32(o))
				}
			}
		}
		best := int(q[0])
		for _, c := range q {
			if m.Depth[c] > m.Depth[best] {
				best = int(c)
			}
		}
		r.Hold[0], r.Hold[1] = w.CellPos(best)
		r.HoldDepth = int(m.Depth[best])
		m.Regions = append(m.Regions, r)
	}
	for i := range m.Regions {
		a := &m.Regions[i]
		for j := range m.Regions {
			b := &m.Regions[j]
			if i != j && b.Cells >= 30 && b.Z >= a.Z-3 && hyp(a.Hold[0]-b.Hold[0], a.Hold[1]-b.Hold[1]) < 90 {
				a.HigherNear++
			}
		}
	}
	roofCache.w, roofCache.m = w, m
	return m
}

// Usable reports whether a region is a fortress candidate at all.
func (r *RoofRegion) Usable() bool {
	h := r.Z - r.Ground
	return r.Cells >= 50 && r.HoldDepth >= 3 && h >= 4 && h <= 42 && len(r.Launch) > 0
}

type roofState struct {
	m          *RoofMap
	reg        int // chosen region, -1 none
	phase      int // 0 idle, 1 approach, 2 climb, 3 hold
	launch     [4]float64
	since      float64
	hpIn       float64
	aliveIn    int
	aliveAt    float64
	pickAt     float64
	off        float64 // cooldown until
	fails      int
	bad        map[int]float64
	stall      float64
	seenMech   bool
	lastAction string
}

func (b *Brain) roofRegionAt(x, y, zf float64) int {
	m := b.roof.m
	c := b.W.Cell(x, y)
	if r := m.Of[c]; r >= 0 && math.Abs(zf-m.Regions[r].Z) < 1.6 {
		return int(r)
	}
	return -1
}

func (b *Brain) roofAbandon(cool float64) {
	rs := &b.roof
	if rs.reg >= 0 {
		rs.bad[rs.reg] = b.now + 90
	}
	rs.reg, rs.phase, rs.off = -1, 0, b.now+cool
	rs.fails++
}

func (b *Brain) roofPick(o *Obs) {
	rs := &b.roof
	me := &o.Self
	x, y := me.Pos[0], me.Pos[1]
	t0 := time.Now()
	best, bestC := -1, math.Inf(1)
	var bestL [4]float64
	for i := range rs.m.Regions {
		r := &rs.m.Regions[i]
		if !r.Usable() || rs.bad[i] > b.now || hyp(r.Hold[0]-x, r.Hold[1]-y) > 260 {
			continue
		}
		if b.zoneDeadline(&o.Zone, r.Hold[0], r.Hold[1], 10) < b.now+60 {
			continue
		}
		var l [4]float64
		dl := math.Inf(1)
		for _, c := range r.Launch {
			if d := hyp(c[0]-x, c[1]-y); d < dl && b.W.Reachable(c[0], c[1]) {
				dl, l = d, c
			}
		}
		if math.IsInf(dl, 1) {
			continue
		}
		cost := dl + 18*float64(r.HigherNear) + 0.5*float64(r.Open) - math.Min(float64(r.Cells), 400)/8
		if r.OnFoot {
			cost += 80
		}
		for _, k := range b.crates {
			if b.roofRegionAt(k.Pos[0], k.Pos[1], k.Pos[2]) == i {
				cost -= 40
			}
		}
		for _, k := range b.pickups {
			if b.roofRegionAt(k.Pos[0], k.Pos[1], k.Pos[2]) == i {
				cost -= 30
			}
		}
		if cost < bestC {
			best, bestC, bestL = i, cost, l
		}
		if time.Since(t0) > 4*time.Millisecond {
			break
		}
	}
	rs.reg, rs.launch, rs.pickAt = best, bestL, b.now
	if best >= 0 {
		rs.phase, rs.since = 1, b.now
	}
}

// roofStep may override movement after the base logic. It returns true when
// it took control. base is the mode chosen by the base logic.
func (b *Brain) roofStep(o *Obs, base string, zoneMust bool, mx, my *float64, boost, jump *bool) bool {
	me := &o.Self
	rs := &b.roof
	now := b.now
	x, y, zf := me.Pos[0], me.Pos[1], me.Pos[2]
	if rs.m == nil {
		rs.m, rs.reg, rs.bad = b.W.Roofs(), -1, map[int]float64{}
	}
	for _, t := range b.tracks {
		if now-t.Seen < 0.2 || now-t.HitMe < 1 {
			rs.seenMech = true
		}
	}
	if rs.fails >= 4 || now < rs.off || now < 22 {
		return false
	}
	if zoneMust && rs.phase != 2 {
		if rs.phase != 0 {
			rs.reg, rs.phase = -1, 0
		}
		return false
	}
	if rs.phase == 0 {
		if b.P.Roof >= 2 && !rs.seenMech {
			return false
		}
		if base != "idle" && base != "home" && base != "zone-walk" && base != "explore" && base != "zone" &&
			(len(base) < 5 || base[:5] != "loot:") {
			return false
		}
		if now-rs.pickAt < 3 {
			return false
		}
		b.roofPick(o)
		if rs.reg < 0 {
			return false
		}
	}
	r := &rs.m.Regions[rs.reg]
	on := me.Grounded && b.roofRegionAt(x, y, zf) == rs.reg
	foe := false
	for _, t := range b.tracks {
		if now-t.Seen < 0.3 && t.Dist < 30 && math.Abs(t.Pos[2]-r.Z) < 3 {
			foe = true
		}
	}
	switch rs.phase {
	case 1: // walk to the launch point, then wait for energy (silently)
		if on {
			rs.phase, rs.since, rs.hpIn, rs.aliveIn, rs.aliveAt = 3, now, me.HP, o.Alive, now
			break
		}
		if base == "fight" || base == "cover" || base == "flee" || base == "cornered" || base == "dodge" || base == "escape" {
			return false // base handles threats while we are still on the ground
		}
		if (len(base) > 5 && base[:5] == "loot:" && now < 60) || now-rs.since > 45 {
			if now-rs.since > 45 {
				b.roofAbandon(20)
			}
			return false
		}
		lx, ly := rs.launch[0], rs.launch[1]
		if d := hyp(lx-x, ly-y); d > 1.5 {
			*mx, *my = b.travel(me, lx, ly)
			return true
		}
		need := math.Min(me.MaxEnergy, (r.Z-zf+3)*1.75+12)
		*mx, *my = 0, 0
		if me.Energy >= need && me.Grounded {
			*jump = true
			rs.phase, rs.since, rs.stall = 2, now, now
		}
		return true
	case 2: // airborne: jet until feet clear the roof line, then move over it
		if on {
			rs.phase, rs.since, rs.hpIn, rs.aliveIn, rs.aliveAt = 3, now, me.HP, o.Alive, now
			break
		}
		if me.Grounded && now-rs.since > 0.4 {
			rs.fails++
			rs.phase = 1
			if rs.fails%2 == 0 {
				b.roofAbandon(10)
			}
			return false
		}
		tx, ty := rs.launch[2], rs.launch[3]
		dx, dy := r.Hold[0]-tx, r.Hold[1]-ty
		if l := hyp(dx, dy); l > 0.1 {
			tx, ty = tx+dx/l*math.Min(5, l), ty+dy/l*math.Min(5, l)
		}
		d := hyp(tx-x, ty-y)
		if d > 0.3 {
			*mx, *my = (tx-x)/d, (ty-y)/d
		}
		*boost = zf < r.Z+1.5 && me.Energy > 1
		if me.Vel[2] > 0.5 || !*boost {
			rs.stall = now
		} else if now-rs.stall > 1.2 { // eave or ceiling: give up on this roof
			b.roofAbandon(10)
			return false
		}
		*jump = false
		return true
	}
	// phase 3: hold the roof
	if !on {
		if me.Grounded {
			rs.phase, rs.since = 1, now
			rs.fails++
			return false
		}
		return true // still landing or stepping across a seam
	}
	if o.Alive != rs.aliveIn {
		rs.aliveIn, rs.aliveAt = o.Alive, now
	}
	switch {
	case foe:
		b.roofAbandon(30)
		return false
	case rs.hpIn-me.HP > 0.35*me.MaxHP && now-b.lastHurt < 3:
		b.roofAbandon(40)
		return false
	case now-rs.aliveAt > 150:
		b.roofAbandon(60)
		return false
	case b.zoneDeadline(&o.Zone, r.Hold[0], r.Hold[1], 8) < now+25:
		rs.reg, rs.phase = -1, 0 // move on: base walks off, we re-pick later
		return false
	}
	if me.HP > rs.hpIn {
		rs.hpIn = me.HP
	}
	if base == "loot:drop" {
		for _, d := range o.Drops {
			if hyp(d.Pos[0]-r.Hold[0], d.Pos[1]-r.Hold[1]) < 30 && len(b.tracks) == 0 {
				rs.reg, rs.phase = -1, 0
				return false
			}
		}
	}
	gx, gy := r.Hold[0], r.Hold[1]
	got := false
	for _, k := range b.cubes {
		if b.roofRegionAt(k.Pos[0], k.Pos[1], k.Pos[2]) == rs.reg {
			gx, gy, got = k.Pos[0], k.Pos[1], true
		}
	}
	for _, k := range b.pickups {
		if !got && b.roofRegionAt(k.Pos[0], k.Pos[1], k.Pos[2]) == rs.reg && b.wantPickup(me, k.Kind) {
			gx, gy, got = k.Pos[0], k.Pos[1], true
		}
	}
	if !got { // lean toward the edge facing the nearest seen mech (lane)
		var near *Track
		for _, t := range b.tracks {
			if now-t.Seen < 2 && t.Dist < 200 && (near == nil || t.Dist < near.Dist) {
				near = t
			}
		}
		if near != nil {
			ux, uy := near.Pos[0]-r.Hold[0], near.Pos[1]-r.Hold[1]
			if l := hyp(ux, uy); l > 1 {
				for s := 2.0; s < 80; s += 2 {
					px, py := r.Hold[0]+ux/l*s, r.Hold[1]+uy/l*s
					c := b.W.Cell(px, py)
					if int(rs.m.Of[c]) != rs.reg || rs.m.Depth[c] < 3 {
						break
					}
					gx, gy = px, py
				}
			}
		}
	}
	*mx, *my, *boost, *jump = 0, 0, false, false
	if d := hyp(gx-x, gy-y); d > 1 {
		q := math.Min(1, 4.6/math.Max(me.Stats.WalkSpeed, 1)) // silent: < 5 m/s
		*mx, *my = (gx-x)/d*q, (gy-y)/d*q
	}
	return true
}
