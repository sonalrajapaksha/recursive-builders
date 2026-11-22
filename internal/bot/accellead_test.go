package bot

import (
	"math"
	"os"
	"path/filepath"
	"testing"

	"apexbot/internal/proto"
	"apexbot/internal/world"
)

func TestAccelLeadGate(t *testing.T) {
	h := &proto.Hello{}
	b := Bot{P: DefaultParams(), C: &h.Config}
	tr := &Track{Listed: true, WasListed: true}
	tr.updateAccel([3]float64{0, 5, 0}, 0.1)
	if b.targetOf(tr).gunAccel != [2]float64{} {
		t.Fatal("default parameters applied acceleration lead")
	}
	b.P.AccelLead = true
	if got := b.targetOf(tr).gunAccel; got[0] != 0 || got[1] <= 0 {
		t.Fatalf("expected acceleration down Y, got %v", got)
	}
	tr.updateAccel([3]float64{0, 13, 0}, 0.4)
	if b.targetOf(tr).gunAccel != [2]float64{} {
		t.Fatal("used acceleration across a gap in observations")
	}
}

func TestAccelCorrectionCap(t *testing.T) {
	a := [2]float64{30, -50}
	x, y := accelCorrection(a, 0.1)
	if math.Abs(x-0.15) > 1e-9 || math.Abs(y+0.25) > 1e-9 {
		t.Fatalf("unexpected short-flight correction (%v, %v)", x, y)
	}
	x, y = accelCorrection(a, 1)
	if math.Abs(hyp(x, y)-2.5) > 1e-9 {
		t.Fatalf("long-flight correction missed the 2.5 m cap (%v, %v)", x, y)
	}
}

func TestGunLineFallbacks(t *testing.T) {
	dir := t.TempDir()
	mapDir := filepath.Join(dir, "v2")
	if err := os.Mkdir(mapDir, 0o755); err != nil {
		t.Fatal(err)
	}
	const geometry = `{
		"bounds":{"minX":-10,"maxX":50,"minY":-10,"maxY":20},
		"terrain":{"minX":-10,"minY":-10,"step":60,"nx":2,"ny":2},
		"prisms":[
			{"base":0,"top":12,"ring":[20,0.5,22,0.5,22,2,20,2]},
			{"base":0,"top":7,"ring":[26,9,28,9,28,11,26,11]}
		]
	}`
	if err := os.WriteFile(filepath.Join(mapDir, "world.json"), []byte(geometry), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(mapDir, "terrain.i16"), make([]byte, 8), 0o600); err != nil {
		t.Fatal(err)
	}
	w, err := world.Load(dir)
	if err != nil {
		t.Fatal(err)
	}
	h := &proto.Hello{}
	b := Bot{P: DefaultParams(), C: &h.Config, W: w, o: &proto.Obs{}, muzzleH: 7}
	tg := aimTarget{pos: [3]float64{40, 0, 0}, radius: 2.5, centerZ: 4.5, mech: true, gunAccel: [2]float64{0, 60}}
	if s := b.solveDirectLat(tg, 100, b.muzzleH, fireLatency); s.clear {
		t.Fatal("fixture should obstruct the acceleration-corrected line")
	}
	if s := b.solveGun(tg, 100, fireLatency); !s.clear || s.point[1] != 0 {
		t.Fatalf("gun did not fall back to the velocity-only line: %+v", s)
	}
	if s := b.solveDirectLat(tg, 0, b.muzzleH, fireLatency); !s.clear || s.point[1] != 0 {
		t.Fatalf("hitscan used the gun acceleration correction: %+v", s)
	}

	b.pos[1], tg.pos[1], tg.gunAccel = 10, 10, [2]float64{}
	b.slots[0] = slot{ok: true, kind: "gun", ammo: 1}
	act := proto.NewAction(1)
	b.engage(&act, tg, true, true, 1400, true)
	if !act.HasAim || act.Aim[1] <= 0 {
		t.Fatalf("gun did not aim above the wall at head height: %v", act.Aim)
	}
}
