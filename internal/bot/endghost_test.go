package bot

import (
	"testing"

	"apexbot/internal/proto"
)

func TestEndGhostGate(t *testing.T) {
	b := Bot{P: DefaultParams(), o: &proto.Obs{}, st: stance{name: "squad"}}
	b.o.Zone.NextRadius = 140
	b.P.EndGhost = false
	if b.endGhostActive(zoneInfo{}) {
		t.Fatal("disabled EndGhost gate activated")
	}
	b.P.EndGhost = true
	if !b.endGhostActive(zoneInfo{}) || b.endGhostActive(zoneInfo{urgent: true}) {
		t.Fatal("EndGhost must activate at 140 m and yield to urgent rotation")
	}
	b.o.Zone.NextRadius = 141
	if b.endGhostActive(zoneInfo{}) {
		t.Fatal("EndGhost activated outside its radius threshold")
	}
	b.o.Zone.NextRadius = 100
	b.st.name = "late"
	if !b.endGhostActive(zoneInfo{}) {
		t.Fatal("EndGhost rejected the late practice stance")
	}
	b.ffa = true
	if b.endGhostActive(zoneInfo{}) {
		t.Fatal("EndGhost activated in FFA")
	}
}

func TestEndGhostThreat(t *testing.T) {
	far := &Track{ID: 1, Listed: true, LOS: true, Pos: [3]float64{100}, HurtMeT: 0}
	close := &Track{ID: 2, Listed: true, LOS: true, Pos: [3]float64{50}, HurtMeT: 0}
	b := Bot{t: 10, tracks: map[int]*Track{1: far}}
	if b.endGhostThreat() != nil {
		t.Fatal("distant unprovoked mech selected")
	}
	far.HurtMeT = 9
	if b.endGhostThreat() != far {
		t.Fatal("recent visible attacker was ignored")
	}
	b.tracks[2] = close
	if b.endGhostThreat() != close {
		t.Fatal("closer eligible mech was ignored")
	}
}
