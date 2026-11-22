package mech

import (
	"os"
	"sort"
	"testing"
	"time"
)

// go test ./mech -run Roof -v : loads ../arena, prints the best fortress roofs.
func TestRoofMap(t *testing.T) {
	w, err := LoadWorld("../arena")
	if err != nil {
		t.Skip("no arena:", err)
	}
	t0 := time.Now()
	m := w.Roofs()
	el := time.Since(t0)
	var ok []int
	for i := range m.Regions {
		if m.Regions[i].Usable() {
			ok = append(ok, i)
		}
	}
	onFoot := 0
	for _, i := range ok {
		if m.Regions[i].OnFoot {
			onFoot++
		}
	}
	t.Logf("roof precompute %v: %d regions, %d usable, %d usable reachable on foot", el, len(m.Regions), len(ok), onFoot)
	sort.Slice(ok, func(a, b int) bool { return m.Regions[ok[a]].Cells > m.Regions[ok[b]].Cells })
	for k, i := range ok {
		if k >= 15 {
			break
		}
		r := m.Regions[i]
		t.Logf("#%d hold=(%.0f,%.0f) h=%.1fm area=%dm2 depth=%d onFoot=%v open=%d higherNear=%d launches=%d energy~%.0f expo=%.2f",
			i, r.Hold[0], r.Hold[1], r.Z-r.Ground, r.Cells*4, r.HoldDepth, r.OnFoot, r.Open, r.HigherNear, len(r.Launch),
			(r.Z-r.Ground+3)*1.75+12, w.Exposure(r.Hold[0], r.Hold[1]))
	}
	if el > 200*time.Millisecond && os.Getenv("CI") == "" {
		t.Errorf("precompute too slow: %v", el)
	}
}
