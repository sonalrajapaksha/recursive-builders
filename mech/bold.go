package mech

// bold-param-aggro: PARAMETER JUMP towards extreme aggression.
// Applied on top of squadParams (which practice mode switches to after 20 s;
// DefaultParams/Ghost doctrine only governs the first 20 s).
func boldSquad(p Params) Params {
	p = squadParams(p)
	// retreat only at <12% HP (was 38%), come back out at 45% (was 80%)
	p.RetreatHP, p.RecoverHP = 0.12, 0.45
	// LoseRule overwrites b.retreat each tick (brain.go ~661) and CrowdHide forces
	// retreat when >=3 foes are seen; both off so RetreatHP is the only retreat trigger.
	p.LoseRule, p.CrowdHide = false, false
	// engage every visible mech inside MaxTarget (AllFoes case, brain.go ~563)
	p.AllFoes, p.MaxTarget, p.EngageDist = true, 300, 130
	p.GunRange, p.LaserRange = 100, 140
	// loot: loot() caps candidates at 260 m
	p.LootRadius, p.FarmHP, p.FightLoot = 230, 0.3, 110
	// finishing: close in hard on foes under 50% HP, and rush with boost
	p.Finish, p.FinishHP, p.FinishRush = 35, 0.5, true
	p.Pursue, p.Backstab = 0.7, 150
	p.FightBoost, p.DodgeBoost = 35, 40
	return p
}
