package mech

import "math"

// Lightning counter (Params.LightCounter): when a single enemy visibly holds a
// charging laser within ~55 m and we hold lightning, commit a short boosted
// close-in to land the cone (shorts the laser for 2 s), then the base fight
// logic takes over. Aborts when a second hunter is near or HP is low.
func (b *Brain) lightCounterTarget(o *Obs, hpFrac float64) *Track {
	me := &o.Self
	now := b.now
	if !b.P.LightCounter || hpFrac < 0.5 || me.Energy < 25 {
		return nil
	}
	_, light := hasWeapon(me.Weapons, "lightning")
	if light == nil {
		return nil
	}
	var cand *Track
	for _, t := range b.tracks {
		if now-t.Seen > 2.5 {
			continue
		}
		if t.Seen == now && t.LOS && t.Charging && holds(t.Weapons, "laser") && t.Dist <= 55 && t.Dist > 4 {
			toMe := math.Atan2(me.Pos[1]-t.Pos[1], me.Pos[0]-t.Pos[0])
			if t.Dist <= 30 || math.Abs(angDiff(t.Aim[0], toMe)) > 0.35 || b.lcID == t.ID && now-b.lcAt < 1.5 {
				if cand == nil || t.Dist < cand.Dist {
					cand = t
				}
			}
		}
	}
	if cand == nil {
		return nil
	}
	for _, t := range b.tracks {
		if t.ID != cand.ID && now-t.Seen < 3 && t.Dist < 100 {
			return nil // a second hunter is near: abort
		}
	}
	b.lcID, b.lcAt = cand.ID, now
	return cand
}

// lightCounterFire points at the target and pulls the lightning trigger once in cone.
func (b *Brain) lightCounterFire(o *Obs, t *Track, aim *[2]float64, act *Action) {
	me := &o.Self
	st := &me.Stats
	li, light := hasWeapon(me.Weapons, "lightning")
	if light == nil || li > 1 {
		return
	}
	th := b.Cfg.Mech.Height * b.scaleOf(t.Cubes)
	muzzle := Vec3{me.Pos[0], me.Pos[1], me.Pos[2] + st.MuzzleHeight}
	dp := Vec3{t.Pos[0] + t.Vel[0]*(lat+0.05), t.Pos[1] + t.Vel[1]*(lat+0.05), t.Pos[2] + th*0.5}
	hy := math.Atan2(dp[1]-muzzle[1], dp[0]-muzzle[0])
	hp := math.Atan2(dp[2]-muzzle[2], hyp(dp[0]-muzzle[0], dp[1]-muzzle[1]))
	*aim = [2]float64{hy, hp}
	dist := hyp(dp[0]-muzzle[0], dp[1]-muzzle[1])
	cone := light.Stats.ConeDeg * math.Pi / 180
	if dist < light.Stats.Range-1.5 && math.Abs(angDiff(hy, me.Aim[0])) < cone*0.5-0.05 && me.Energy >= light.Stats.Energy {
		act.Fire[li] = true
	}
}
