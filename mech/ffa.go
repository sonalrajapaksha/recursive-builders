package mech

// FFA-only behaviour, switched on by ffaProven. Ported from waiprotein/mech-royale-bot
// (https://github.com/waiprotein/mech-royale-bot, commit 42c594f, mech/brain.go: holdingOut, holdHome,
// duelOdds, exchange), MIT licence, Copyright (c) 2026 waihu (modifications), see
// LICENSE-waiprotein. Adapted to this codebase (no homelos force flag).

import "math"

// ffaProven reports a proven free-for-all: the practice detector has latched (a death we did not cause, held
// for 5 ticks), at least ffaStrictN deaths we did not cause, and squad/opening params are not on.
func (b *Brain) ffaProven() bool {
	return b.notPractice && b.maxUnexpl >= ffaStrictN && !b.pracOn && !b.openOn
}

// holdingOut reports whether a ghost should stay away from the final circle's centre for now.
func (b *Brain) holdingOut(z *Zone, alive int) bool {
	return b.P.Ghost && b.P.HoldOut > 0 && b.now < b.P.HoldOut && z.NextRadius <= 30 && alive > 2
}

// holdHome picks a hidden spot inside the current circle, between HoldMin and HoldMin+25 m from the final
// centre. The normal zone deadline logic still pulls the bot in before the circle reaches it.
func (b *Brain) holdHome(o *Obs) (float64, float64, bool) {
	z := &o.Zone
	c := b.curZone(z)
	minD := b.P.HoldMin
	if minD <= 0 {
		minD = 40
	}
	valid := func(px, py float64) bool {
		d := hyp(px-z.NextCenter[0], py-z.NextCenter[1])
		return d >= minD*0.8 && hyp(px-c.X, py-c.Y) <= c.R-12
	}
	if !b.homeSet || !valid(b.homeXY[0], b.homeXY[1]) || b.now-b.homeAt > 12 {
		b.homeAt = b.now
		best, bestC := [2]float64{}, math.Inf(1)
		for k := 0; k < 48; k++ {
			a := b.rng.Float64() * 2 * math.Pi
			r := minD + b.rng.Float64()*25
			px, py := z.NextCenter[0]+math.Cos(a)*r, z.NextCenter[1]+math.Sin(a)*r
			if !valid(px, py) || !b.W.InBounds(px, py) || !b.W.Reachable(px, py) {
				continue
			}
			if cst := b.homeCost(o, px, py) + 0.5*r; cst < bestC {
				best, bestC = [2]float64{px, py}, cst
			}
		}
		if math.IsInf(bestC, 1) {
			// No valid spot (circle too small): go to the final centre as before.
			return z.NextCenter[0], z.NextCenter[1], true
		}
		if !b.homeSet || !valid(b.homeXY[0], b.homeXY[1]) || bestC < b.homeCost(o, b.homeXY[0], b.homeXY[1])+0.5*hyp(b.homeXY[0]-z.NextCenter[0], b.homeXY[1]-z.NextCenter[1])-15 {
			b.homeXY, b.homeSet = best, true
		}
	}
	return b.homeXY[0], b.homeXY[1], b.homeSet
}

// exchange records who opened the current exchange of fire with one mech (an exchange ends after 6 s
// without hits either way). duelOdds uses it to pick the first-shooter side of the duel model.
type exchange struct {
	last    float64
	meFirst bool
}

func (b *Brain) noteExchange(id int, byMe bool, now float64) {
	if b.exch == nil {
		b.exch = map[int]*exchange{}
	}
	ex := b.exch[id]
	if ex == nil {
		ex = &exchange{last: -100}
		b.exch[id] = ex
	}
	if now-ex.last > 6 {
		ex.meFirst = byMe
	}
	ex.last = now
}

// duelOdds is waiprotein's logistic duel model (fitted on 187 decisive engagements in recorded top-16
// showdowns). For the side that shot first: z = 0.94 + 4.0*ln(HP_shooter/HP_target) + 0.74*[shooter holds
// laser] - 1.19*[target holds laser] + 0.68*[target's back turned]. If t shot first, our chance is
// 1 - P(t wins as shooter). Used only by DuelFlee.
func (b *Brain) duelOdds(me *Self, t *Track) float64 {
	sig := func(z float64) float64 { return 1 / (1 + math.Exp(-z)) }
	_, ml := hasWeapon(me.Weapons, "laser")
	meLaser, themLaser := ml != nil, holds(t.Weapons, "laser")
	ind := func(v bool) float64 {
		if v {
			return 1
		}
		return 0
	}
	hpMe, hpThem := math.Max(me.HP, 1), math.Max(t.HP, 1)
	if ex := b.exch[t.ID]; ex != nil && b.now-ex.last < 6 && !ex.meFirst {
		toT := math.Atan2(t.Pos[1]-me.Pos[1], t.Pos[0]-me.Pos[0])
		meBack := math.Abs(angDiff(me.Aim[0], toT)) > math.Pi/2
		z := 0.94 + 4.0*math.Log(hpThem/hpMe) + 0.74*ind(themLaser) - 1.19*ind(meLaser) + 0.68*ind(meBack)
		return 1 - sig(z)
	}
	toMe := math.Atan2(me.Pos[1]-t.Pos[1], me.Pos[0]-t.Pos[0])
	themBack := math.Abs(angDiff(t.Aim[0], toMe)) > math.Pi/2
	return sig(0.94 + 4.0*math.Log(hpMe/hpThem) + 0.74*ind(meLaser) - 1.19*ind(themLaser) + 0.68*ind(themBack))
}
