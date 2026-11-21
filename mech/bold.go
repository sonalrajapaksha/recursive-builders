package mech

// bold-param-defense: PARAMETER JUMP towards defensive cube economy.
// Applied on top of squadParams (practice mode switches to it after 20 s), but
// reverts the squad "fight everything" doctrine back to the Ghost doctrine
// (sneak to a low-exposure home spot, cover when hurt/seen) and adds Econ looting.
func boldSquad(p Params) Params {
	p = squadParams(p)
	// Ghost: enables hideFromBearing cover (brain.go ~722) and the "home" idle walk
	// capped at 4.6 m/s (silent, <5 m/s) (~831); Peek: shoot-and-duck fight movement.
	p.Ghost, p.Peek = true, true
	// low-exposure home spots weigh 250 (was 120) in homeCost
	p.HomeExpo = 250
	// cover whenever ANY mech has LOS within 230 m, for the whole game (brain.go ~725 EarlyHide)
	p.EarlyHide = 1e9
	// Shy/Alert: step into cover from approaching foes before they reach engage range
	p.Shy, p.Alert, p.Evade = 140, 80, true
	// engage only inside 40 m (Ghost engage rule), still reacts to hits / low HP foes
	p.EngageDist = 40
	// regen early: retreat under 60% HP, only return at 95%. LoseRule would overwrite
	// b.retreat each tick, so it is turned off.
	p.RetreatHP, p.RecoverHP, p.LoseRule = 0.6, 0.95, false
	// economy: value-0.6*distance loot scoring, skip anything >60 m away within 10 s of seeing a mech,
	// no looting while under 45% HP unless adjacent; cube cap raised so cubes keep full value
	p.Econ, p.EconSafe, p.CubeGoal = true, 10, 12
	p.LootRadius, p.FarmHP, p.FightLoot = 150, 0.6, 0
	// less movement-boost / dodge burning of energy, no hunting of hidden foes
	p.Pursue, p.Stick, p.LowBonus = 0, 0, 0
	// nanites/plating first (damage taken and regen)
	p.NanoUp, p.LaserUp = true, false
	return p
}
