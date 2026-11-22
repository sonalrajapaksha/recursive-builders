use super::math::*;
use super::memory::Track;
use super::{Brain, Mode, Tgt};
use crate::proto::{ActorKind, Event, Obs, WeaponKind};
use crate::world::World;

#[derive(Clone, Debug, Default)]
pub(crate) struct Fz {
    pub rec: bool,
    pub rec_from: V3,
    pub fight_t: f64,
    pub fight_pos: V3,
    pub fought: bool,
    pub multi: bool,
    pub forced: bool,
    pub lines: usize,
    pub hide: bool,
    pub boost: bool,
    pub prev_hp: f64,
    pub st: [f64; 6],
    pub kills_at: f64,
    pub max_ms: f64,
    pub hide3: bool,
    pub hold3: Option<(V3, f64)>,
    pub cnt: std::cell::RefCell<std::collections::BTreeMap<&'static str, f64>>,
    pub nofire_t: f64,
}

impl Brain {
    pub(crate) fn fz_forced(&self) -> bool {
        self.p.fz_force_kills > 0.0 && self.ffa.kills() as f64 >= self.p.fz_force_kills
    }

    pub(crate) fn fz_mode(&self, obs: &Obs) -> bool {
        let p = &self.p;
        p.fz_on > 0.5 && self.fz_forced() || self.fz_ffa(obs)
    }

    pub(crate) fn fz_ffa(&self, obs: &Obs) -> bool {
        let p = &self.p;
        p.fz_on > 0.5 && ((self.ffa.on && (self.ffa.on_t <= p.fz_on_t || (self.ffa.why == 1 && self.ffa.on_t <= p.fz_on_t1))) || self.fz4.on) && (obs.alive as f64) > p.fz_end_alive
    }

    pub(crate) fn fz_update(&mut self, obs: &Obs) {
        if self.p.fz_on <= 0.5 {
            return;
        }
        let t = obs.t;
        let pos = obs.me.pos;
        let mechs: Vec<i64> = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech).map(|tr| tr.id).collect();
        let mut fight = self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < 1.0);
        for ev in &obs.events {
            match ev {
                Event::Hit(h) if mechs.contains(&h.target) => fight = true,
                Event::Kill(_) => fight = true,
                _ => {}
            }
        }
        if fight {
            self.fz.fight_t = t;
            self.fz.fight_pos = pos;
            self.fz.fought = true;
        }
        self.fz.forced = (self.fz_forced() && !self.fz_ffa(obs)) || (self.p.fz_ffa_wave > 0.5 && self.fz_ffa(obs));
        self.fz_stats(obs);
        self.fz.multi = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < self.p.fz_multi_s).count() >= 2;
        if !self.fz_mode(obs) {
            self.fz.rec = false;
            return;
        }
        let p = &self.p;
        let hpf = frac(obs.me.hp, obs.me.max_hp);
        if self.fz.forced {
            self.fz.rec = false;
            let natt = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < 5.0).count();
            if hpf < p.fz_dis_hp && natt >= 2 {
                self.fz.hide = true;
            }
            if hpf >= p.fz_regen {
                self.fz.hide = false;
            }
            return;
        }
        if self.fz.fought && t - self.fz.fight_t > p.fz_calm {
            self.fz.fought = false;
            if !self.fz.rec && hpf < p.fz_rec_hp {
                self.fz.rec = true;
                self.fz.rec_from = self.fz.fight_pos;
            }
        }
        if self.fz.rec && hpf >= p.fz_regen && dist2(pos, self.fz.rec_from) >= p.fz_move {
            self.fz.rec = false;
        }
    }

    fn fz_cover_near(&self, world: Option<&World>, obs: &Obs, tr: &Track) -> bool {
        let Some(world) = world else { return false };
        let r = self.p.fz_cover_r;
        let t = obs.t;
        let eye = up(tr.pos_at(t), self.cfg.mech.eye_height);
        let pos = obs.me.pos;
        let h = obs.me.stats.height.max(1.0) * 0.6;
        for k in 0..8 {
            let a = k as f64 * std::f64::consts::FRAC_PI_4;
            for f in [0.5, 1.0] {
                let q = [pos[0] + r * f * a.cos(), pos[1] + r * f * a.sin(), pos[2]];
                if !world.sight(eye, up(q, h)) {
                    return true;
                }
            }
        }
        false
    }

    pub(crate) fn fz_stronger(&self, obs: &Obs, tr: &Track) -> bool {
        tr.cubes > obs.me.cubes + 0.5 || (tr.has(WeaponKind::Laser) && tr.cubes >= self.p.fz_up_cubes && tr.cubes + 0.5 >= obs.me.cubes)
    }

    fn fz_ahead(&self, obs: &Obs, tr: &Track) -> bool {
        obs.me.hp >= tr.hp && obs.me.cubes + 0.5 >= tr.cubes
    }

    fn fz_alone(&self, obs: &Obs, tr: &Track, r: f64) -> bool {
        let t = obs.t;
        !self.mem.tracks.iter().any(|o| o.kind == ActorKind::Mech && o.id != tr.id && t - o.last_seen < 3.0 && dist(o.pos_at(t), obs.me.pos) < r)
    }

    pub(crate) fn fz_busy(&self, obs: &Obs, tr: &Track) -> bool {
        let t = obs.t;
        if t - self.ffa.foreign_t(tr.id) < self.p.fz_busy_s {
            return true;
        }
        let to_us = (obs.me.pos[1] - tr.pos[1]).atan2(obs.me.pos[0] - tr.pos[0]);
        adiff(tr.aim[0], to_us).abs() > 1.6
    }

    /// the mech of the fight that is live now (exchange within fz_live_s), if any
    fn fz_live(&self, obs: &Obs) -> Option<i64> {
        let t = obs.t;
        let mut best: Option<(f64, i64)> = None;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 2.0 {
                continue;
            }
            let x = tr.last_dmg_t.max(self.ffa.our_hit_t(tr.id));
            if t - x < self.p.fz_live_s && best.map_or(true, |b| x > b.0) {
                best = Some((x, tr.id));
            }
        }
        best.map(|b| b.1)
    }

    /// target and fire gate; world None = skip the cover test
    pub(crate) fn fz_allow(&self, obs: &Obs, world: Option<&World>, tr: &Track, attacker: bool) -> bool {
        let p = &self.p;
        let t = obs.t;
        let d = dist(tr.pos_at(t), obs.me.pos);
        if p.fz_t0 > 0.0 && t < p.fz_t0 && !attacker && (p.fz_t0_ffa < 0.5 || self.ffa.on) {
            let to_us = (obs.me.pos[1] - tr.pos[1]).atan2(obs.me.pos[0] - tr.pos[0]);
            let aims = p.fz_t0_aim > 0.0 && adiff(tr.aim[0], to_us).abs() < p.fz_t0_aim;
            if !(aims || d < p.fz_t0_r) {
                return false;
            }
        }
        if !attacker && !self.fz3_open_ok(obs, tr) {
            return false;
        }
        if !self.fz_mode(obs) || self.fz.forced {
            return true;
        }
        // rule 2: several attackers: hold fire until in cover
        if p.fz_r_multi > 0.5 && self.fz.multi && self.mode == Mode::Retreat && world.is_some() {
            if let Some((c, _)) = self.cover {
                if dist2(c, obs.me.pos) > 3.0 {
                    return false;
                }
            }
        }
        // rule 1: one fight at a time
        if p.fz_r_one > 0.5 {
            if let Some(a) = self.fz_live(obs) {
                if a != tr.id && !(attacker && self.target == Tgt::Mech(tr.id)) {
                    return false;
                }
            }
        }
        if attacker {
            // rule 4: shot by a stronger mech: break LOS when cover is close
            if p.fz_r_str > 0.5 && self.fz_stronger(obs, tr) && self.fz_cover_near(world, obs, tr) {
                return false;
            }
            return true;
        }
        if self.fz.rec && p.fz_r_rec > 0.5 {
            return false;
        }
        if p.fz_r_one > 0.5 && !self.fz_alone(obs, tr, p.fz_alone_r) {
            return false;
        }
        if p.fz_r_ahead > 0.5 && !self.fz_ahead(obs, tr) && frac(tr.hp, tr.max_hp) >= p.fz_low_hp {
            return false;
        }
        if t < p.fz_open_t && d > p.fz_open_r {
            return false;
        }
        true
    }

    pub(crate) fn fz_bonus(&self, obs: &Obs, tr: &Track) -> f64 {
        if !self.fz_mode(obs) || self.p.fz_bonus <= 0.0 {
            return 0.0;
        }
        if self.fz_busy(obs, tr) {
            self.p.fz_bonus
        } else {
            0.0
        }
    }

    pub(crate) fn fz_retreat(&self, obs: &Obs, world: &World, tgt: Option<&Track>) -> bool {
        if !self.fz_mode(obs) || self.fz.forced {
            return false;
        }
        let p = &self.p;
        let t = obs.t;
        let hpf = frac(obs.me.hp, obs.me.max_hp);
        let finish = tgt.map_or(false, |g| frac(g.hp, g.max_hp) < 0.2 && t - g.last_seen < 0.5 && dist(g.pos_at(t), obs.me.pos) < 120.0);
        if p.fz_r_multi > 0.5 && self.fz.multi && !finish {
            return true;
        }
        let under_fire = t - self.mem.last_damage_t < 3.0;
        if p.fz_r_hp > 0.5 && under_fire && hpf < p.fz_dis_hp && !finish {
            return true;
        }
        if self.mode == Mode::Retreat && p.fz_r_hp > 0.5 && hpf < p.fz_dis_hp + 0.1 && under_fire {
            return true;
        }
        if p.fz_r_str > 0.5 {
            for tr in &self.mem.tracks {
                if tr.kind == ActorKind::Mech && t - tr.last_dmg_t < 3.0 && self.fz_stronger(obs, tr) && self.fz_cover_near(Some(world), obs, tr) && !finish {
                    return true;
                }
            }
        }
        false
    }

    /// rat-style hide control in ffa mode
    pub(crate) fn fz_hide(&self, obs: &Obs) -> bool {
        if !self.fz_mode(obs) || self.fz.forced || obs.t - self.mem.last_damage_t < 1.5 {
            return false;
        }
        if self.fz.rec && self.p.fz_r_rec > 0.5 {
            return !matches!(self.mode, Mode::Zone);
        }
        self.p.fz_r_hide > 0.5 && matches!(self.mode, Mode::Idle | Mode::Hunt)
    }

    /// rule 5: stay on the ground out of combat
    pub(crate) fn fz_nojump(&self, obs: &Obs) -> bool {
        if self.p.fz_r_ground < 0.5 || !self.fz_mode(obs) {
            return false;
        }
        if self.fz.forced {
            let t = obs.t;
            return self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 10.0 && self.sf_not_harmless(tr) && dist(tr.pos_at(t), obs.me.pos) < 150.0);
        }
        obs.t - self.mem.last_damage_t > 3.0
    }

    /// forced mode: non-harmless mechs with a line to us (or hit us within 5 s)
    fn fz_line_mechs(&self, obs: &Obs, world: &World) -> Vec<V3> {
        let t = obs.t;
        let me_c = up(obs.me.pos, obs.me.stats.height * 0.6);
        let mut v = Vec::new();
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 1.0 || !self.sf_not_harmless(tr) {
                continue;
            }
            let tp = tr.pos_at(t);
            if dist(tp, obs.me.pos) > 220.0 {
                continue;
            }
            let eye = up(tp, self.cfg.mech.eye_height);
            if t - tr.last_dmg_t < 5.0 || world.sight(eye, me_c) {
                v.push(eye);
            }
        }
        v
    }

    /// forced mode goal: Some(goal) when we must move to cover
    pub(crate) fn fz_force_goal(&mut self, obs: &Obs, world: &World, nav: &crate::nav::Nav) -> Option<super::Goal> {
        self.fz.boost = false;
        if !self.fz.forced {
            return None;
        }
        let eyes = self.fz_line_mechs(obs, world);
        self.fz.lines = eyes.len();
        if self.p.fz_r_multi < 0.5 {
            return None;
        }
        let full = self.fz.hide;
        if eyes.len() < 2 && !full {
            return None;
        }
        let pos = obs.me.pos;
        let h = obs.me.stats.height.max(1.0);
        let allow = if full { 0 } else { 1 };
        let seen_from = |q: V3| eyes.iter().filter(|e| world.sight(**e, up(q, h * 0.5)) || world.sight(**e, up(q, h * 0.92))).count();
        if seen_from(pos) <= allow {
            return Some(super::Goal::Nav { pos, arrive: 1.0 });
        }
        let z = &obs.zone;
        let mut best: Option<(f64, V3)> = None;
        for r in [6.0, 12.0, 18.0, 24.0, 30.0] {
            for k in 0..16 {
                let a = k as f64 * std::f64::consts::PI / 8.0;
                let q0 = [pos[0] + r * a.cos(), pos[1] + r * a.sin(), pos[2] + 2.0];
                let Some(q) = nav.snap(q0) else { continue };
                if (q[0] - q0[0]).hypot(q[1] - q0[1]) > 3.5 || (q[2] - pos[2]).abs() > 6.0 {
                    continue;
                }
                if dist2v(q, z.center) > z.radius - 6.0 {
                    continue;
                }
                if seen_from(q) <= allow {
                    let s = dist2(q, pos);
                    if best.map_or(true, |b| s < b.0) {
                        best = Some((s, q));
                    }
                }
            }
            if best.is_some() {
                break;
            }
        }
        let (_, q) = best?;
        self.fz.boost = true;
        Some(super::Goal::Nav { pos: q, arrive: 1.5 })
    }

    pub(crate) fn fz_stats(&mut self, obs: &Obs) {
        let t = obs.t;
        let k = self.ffa.kills() as f64;
        if k >= 4.0 && self.fz.kills_at <= 0.0 {
            self.fz.kills_at = k;
        }
        let drop = (self.fz.prev_hp - obs.me.hp).max(0.0);
        self.fz.prev_hp = obs.me.hp;
        if self.fz.kills_at <= 0.0 || std::env::var_os("FZ_LOG").is_none() {
            return;
        }
        let natt = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < 5.0).count();
        self.fz.st[0] += 1.0;
        if self.fz.lines >= 2 {
            self.fz.st[1] += 1.0;
        }
        self.fz.st[2] += drop;
        if natt >= 2 {
            self.fz.st[3] += drop;
        }
        if !obs.me.grounded {
            self.fz.st[4] += 1.0;
        }
        self.fz.st[5] = k - 4.0;
        if obs.tick % 20 == 0 {
            eprintln!("FZST seed={} frames={} lines2={} dmg={:.0} dmg2={:.0} air={} kills_after={} maxms={:.2}", self.ffa.seed, self.fz.st[0], self.fz.st[1], self.fz.st[2], self.fz.st[3], self.fz.st[4], self.fz.st[5], self.fz.max_ms);
        }
    }

    /// rule 6: no weapon swap in a fight, no mortar
    pub(crate) fn fz_take_ok(&self, obs: &Obs, kind: WeaponKind, swap: bool) -> bool {
        if self.p.fz_r_swap < 0.5 || !self.fz_mode(obs) {
            return true;
        }
        if self.fz.forced {
            return !(swap && self.fz.lines >= 1);
        }
        if kind == WeaponKind::Mortar {
            return false;
        }
        let t = obs.t;
        let seen = self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 5.0 && dist(tr.pos_at(t), obs.me.pos) < 150.0);
        !(swap && (seen || t - self.mem.last_damage_t < 5.0))
    }

    /// rule 7: keep range against lightning
    pub(crate) fn fz_pref(&self, obs: &Obs, tr: &Track, pref: f64) -> f64 {
        if self.p.fz_lt_r > 0.0 && self.fz_mode(obs) && !self.fz.forced && tr.has(WeaponKind::Lightning) {
            pref.max(self.p.fz_lt_r)
        } else {
            pref
        }
    }
}
