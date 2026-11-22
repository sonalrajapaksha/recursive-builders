package mech

import "testing"

func TestDroneHystGate(t *testing.T) {
	b := &Brain{P: DefaultParams()}
	n := &Track{MechSeen: MechSeen{Kind: "npc"}}
	if b.droneGateDist(60, 0.5) != 60 {
		t.Fatal("must be off in DefaultParams")
	}
	b.P = squadParams(DefaultParams())
	if b.droneLaserOK(n, nil, 1, b.droneGateDist(60, 0)) {
		t.Fatal("a new charge still needs DroneRange")
	}
	if !b.droneLaserOK(n, nil, 1, b.droneGateDist(60, 0.4)) {
		t.Fatal("a charge in progress may finish just outside DroneRange")
	}
	if b.droneLaserOK(n, nil, 1, b.droneGateDist(70, 0.4)) || b.droneLaserOK(n, nil, 0.5, b.droneGateDist(60, 0.4)) {
		t.Fatal("hysteresis is bounded and leaves the HP gate alone")
	}
}
