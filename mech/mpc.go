package mech

import (
	"math"
	"time"
)

// Sampling-based predictive combat controller (small MPC / rollout search).
//
// Each decision it samples ~40 candidate (direction x speed x boost) moves,
// rolls each forward over a short horizon with a simple model of enemy guns,
// charging lasers, bullets already in flight, our own fire window, cover,
// the zone and obstacles, and returns the best-scoring one. Aim/fire logic is
// untouched. It never prints; it returns false (caller keeps the heuristic
// movement) when there is no threat, when disabled, or when its time guard hits.

const (
	mpcBudget  = 12 * time.Millisecond
	mpcSteps   = 8
	mpcDt      = 0.1
	mpcDealW   = 0.55
	mpcHystSim = 5.0
)

type mpcState struct {
	prevAng   float64
	prevSpeed int // 0 stop, 1 walk, 2 boost
	prevAt    float64
	hasPrev   bool
	chargeAt  map[int]float64 // enemy id -> time we first saw its laser charging
	// stats (for local measurement)
	Calls, Aborts int
	TotNs, MaxNs  int64
}

type mpcCand struct {
	dx, dy float64
	speed  int
}

type mpcEnemy struct {
	m      *MechSeen
	dist   float64
	gun    bool
	laser  bool
	light  bool
	npc    bool
	tFire  float64 // laser: seconds until it fires (<=0 means not charging)
	aimYaw float64
	dmgMul float64 // size scaling from cubes
}

// mpcThreat reports whether the controller should be active this tick.
// lite: only imminent incoming laser / projectile.
func (b *Brain) mpcThreat(o *Obs, lite bool) bool {
	me := &o.Self
	x, y := me.Pos[0], me.Pos[1]
	cz := me.Pos[2] + me.Stats.Height*0.56
	for i := range o.Mechs {
		m := &o.Mechs[i]
		if m.Charging {
			toMe := math.Atan2(y-m.Pos[1], x-m.Pos[0])
			d := hyp(x-m.Pos[0], y-m.Pos[1])
			if math.Abs(angDiff(m.Aim[0], toMe)) < 0.35 && d < 300 {
				return true
			}
		}
	}
	for i := range o.Projectiles {
		p := &o.Projectiles[i]
		if p.Kind == "mortar" {
			continue
		}
		v2 := p.Vel[0]*p.Vel[0] + p.Vel[1]*p.Vel[1] + p.Vel[2]*p.Vel[2]
		if v2 < 1 {
			continue
		}
		tc := ((x-p.Pos[0])*p.Vel[0] + (y-p.Pos[1])*p.Vel[1] + (cz-p.Pos[2])*p.Vel[2]) / v2
		if tc <= 0 || tc > 1.0 {
			continue
		}
		mx, my := p.Pos[0]+p.Vel[0]*tc-x, p.Pos[1]+p.Vel[1]*tc-y
		if hyp(mx, my) < me.Stats.Radius+6 {
			return true
		}
	}
	if lite {
		return false
	}
	for _, t := range b.tracks {
		if t.Seen == b.now && t.LOS && t.Dist < 170 && t.Kind == "mech" {
			return true
		}
	}
	return false
}

// mpcMove returns true and overrides (mx,my,boost) when it found a plan.
// baseX/baseY/baseBoost is the heuristic intent; foe is the selected target (may be nil).
func (b *Brain) mpcMove(o *Obs, foe *Track, mode string, mx, my *float64, boost *bool) bool {
	lite := b.P.MPC == 2
	if !b.mpcThreat(o, lite) {
		return false
	}
	t0 := time.Now()
	st := &b.mpc
	if st.chargeAt == nil {
		st.chargeAt = map[int]float64{}
	}
	me := &o.Self
	cfg := &b.Cfg
	now := o.T
	x0, y0 := me.Pos[0], me.Pos[1]
	rad := me.Stats.Radius
	hitR := rad + 1.2

	// ---- enemy list
	var enemies []mpcEnemy
	liveCharge := map[int]bool{}
	gunW, laserW, lightW := cfg.Weapons["gun"], cfg.Weapons["laser"], cfg.Weapons["lightning"]
	for i := range o.Mechs {
		m := &o.Mechs[i]
		d := hyp(m.Pos[0]-x0, m.Pos[1]-y0)
		if d > 300 {
			continue
		}
		e := mpcEnemy{m: m, dist: d, npc: m.Kind == "npc", aimYaw: m.Aim[0], dmgMul: 1}
		if e.npc {
			e.gun = d < 100
		} else {
			for _, w := range m.Weapons {
				switch w {
				case "gun":
					e.gun = d < gunW.Range
				case "laser":
					e.laser = true
				case "lightning":
					e.light = d < lightW.Range+8
				}
			}
			e.dmgMul = 1 + cfg.Cubes.DamagePerCube*math.Min(float64(m.Cubes), float64(cfg.Cubes.StatCap))
		}
		if m.Charging {
			liveCharge[m.ID] = true
			if _, ok := st.chargeAt[m.ID]; !ok {
				st.chargeAt[m.ID] = now
			}
			e.tFire = math.Max(0.08, laserW.Charge-(now-st.chargeAt[m.ID]))
		}
		enemies = append(enemies, e)
	}
	for id := range st.chargeAt {
		if !liveCharge[id] {
			delete(st.chargeAt, id)
		}
	}

	// ---- candidates
	var cands []mpcCand
	hasBoost := me.Energy > 20
	for k := 0; k < 16; k++ {
		a := float64(k) * math.Pi / 8
		c, s := math.Cos(a), math.Sin(a)
		cands = append(cands, mpcCand{c, s, 1})
		if hasBoost {
			cands = append(cands, mpcCand{c, s, 2})
		}
	}
	for k := 0; k < 8; k++ {
		a := (float64(k) + 0.5) * math.Pi / 4
		cands = append(cands, mpcCand{math.Cos(a), math.Sin(a), 1})
	}
	cands = append(cands, mpcCand{0, 0, 0})
	bl := hyp(*mx, *my)
	baseDX, baseDY := 0.0, 0.0
	if bl > 0.05 {
		baseDX, baseDY = *mx/bl, *my/bl
		cands = append(cands, mpcCand{baseDX, baseDY, 1})
		if hasBoost {
			cands = append(cands, mpcCand{baseDX, baseDY, 2})
		}
	}

	// intent weight
	wI := 10.0
	switch mode {
	case "zone":
		wI = 28
	case "fight", "cornered", "cover", "evade", "shy", "earlyhide", "flee", "dodge":
		wI = 10
	default:
		wI = 16
	}
	if lite {
		wI = 30
	}

	zone := b.curZone(&o.Zone)
	chargeMul := 1.0
	if laserWS := laserState(me); laserWS != nil && laserWS.Charge > 0 {
		chargeMul = cfg.Mech.ChargeMoveMult
		if chargeMul <= 0 {
			chargeMul = 0.5
		}
	}
	rearM := b.rearMult()
	arc := cfg.Mech.FrontArcDeg
	if arc <= 0 {
		arc = 180
	}
	myYaw := me.Aim[0]

	// our own weapons
	_, myGun := hasWeapon(me.Weapons, "gun")
	_, myLaser := hasWeapon(me.Weapons, "laser")
	_, myLight := hasWeapon(me.Weapons, "lightning")
	gunDPS, laserDPS, lightDPS := 0.0, 0.0, 0.0
	if myGun != nil && (myGun.Ammo > 0 || myGun.Reload < 0.6) {
		gunDPS = gunW.Damage / gunW.Cooldown * 0.6
	}
	if myLaser != nil && myLaser.Cooldown < 0.8 {
		laserDPS = laserW.Damage / (laserW.Charge + laserW.Cooldown) * 0.55
	}
	if myLight != nil && me.Energy > 12 {
		lightDPS = lightW.Damage / lightW.Cooldown * 0.5
	}
	var foeM *MechSeen
	if foe != nil {
		for i := range o.Mechs {
			if o.Mechs[i].ID == foe.ID && o.Mechs[i].Kind == foe.Kind {
				foeM = &o.Mechs[i]
			}
		}
	}

	bestS := math.Inf(-1)
	var best mpcCand
	aborted := false
	for ci := range cands {
		if ci&3 == 0 && time.Since(t0) > mpcBudget {
			aborted = true
			break
		}
		c := cands[ci]
		spd := 0.0
		switch c.speed {
		case 1:
			spd = me.Stats.WalkSpeed
		case 2:
			spd = me.Stats.BoostSpeed
		}
		spd *= chargeMul
		tvx, tvy := c.dx*spd, c.dy*spd
		px, py := x0, y0
		vx, vy := me.Vel[0], me.Vel[1]
		taken, dealt, zonePen, block := 0.0, 0.0, 0.0, 0.0
		blocked := false
		var tracePos [mpcSteps + 1][2]float64
		tracePos[0] = [2]float64{x0, y0}
		for s := 1; s <= mpcSteps; s++ {
			// velocity toward target velocity (accel-limited)
			ax, ay := tvx-vx, tvy-vy
			al := hyp(ax, ay)
			maxA := me.Stats.GroundAccel * mpcDt
			if maxA <= 0 {
				maxA = 5.85
			}
			if al > maxA {
				ax, ay = ax/al*maxA, ay/al*maxA
			}
			vx += ax
			vy += ay
			if !blocked {
				nx, ny := px+vx*mpcDt, py+vy*mpcDt
				if !b.W.Free(nx, ny) {
					blocked = true
					block += 12
				} else {
					px, py = nx, ny
				}
			}
			if blocked {
				block += 2
			}
			tracePos[s] = [2]float64{px, py}
		}
		if !blocked && (c.speed > 0) && !b.W.LineWalkable(x0, y0, px, py) {
			block += 25
		}

		for s := 1; s <= mpcSteps; s++ {
			tt := float64(s)*mpcDt + lat
			cx, cy := tracePos[s][0], tracePos[s][1]
			if hyp(cx-zone.X, cy-zone.Y) > zone.R {
				zonePen += o.Zone.Dps * mpcDt * 1.2
			}
			// incoming bullets in flight
			for i := range o.Projectiles {
				p := &o.Projectiles[i]
				if p.Kind == "mortar" {
					continue
				}
				bx, by := p.Pos[0]+p.Vel[0]*tt, p.Pos[1]+p.Vel[1]*tt
				if hyp(bx-cx, by-cy) < hitR+0.8 {
					dm := gunW.Damage
					if p.Kind == "npc" {
						dm = cfg.Npc.Damage
					}
					taken += dm * 0.7
				}
			}
			for ei := range enemies {
				e := &enemies[ei]
				m := e.m
				ex, ey := m.Pos[0]+m.Vel[0]*tt, m.Pos[1]+m.Vel[1]*tt
				dist := hyp(cx-ex, cy-ey)
				// facing: do we show our back to them
				rear := 1.0
				// rear: attacker is behind our aim
				if rearM > 1 {
					behind := math.Abs(angDiff(myYaw, math.Atan2(ey-cy, ex-cx))) > arc*math.Pi/360+0.1
					if behind {
						rear = rearM
					} else {
						rear = 1
					}
				}
				var los bool
				losDone := false
				getLOS := func() bool {
					if !losDone {
						losDone = true
						if dist > 300 {
							los = false
						} else {
							h := cfg.Mech.EyeHeight * b.scaleOf(m.Cubes)
							los = b.W.Clear(Vec3{ex, ey, m.Pos[2] + h}, Vec3{cx, cy, me.Pos[2] + me.Stats.Height*0.6})
						}
					}
					return los
				}
				if e.gun && !(m.Charging) {
					sp := gunW.Speed
					rng := gunW.Range
					dps := gunW.Damage / gunW.Cooldown * 0.6
					if e.npc {
						sp, rng, dps = cfg.Npc.ProjectileSpeed, 100, cfg.Npc.Damage/math.Max(cfg.Npc.Cooldown, 0.1)
					}
					if dist < rng && s%2 == 0 || (dist < rng && s == 1) {
						fl := dist / sp
						// where the enemy expects us: current position + current velocity (lead) or no lead
						lx, ly := x0+me.Vel[0]*(fl+lat), y0+me.Vel[1]*(fl+lat)
						missL := hyp(cx-lx, cy-ly)
						missN := hyp(cx-x0, cy-y0)
						sig := hitR + 0.8
						p := 0.5*math.Exp(-(missL*missL)/(sig*sig)) + 0.5*math.Exp(-(missN*missN)/(sig*sig))
						if p > 0.02 && getLOS() {
							w := 2.0 // each evaluated step covers two steps' worth (every other step)
							if s == 1 {
								w = 1
							}
							taken += dps * mpcDt * w * p * rear * e.dmgMul
						}
					}
				}
				if e.laser && e.tFire > 0 && math.Abs(e.tFire-tt) < mpcDt/2+1e-9 {
					// laser fires now along aim; enemy re-aims toward us at turn_rate
					bear := math.Atan2(cy-m.Pos[1], cx-m.Pos[0])
					maxTurn := me.Stats.TurnRate * e.tFire
					if maxTurn <= 0 {
						maxTurn = 4 * e.tFire
					}
					d := hyp(cx-m.Pos[0], cy-m.Pos[1])
					// aim if it just holds its current aim
					hold := math.Abs(angDiff(m.Aim[0], bear))
					// aim if it tracks (limited by turn rate) our predicted position
					track := math.Max(0, hold-maxTurn)
					perp := func(ang float64) float64 { return d * math.Sin(math.Min(ang, math.Pi/2)) }
					ph := math.Exp(-math.Pow(perp(hold)/(hitR+0.5), 2))
					pt := math.Exp(-math.Pow(perp(track)/(hitR+0.5), 2))
					p := 0.4*ph + 0.6*pt
					if p > 0.02 && getLOS() && d < laserW.Range {
						taken += laserW.Damage * p * rear * e.dmgMul
					}
				}
				if e.light && dist < lightW.Range+3 && s%2 == 0 {
					if getLOS() {
						taken += lightW.Damage / lightW.Cooldown * mpcDt * 2 * 0.5 * rear
					}
				}
			}
			// our own fire window against the selected target
			if !lite && foeM != nil && s%2 == 0 {
				fx, fy := foeM.Pos[0]+foeM.Vel[0]*tt, foeM.Pos[1]+foeM.Vel[1]*tt
				fd := hyp(fx-cx, fy-cy)
				dps := 0.0
				if fd < gunW.Range-10 {
					dps += gunDPS * (1 - 0.3*clamp(fd/gunW.Range, 0, 1))
				}
				if fd < b.P.LaserRange {
					dps += laserDPS
				}
				if fd < lightW.Range {
					dps += lightDPS
				}
				if dps > 0 {
					h := cfg.Mech.EyeHeight * b.scaleOf(foeM.Cubes)
					if b.W.Clear(Vec3{cx, cy, me.Pos[2] + me.Stats.MuzzleHeight}, Vec3{fx, fy, foeM.Pos[2] + h*0.6}) {
						dealt += dps * mpcDt * 2
					}
				}
			}
		}

		score := -taken + mpcDealW*dealt - zonePen - block
		// intent
		dot := c.dx*baseDX + c.dy*baseDY
		if bl > 0.05 {
			if c.speed == 0 {
				score += wI * 0.1
			} else {
				score += wI * 0.5 * dot
			}
		} else if c.speed == 0 {
			score += wI * 0.4
		} else {
			score -= wI * 0.05
		}
		if c.speed == 2 && !*boost {
			score -= 3
		}
		if c.speed == 2 && me.Energy < 40 {
			score -= 3
		}
		if !lite {
			// small cover preference: no enemy LOS at the end position
			ex0 := tracePos[mpcSteps]
			seenEnd := false
			for ei := range enemies {
				e := &enemies[ei]
				if e.npc || e.dist > 200 {
					continue
				}
				if b.W.Clear(b.eye(&Track{MechSeen: *e.m}), Vec3{ex0[0], ex0[1], me.Pos[2] + me.Stats.Height*0.6}) {
					seenEnd = true
					break
				}
			}
			if !seenEnd {
				score += 3
			}
		}
		// temporal smoothness
		if st.hasPrev && now-st.prevAt < 0.4 && c.speed == st.prevSpeed {
			if c.speed == 0 || math.Abs(angDiff(math.Atan2(c.dy, c.dx), st.prevAng)) < 0.35 {
				score += mpcHystSim
			}
		}
		if score > bestS {
			bestS, best = score, c
		}
	}

	dur := time.Since(t0).Nanoseconds()
	st.Calls++
	st.TotNs += dur
	if dur > st.MaxNs {
		st.MaxNs = dur
	}
	if aborted || math.IsInf(bestS, -1) {
		st.Aborts++
		return false
	}
	st.hasPrev, st.prevAt, st.prevSpeed = true, now, best.speed
	if best.speed != 0 {
		st.prevAng = math.Atan2(best.dy, best.dx)
	}
	if best.speed == 0 {
		*mx, *my, *boost = 0, 0, false
	} else {
		*mx, *my, *boost = best.dx, best.dy, best.speed == 2
	}
	return true
}

func laserState(me *Self) *WeaponState {
	_, l := hasWeapon(me.Weapons, "laser")
	return l
}
