package mech

import (
	"reflect"
	"testing"
)

func noFFA(t *testing.T, where string, p Params) {
	t.Helper()
	if p.LateR != 0 || p.HoldOut != 0 || p.HoldMin != 0 || p.DuelFlee != 0 {
		t.Fatalf("%s: FFA knobs must be off, got LateR=%v HoldOut=%v HoldMin=%v DuelFlee=%v", where, p.LateR, p.HoldOut, p.HoldMin, p.DuelFlee)
	}
}

// feed runs observe over ticks 0.1 s apart from t0 to t1 with the given alive count and events on the first tick.
func feed(b *Brain, t0, t1 float64, alive int, ev []Event) {
	for k := 0; t0+float64(k)*0.1 < t1; k++ {
		o := &Obs{T: t0 + float64(k)*0.1, Alive: alive}
		if k == 0 {
			o.Events = ev
		}
		b.now = o.T
		b.observe(o)
	}
}

// TestFFAGateOffInPractice: practice-like play (every death is our kill, plus one house bot dying to the zone,
// which latches the old detector) must never switch the FFA profile on, and the params must stay exactly the
// ones practice has always used. Two deaths we did not cause switch it on.
func TestFFAGateOffInPractice(t *testing.T) {
	noFFA(t, "DefaultParams", DefaultParams())
	noFFA(t, "squadParams", squadParams(DefaultParams()))

	b := &Brain{P: DefaultParams()}
	feed(b, 0, 25, 16, nil)
	if !b.pracOn || !reflect.DeepEqual(b.P, squadParams(DefaultParams())) {
		t.Fatal("squad profile should be on after 20 s in practice")
	}
	alive := 16
	for k := 0; k < 6; k++ { // we kill six house bots
		alive--
		feed(b, 25+float64(k)*10, 35+float64(k)*10, alive, []Event{{Type: "kill", Target: 100 + k}})
		if b.ffaOn || !reflect.DeepEqual(b.P, squadParams(DefaultParams())) {
			t.Fatalf("practice kill %d changed params", k)
		}
	}
	alive-- // one house bot dies to the zone: old detector latches, FFA profile must stay off
	feed(b, 90, 120, alive, nil)
	if !b.notPractice || b.ffaOn {
		t.Fatalf("one unexplained death: want notPractice && !ffaOn, got %v %v", b.notPractice, b.ffaOn)
	}
	if !reflect.DeepEqual(b.P, DefaultParams()) {
		t.Fatal("after one unexplained death params must be exactly DefaultParams (old behaviour)")
	}
	noFFA(t, "after one unexplained death", b.P)

	alive-- // a second death we did not cause: proven free-for-all
	feed(b, 120, 121, alive, nil)
	if !b.ffaOn || b.P.HoldOut == 0 || b.P.LateR == 0 {
		t.Fatal("two unexplained deaths should switch the FFA profile on")
	}
}
