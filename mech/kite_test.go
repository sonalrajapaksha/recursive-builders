package mech

import (
	"math"
	"testing"
)

func TestKiteDirTangential(t *testing.T) {
	// On the target radius: pure tangent, CCW for +1.
	dx, dy := kiteDir(100, 0, 0, 0, 100, 1)
	if math.Abs(dx) > 1e-9 || math.Abs(dy-1) > 1e-9 {
		t.Fatalf("ccw tangent got %v,%v", dx, dy)
	}
	// Outside the target radius: steer inward.
	dx, _ = kiteDir(120, 0, 0, 0, 100, -1)
	if dx >= 0 {
		t.Fatalf("expected inward component, got %v", dx)
	}
	if DefaultParams().Kite {
		t.Fatal("Kite must be off in DefaultParams")
	}
	if !squadParams(DefaultParams()).Kite {
		t.Fatal("Kite should be on in squad profile via tune.json")
	}
}
