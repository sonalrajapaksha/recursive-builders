package bot

import (
	"testing"

	"apexbot/internal/proto"
)

func TestCoverHealGate(t *testing.T) {
	b := Bot{P: DefaultParams(), hp: 590, maxHP: 1000}
	b.P.CoverHeal = false
	if b.coverHealActive(zoneInfo{}, 81) {
		t.Fatal("disabled CoverHeal gate activated")
	}
	b.P.CoverHeal = true
	if b.coverHealActive(zoneInfo{}, 80) || b.coverHealActive(zoneInfo{urgent: true}, 81) {
		t.Fatal("CoverHeal should yield to nearby mechs and urgent rotation")
	}
	if !b.coverHealActive(zoneInfo{}, 81) {
		t.Fatal("CoverHeal did not activate below 60% HP")
	}
	b.hp = 700
	if b.coverHealActive(zoneInfo{}, 50) || !b.coverHealActive(zoneInfo{}, 100) {
		t.Fatal("CoverHeal should pause and resume until healed")
	}
	b.hp = 900
	if b.coverHealActive(zoneInfo{}, 100) {
		t.Fatal("CoverHeal persisted at 90% HP")
	}
	b.hp = 600
	if b.coverHealActive(zoneInfo{}, 100) {
		t.Fatal("CoverHeal reactivated at 60% HP")
	}
}

func TestCoverHealDropSafety(t *testing.T) {
	b := Bot{t: 10, o: &proto.Obs{}, tracks: map[int]*Track{}}
	b.o.Zone.Radius = 200
	b.o.Zone.NextRadius = 60
	b.o.Zone.NextCenter = [2]float64{40, 0}
	b.o.Zone.ShrinkStart = 30
	b.o.Drops = []proto.DropObs{
		{ID: 1, Pos: [3]float64{-25, 0, 0}},
		{ID: 2, Pos: [3]float64{35, 0, 0}},
	}
	if got := b.coverHealDrop(); got == nil || got.ID != 2 {
		t.Fatalf("expected the drop inside the next circle, got %v", got)
	}
	b.tracks[3] = &Track{Pos: [3]float64{85, 0, 0}, LastSeen: b.t}
	if b.coverHealDrop() != nil {
		t.Fatal("drop with a mech 50 m away was considered safe")
	}
}
