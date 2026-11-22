package bot

import (
	"math"

	"apexbot/internal/proto"
)

func (b *Bot) endGhostActive(zi zoneInfo) bool {
	r := b.o.Zone.NextRadius
	return b.P.EndGhost && b.P.PracticeAware && !b.ffa &&
		(b.st.name == "squad" || b.st.name == "late") &&
		r > 0 && r <= 140 && !zi.urgent && !zi.critical
}

// endGhostStep walks to a sheltered part of the next circle and holds there.
func (b *Bot) endGhostStep(act *proto.Action, zi zoneInfo) bool {
	if !b.endGhostActive(zi) {
		b.endGhostCell = -1
		b.endGhostRetry = 0
		return false
	}
	if !b.onGroundLevel() {
		return false
	}
	z := &b.o.Zone
	key := [3]float64{z.NextCenter[0], z.NextCenter[1], z.NextRadius}
	if b.endGhostZone != key {
		b.endGhostZone = key
		b.endGhostCell = -1
		b.endGhostRetry = 0
	}
	if b.endGhostCell >= 0 && (!b.sameComp(b.endGhostCell) ||
		!b.Nav.Walkable(b.endGhostCell, b.radius+0.4, b.height)) {
		b.endGhostCell = -1
	}
	if b.endGhostCell < 0 && b.t >= b.endGhostRetry {
		b.endGhostRetry = b.t + 3
		b.endGhostCell = b.chooseHide(zi)
	}
	if b.endGhostCell < 0 {
		return false
	}

	gx, gy := b.Nav.Pos(b.endGhostCell)
	dx, dy, d, ok := b.navDir(gx, gy)
	if !ok {
		b.endGhostCell = -1
		b.endGhostRetry = b.t + 3
		return false
	}
	b.roof.state = roofNone
	b.mode = "endghost"
	rq := steerReq{threats: b.gatherIncoming(), hold: d <= 1.5}
	if !rq.hold {
		rq.wantX, rq.wantY, rq.wantW = dx, dy, 2
	}
	b.steer(act, rq)
	if tr := b.endGhostThreat(); tr != nil {
		b.targetID = tr.ID
		b.engage(act, b.targetOf(tr), true, true, tr.HP, true)
	} else {
		b.targetID = -1
		if b.t-b.lastWeaponDT < 1.5 {
			act.Aim, act.HasAim = [2]float64{b.lastDmgBear, 0}, true
		} else {
			b.idleAim(act, math.Atan2(dy, dx), !rq.hold)
		}
	}
	b.modeLabel = b.st.name + ":" + b.mode
	act.Label = b.modeLabel
	return true
}

func (b *Bot) endGhostThreat() *Track {
	var best *Track
	bestD := math.Inf(1)
	for _, tr := range b.tracks {
		if !tr.Listed || !tr.LOS {
			continue
		}
		d := dist2(b.pos, tr.Pos)
		recentHit := b.t-tr.HurtMeT < 3
		if !recentHit && (tr.NPC || d > 55) {
			continue
		}
		if d < bestD || (d == bestD && tr.ID < best.ID) {
			best, bestD = tr, d
		}
	}
	return best
}
