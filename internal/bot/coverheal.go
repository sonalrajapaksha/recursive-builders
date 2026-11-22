package bot

import "apexbot/internal/proto"

func (b *Bot) coverHealActive(zi zoneInfo, nearest float64) bool {
	if !b.P.CoverHeal {
		return false
	}
	fraction := b.hp / b.maxHP
	if fraction >= b.P.CoverHealClear {
		b.coverHealOn = false
	}
	if zi.urgent || zi.critical || nearest <= 80 {
		return false
	}
	if fraction < b.P.CoverHealStart {
		b.coverHealOn = true
	}
	return b.coverHealOn
}

func (b *Bot) coverHealStep(act *proto.Action, zi zoneInfo, ths []threat, inc []incoming) bool {
	nearest := b.nearestEye(ths)
	if !b.coverHealActive(zi, nearest) || !b.onGroundLevel() {
		b.coverHealCell, b.coverHealRetry = -1, 0
		return false
	}
	if dr := b.coverHealDrop(); dr != nil {
		if b.coverHealMove(act, "heal-drop", dr.Pos[0], dr.Pos[1], 3, inc) {
			return true
		}
		b.banUntil[dr.ID] = b.t + 3
	}

	// Leave enough time for regeneration and a short walk to the shelter.
	seconds := 5 + (b.P.CoverHealClear*b.maxHP-b.hp)/45
	accept := func(k int, hasEyes bool) bool {
		x, y := b.Nav.Pos(k)
		return b.inFutureZone(x, y, seconds+6, 4) && (hasEyes || b.coverHealSheltered(k))
	}
	here := b.Nav.Index(b.pos[0], b.pos[1])
	if b.inFutureZone(b.pos[0], b.pos[1], seconds, 4) &&
		(nearest < 1e9 || b.coverHealSheltered(here)) && b.hiddenHere(ths) {
		b.coverHealCell = -1
		return b.coverHealMove(act, "heal-hold", b.pos[0], b.pos[1], 1, inc)
	}
	if k := b.coverHealCell; k >= 0 &&
		(!b.Nav.Walkable(k, b.radius+0.6, b.height) || !accept(k, nearest < 1e9) || !b.cellHidden(k, ths)) {
		b.coverHealCell = -1
	}
	if b.coverHealCell < 0 && b.t >= b.coverHealRetry {
		b.coverHealRetry = b.t + 1
		b.coverHealCell = b.findCoverWhere(ths, 60, accept)
	}
	if b.coverHealCell >= 0 {
		gx, gy := b.Nav.Pos(b.coverHealCell)
		if b.coverHealMove(act, "heal-cover", gx, gy, 1, inc) {
			return true
		}
		b.coverHealCell, b.coverHealRetry = -1, b.t+1
	}
	return false
}

// Without a known observer, use the nearest enclosed pocket on the exposure map.
func (b *Bot) coverHealSheltered(k int) bool {
	return b.Nav.Exposure().At(k) <= 0.40
}

func (b *Bot) coverHealDrop() *proto.DropObs {
	z := &b.o.Zone
	var best *proto.DropObs
	bestD := 45.0
	for i := range b.o.Drops {
		dr := &b.o.Drops[i]
		d := dist2(b.pos, dr.Pos)
		if d >= bestD || dr.LandsIn > 8 || b.banUntil[dr.ID] > b.t ||
			hyp(dr.Pos[0]-z.NextCenter[0], dr.Pos[1]-z.NextCenter[1]) > z.NextRadius-4 ||
			!b.inFutureZone(dr.Pos[0], dr.Pos[1], 10, 4) ||
			b.enemyNear(dr.Pos, 55) || !b.reachable(dr.Pos[0], dr.Pos[1]) {
			continue
		}
		best, bestD = dr, d
	}
	return best
}

func (b *Bot) coverHealMove(act *proto.Action, mode string, gx, gy, stop float64, inc []incoming) bool {
	dx, dy, d, ok := b.navDir(gx, gy)
	if !ok {
		return false
	}
	rq := steerReq{threats: inc, hold: d <= stop}
	if !rq.hold {
		rq.wantX, rq.wantY, rq.wantW = dx, dy, 2.4
	}
	b.steer(act, rq)
	b.idleAim(act, 0, false)
	b.roof.state = roofNone
	b.targetID = -1
	b.mode = mode
	b.modeLabel = b.st.name + ":" + mode
	act.Label = b.modeLabel
	return true
}
