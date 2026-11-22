package mech

import "testing"

func TestDroneGhostGate(t *testing.T) {
	w, err := LoadWorld("../arena")
	if err != nil {
		t.Skip("no arena:", err)
	}
	if DefaultParams().DroneGhost {
		t.Fatal("must be off in DefaultParams")
	}
	b := &Brain{W: w, P: squadParams(DefaultParams())}
	b.Cfg.Vision.Range, b.Cfg.Vision.FovDeg, b.Cfg.Vision.NearRange = 200, 120, 45
	b.Cfg.Npc.Height = 3.5
	if !b.P.DroneGhost {
		t.Fatal("tune.json should turn it on")
	}
	// find an open spot with clear sight 30 m east
	var me Self
	var n *Track
	for x := -300.0; x < 300 && n == nil; x += 7 {
		for y := -300.0; y < 300 && n == nil; y += 7 {
			g := w.GroundAt(x, y)
			eye := Vec3{x, y, g + 8}
			c := Vec3{x + 30, y, w.GroundAt(x+30, y) + 1.75}
			if w.Free(x, y) && w.Clear(eye, c) {
				me = Self{Pos: Vec3{x, y, g}, Aim: [2]float64{3.14, 0}}
				n = &Track{MechSeen: MechSeen{Kind: "npc", Pos: Vec3{x + 30, y, c[2] - 1.75}}}
			}
		}
	}
	if n == nil {
		t.Skip("no open spot")
	}
	eye := Vec3{me.Pos[0], me.Pos[1], me.Pos[2] + 8}
	n.Seen = 10
	if b.npcGone(n, &me, eye, 10) {
		t.Fatal("listed this tick: not gone")
	}
	if !b.npcGone(n, &me, eye, 10.1) {
		t.Fatal("vanished inside proximity range with clear sight: gone")
	}
	n.Pos[0] += 70 // 100 m away, behind our aim (aim west, drone east)
	if b.npcGone(n, &me, eye, 10.1) {
		t.Fatal("out of fov and proximity: unknown, keep")
	}
	me.Aim[0] = 0
	if b.npcGone(n, &me, eye, 30) {
		t.Fatal("stale and far: keep")
	}
}
