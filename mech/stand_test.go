package mech

import "testing"

func TestDroneStandGate(t *testing.T) {
	b := &Brain{P: DefaultParams(), tracks: map[int]*Track{}}
	me := &Self{HP: 1400, MaxHP: 1400}
	n := &Track{MechSeen: MechSeen{Kind: "npc"}}
	las := &WeaponState{Kind: "laser"}
	if _, ok := b.droneStand(me, n, las); ok {
		t.Fatal("must be off in DefaultParams")
	}
	b.P = squadParams(DefaultParams())
	if r, ok := b.droneStand(me, n, las); !ok || r != 51 {
		t.Fatal("ready laser, healthy, quiet: stand at 51 m", r, ok)
	}
	if _, ok := b.droneStand(me, n, nil); ok {
		t.Fatal("no laser: base 58 m")
	}
	las.Cooldown = 1
	if _, ok := b.droneStand(me, n, las); ok {
		t.Fatal("laser cooling down: base 58 m")
	}
	las.Cooldown = 0
	b.tracks[3] = &Track{Dist: 90}
	if _, ok := b.droneStand(me, n, las); ok {
		t.Fatal("mech within quiet radius: base 58 m")
	}
	delete(b.tracks, 3)
	me.HP = 700
	if _, ok := b.droneStand(me, n, las); ok {
		t.Fatal("hurt: base 58 m")
	}
}
