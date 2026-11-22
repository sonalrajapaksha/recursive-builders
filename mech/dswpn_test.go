package mech

import "testing"

func TestDroneLightGate(t *testing.T) {
	me := &Self{HP: 1400, MaxHP: 1400, Energy: 100, Weapons: []*WeaponState{{Kind: "gun"}, {Kind: "lightning"}}}
	b := &Brain{P: DefaultParams(), tracks: map[int]*Track{}, now: 50}
	if b.droneLightOK(me) {
		t.Fatal("must be off in DefaultParams")
	}
	b.P = squadParams(DefaultParams())
	if !b.droneLightOK(me) {
		t.Fatal("should close in with lightning, healthy, no mechs")
	}
	if r := b.prefRange(me, &Track{MechSeen: MechSeen{Kind: "npc"}}); r != b.P.DroneLightR {
		t.Fatalf("npc pref range %v", r)
	}
	b.tracks[3] = &Track{Seen: 49.5, Dist: 100}
	if b.droneLightOK(me) {
		t.Fatal("mech within quiet radius must close the gate")
	}
	b.tracks[3].Seen = 45
	low := *me
	low.HP = 900
	noE := *me
	noE.Energy = 20
	noL := *me
	noL.Weapons = []*WeaponState{{Kind: "gun"}, {Kind: "laser"}}
	if !b.droneLightOK(me) || b.droneLightOK(&low) || b.droneLightOK(&noE) || b.droneLightOK(&noL) {
		t.Fatal("gate must reopen after quiet and close on low hp/energy/no lightning")
	}
	if r := b.prefRange(&noL, &Track{MechSeen: MechSeen{Kind: "npc"}}); r != 58 {
		t.Fatalf("fallback npc range %v", r)
	}
}
