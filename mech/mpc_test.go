package mech

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"math"
	"os"
	"testing"
)

// Replays the recorded stream, injecting synthetic enemies (gun + charging laser) around us so
// the MPC path runs every tick; reports controller time. Run: go test ./mech -run MPCTiming -v
func TestMPCTiming(t *testing.T) {
	f, err := os.Open("../check/stream.jsonl.gz")
	if err != nil {
		t.Skip(err)
	}
	gz, _ := gzip.NewReader(f)
	sc := bufio.NewScanner(gz)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	w, err := LoadWorld("../arena")
	if err != nil {
		t.Skip(err)
	}
	var br *Brain
	n := 0
	for sc.Scan() {
		var p struct{ Type string `json:"type"` }
		json.Unmarshal(sc.Bytes(), &p)
		if p.Type == "hello" {
			var h Hello
			json.Unmarshal(sc.Bytes(), &h)
			br = NewBrain(&h, w)
			continue
		}
		if p.Type != "obs" && p.Type != "observation" {
			continue
		}
		var o Obs
		json.Unmarshal(sc.Bytes(), &o)
		o.T += 30 // pretend squad profile is active
		for k := 0; k < 3; k++ {
			a := float64(n+k*2) * 0.7
			d := 40 + 25*float64(k)
			o.Mechs = append(o.Mechs, MechSeen{ID: 900 + k, Kind: "mech",
				Pos:      Vec3{o.Self.Pos[0] + d*math.Cos(a), o.Self.Pos[1] + d*math.Sin(a), o.Self.Pos[2]},
				Vel:      Vec3{3, -2, 0},
				Aim:      [2]float64{a + math.Pi, 0},
				HP:       900, MaxHP: 1400, Weapons: []string{"gun", "laser"}, Charging: k == 0})
		}
		o.Projectiles = append(o.Projectiles, Proj{ID: 1, Kind: "gun", Pos: Vec3{o.Self.Pos[0] - 30, o.Self.Pos[1], o.Self.Pos[2] + 3}, Vel: Vec3{252, 0, 0}})
		br.Act(&o)
		n++
	}
	s := br.mpc
	if s.Calls == 0 {
		t.Fatal("mpc never ran")
	}
	t.Logf("ticks=%d calls=%d aborts=%d avg=%.2fms max=%.2fms panics=%d", n, s.Calls, s.Aborts,
		float64(s.TotNs)/float64(s.Calls)/1e6, float64(s.MaxNs)/1e6, br.Panics)
}
