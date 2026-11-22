package mech

import "testing"

func TestFarmReachGate(t *testing.T) {
	b := &Brain{P: squadParams(DefaultParams()), tracks: map[int]*Track{}, now: 100}
	base := b.P.LootRadius
	b.P.FarmReach = 0
	if b.farmReach(1) != base {
		t.Fatal("must be a no-op without FarmReach")
	}
	b.P = squadParams(DefaultParams())
	if b.P.FarmReach <= base || b.farmReach(1) != b.P.FarmReach {
		t.Fatalf("quiet+healthy should extend reach: %v", b.farmReach(1))
	}
	if b.farmReach(0.6) != base {
		t.Fatal("low hp must shrink reach")
	}
	b.tracks[2] = &Track{Seen: 98, Dist: 100}
	if b.farmReach(1) != base {
		t.Fatal("recent mech within quiet radius must shrink reach")
	}
	b.tracks[2].Dist = 150
	if b.farmReach(1) != b.P.FarmReach {
		t.Fatal("far mech must not shrink reach")
	}
}
