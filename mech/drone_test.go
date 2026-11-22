package mech

import "testing"

func TestDroneLaserGate(t *testing.T) {
	b := &Brain{P: DefaultParams()}
	n := &Track{MechSeen: MechSeen{Kind: "npc"}}
	if b.droneLaserOK(n, nil, 1, 40) {
		t.Fatal("must be off in DefaultParams")
	}
	b.P = squadParams(DefaultParams())
	if !b.droneLaserOK(n, nil, 1, 40) {
		t.Fatal("should fire at a near drone with no mechs")
	}
	m := &Track{Dist: 70}
	if b.droneLaserOK(n, []*Track{m}, 1, 40) || b.droneLaserOK(n, nil, 0.5, 40) || b.droneLaserOK(n, nil, 1, 90) {
		t.Fatal("gate must close with a mech near, low hp or far drone")
	}
}
