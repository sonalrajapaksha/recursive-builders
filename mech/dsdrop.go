package mech

// Supply-drop capture gate (Params.DropGate, squad profile only via tune.json).
//
// Base (squad, non-econ chooseLoot): a drop is a loot target whenever it is
// reachable before LandsIn+DropWin and nothing is "danger" (an Engage-flagged
// mech, i.e. <60 m, closing, aimed, weak or hit us). A mech at 60-110 m that is
// not closing/aiming does not stop us walking into an open 8 m ring and
// standing there for 4 s, and the base walks on to 2.5 m of the centre
// (steps are audible within 40 m; standing still is silent).
//
// dropQuiet: while we are still away from the ring (farther than
// radius+DropX from its centre) the drop is only considered when no mech was
// seen within DropQuiet of us in the last DropQuietS seconds. Once we are at
// the ring we keep it unless a mech was seen within radius+DropX of the drop
// centre in that window: then the drop is dropped and base logic (fight /
// cover / loot) takes over. No timing change: the base already arrives before
// LandsIn=0 (it leaves as soon as dist/walk < LandsIn+DropWin) and we do not
// add any zone-centre walking.
func (b *Brain) dropQuiet(me *Self, d *Drop) bool {
	if !b.P.DropGate {
		return true
	}
	ring := d.Radius + b.P.DropX
	atRing := hyp(d.Pos[0]-me.Pos[0], d.Pos[1]-me.Pos[1]) < ring
	for _, t := range b.tracks {
		if b.now-t.Seen >= b.P.DropQuietS {
			continue
		}
		if atRing {
			if hyp(t.Pos[0]-d.Pos[0], t.Pos[1]-d.Pos[1]) < ring {
				return false
			}
		} else if t.Dist < b.P.DropQuiet {
			return false
		}
	}
	return true
}

// dropHold: inside the ring (1.5 m margin) stop instead of walking on to the
// centre, so we are still and silent; the idle aim sweep in step() keeps
// scanning (+0.35 rad per decision) while we hold.
func (b *Brain) dropHold(o *Obs, id int) bool {
	if !b.P.DropGate {
		return false
	}
	for i := range o.Drops {
		d := &o.Drops[i]
		if d.ID == id {
			return hyp(d.Pos[0]-o.Self.Pos[0], d.Pos[1]-o.Self.Pos[1]) < d.Radius-1.5
		}
	}
	return false
}
