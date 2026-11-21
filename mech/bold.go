package mech

// bold-param-mixed: PARAMETER JUMP, time-phased extreme.
// 20 s .. bPhaseT : very aggressive (house bots do not hunt before ~180 s, so early
//
//	kills/cubes are cheap and the survival tail is long);
//
// after bPhaseT   : very defensive-economy (be quiet and hard to find when the hunters start).
// Practice mode already switches DefaultParams -> squadParams at 20 s; both phases build on squadParams.
const bPhaseT = 120.0

func boldSquad(p Params, late bool) Params {
	p = squadParams(p)
	if !late {
		// aggressive phase: RetreatHP 0.38->0.12; LoseRule/CrowdHide off so RetreatHP is the only trigger
		p.RetreatHP, p.RecoverHP = 0.12, 0.45
		p.LoseRule, p.CrowdHide = false, false
		// AllFoes engages every visible mech inside MaxTarget (brain.go ~563)
		p.AllFoes, p.MaxTarget, p.EngageDist = true, 300, 130
		p.GunRange, p.LaserRange = 100, 140
		p.LootRadius, p.FarmHP, p.FightLoot = 230, 0.3, 110
		p.Finish, p.FinishHP, p.FinishRush = 35, 0.5, true
		p.Pursue, p.Backstab = 0.7, 150
		p.FightBoost, p.DodgeBoost = 35, 40
		return p
	}
	// defensive-economy phase: Ghost doctrine (cover when seen/hurt, <4.6 m/s sneak to a low-exposure home)
	p.Ghost, p.Peek = true, true
	p.HomeExpo = 250
	p.EarlyHide = 1e9 // cover whenever any mech has LOS within 230 m
	p.Shy, p.Alert, p.Evade = 140, 80, true
	p.EngageDist = 40
	p.RetreatHP, p.RecoverHP, p.LoseRule = 0.6, 0.95, false
	// Econ loot scoring, skip loot >60 m away within 10 s of seeing a mech
	p.Econ, p.EconSafe, p.CubeGoal = true, 10, 12
	p.LootRadius, p.FarmHP, p.FightLoot = 150, 0.6, 0
	p.Pursue, p.Stick, p.LowBonus = 0, 0, 0
	p.NanoUp, p.LaserUp = true, false
	return p
}
