package mech

import "testing"

func TestDropGate(t *testing.T) {
	me := &Self{Pos: Vec3{0, 0, 0}}
	far := &Drop{ID: 20000, Pos: Vec3{200, 0, 0}, Radius: 8}
	b := &Brain{P: DefaultParams(), tracks: map[int]*Track{}, now: 100}
	b.tracks[4] = &Track{MechSeen: MechSeen{Pos: Vec3{-90, 0, 0}}, Seen: 99, Dist: 90}
	if !b.dropQuiet(me, far) {
		t.Fatal("must be a no-op in DefaultParams")
	}
	b.P = squadParams(DefaultParams())
	if b.dropQuiet(me, far) {
		t.Fatal("mech within DropQuiet of us must block the approach")
	}
	b.tracks[4].Seen = 90
	if !b.dropQuiet(me, far) {
		t.Fatal("stale sighting must not block")
	}
	near := &Drop{ID: 20001, Pos: Vec3{5, 0, 0}, Radius: 8}
	b.tracks[4].Seen = 99
	if !b.dropQuiet(me, near) {
		t.Fatal("at the ring only mechs near the ring abort")
	}
	b.tracks[4].MechSeen.Pos = Vec3{25, 0, 0}
	if b.dropQuiet(me, near) {
		t.Fatal("mech inside ring+DropX must abort")
	}
	o := &Obs{Self: *me, Drops: []Drop{*near}}
	if !b.dropHold(o, near.ID) || b.dropHold(o, far.ID) {
		t.Fatal("hold only inside the ring")
	}
}
