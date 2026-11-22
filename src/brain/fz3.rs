use super::aim::FireOut;
use super::math::*;
use super::memory::Track;
use super::{Brain, Goal, Mode, Tgt};
use crate::nav::Nav;
use crate::proto::{ActorKind, Obs, SoundDist, WeaponKind};
use crate::world::World;

impl Brain {
    pub(crate) fn fz3(&self, _obs: &Obs) -> bool {
        let p = &self.p;
        p.fz_on > 0.5 && ((self.ffa.on && (self.ffa.on_t <= p.fz_on_t || (p.fz3_why1 > 0.5 && self.ffa.why == 1 && self.ffa.on_t <= p.fz_on_t1))) || self.fz4.on)
    }

    pub(crate) fn fz3_cnt(&self, k: &'static str) {
        if self.au.on {
            *self.fz.cnt.borrow_mut().entry(k).or_insert(0.0) += 1.0;
        }
    }

    fn fz3_last(&self, obs: &Obs) -> bool {
        self.p.fz3_end > 0.5 && (obs.alive as f64) <= self.p.fz3_e_alive && self.fz3(obs)
    }

    fn fz3_watched(&self, obs: &Obs, id: i64, tp: V3) -> bool {
        let p = &self.p;
        let t = obs.t;
        let pos = obs.me.pos;
        if self.mem.tracks.iter().any(|o| o.kind == ActorKind::Mech && o.id != id && t - o.last_seen < p.fz3_w_s && dist(o.pos_at(t), pos) < p.fz3_w_los) {
            return true;
        }
        let tb = (tp[1] - pos[1]).atan2(tp[0] - pos[0]);
        self.mem.sounds.iter().any(|s| {
            if t - s.t > p.fz3_w_s || adiff(s.bearing, tb).abs() < 0.3 {
                return false;
            }
            let short = matches!(s.kind.as_str(), "step" | "boost" | "jet" | "reload");
            let mech = !matches!(s.kind.as_str(), "npc_gun" | "crate" | "death" | "drop" | "explosion");
            let mid = matches!(s.dist, SoundDist::Mid);
            mech && (matches!(s.dist, SoundDist::Near) || (short && mid && p.fz3_w_hear >= 90.0) || (mid && p.fz3_w_hear >= 160.0))
        })
    }

    pub(crate) fn fz3_open_ok(&self, obs: &Obs, tr: &Track) -> bool {
        let p = &self.p;
        if p.fz3_gate < 0.5 && p.fz3_watch < 0.5 && p.fz3_end < 0.5 {
            return true;
        }
        if !self.fz3(obs) {
            return true;
        }
        let t = obs.t;
        let me = &obs.me;
        if t - self.ffa.our_hit_t(tr.id) < p.fz3_live_s {
            return true;
        }
        let hpf = frac(me.hp, me.max_hp);
        let tf = frac(tr.hp, tr.max_hp);
        let tp = tr.pos_at(t);
        let d = dist(tp, me.pos);
        if self.fz3_last(obs) {
            let ok = (d <= p.fz3_e_r && me.hp >= tr.hp - p.fz3_e_lead) || tf < p.fz3_g_low;
            self.fz3_cnt(if ok { "fz3_end_open" } else { "fz3_end_block" });
            return ok;
        }
        if p.fz3_gate > 0.5 && !((hpf >= p.fz3_g_hp && me.hp - tr.hp >= p.fz3_g_lead) || tf < p.fz3_g_low) {
            self.fz3_cnt("fz3_gate_block");
            return false;
        }
        if p.fz3_watch > 0.5 && self.fz3_watched(obs, tr.id, tp) {
            self.fz3_cnt("fz3_watch_block");
            return false;
        }
        true
    }

    pub(crate) fn fz3_ret(&self, obs: &Obs) -> bool {
        self.p.fz3_open > 0.5 && self.fz3(obs)
    }

    pub(crate) fn fz3_bonus(&self, obs: &Obs, tr: &Track) -> f64 {
        let p = &self.p;
        if p.fz3_tgt < 0.5 || !self.fz3(obs) {
            return 0.0;
        }
        let t = obs.t;
        let low = frac(tr.hp, tr.max_hp) < p.fz3_t_low;
        let mut busy = t - self.ffa.foreign_t(tr.id) < p.fz3_t_busy;
        if !busy {
            let tp = tr.pos_at(t);
            busy = self.mem.tracks.iter().any(|o| {
                if o.kind != ActorKind::Mech || o.id == tr.id || t - o.last_seen > p.fz3_t_busy {
                    return false;
                }
                let q = o.pos_at(t);
                let dd = dist2(q, tp).max(1.0);
                let b = (q[1] - tp[1]).atan2(q[0] - tp[0]);
                adiff(tr.aim[0], b).abs() < (8.0f64).atan2(dd) + 0.05
            });
        }
        let mut s = 0.0;
        if low {
            s += p.fz3_t_bonus;
        }
        if busy {
            s += p.fz3_t_bonus;
        }
        if s > 0.0 {
            self.fz3_cnt("fz3_tgt_bonus");
        }
        s
    }

    pub(crate) fn fz3_retreat(&mut self, obs: &Obs, tgt: Option<&Track>) -> bool {
        self.fz.hide3 = false;
        if !self.fz3(obs) {
            return false;
        }
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        let hpf = frac(me.hp, me.max_hp);
        let finish = tgt.map_or(false, |g| frac(g.hp, g.max_hp) < p.fz3_finish && t - g.last_seen < 0.5 && dist(g.pos_at(t), me.pos) < 120.0);
        if finish {
            return false;
        }
        if p.fz3_open > 0.5 {
            let bad = self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < p.fz3_o_s && (tr.hp - me.hp > p.fz3_o_lead || hpf < p.fz3_o_hp));
            if bad {
                self.fz.hide3 = true;
                self.fz3_cnt("fz3_open_hide");
                return true;
            }
        }
        if p.fz3_watch > 0.5 {
            let n = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_dmg_t < p.fz3_w_s).count();
            if n >= 2 {
                self.fz.hide3 = true;
                self.fz3_cnt("fz3_watch_hide");
                return true;
            }
        }
        if p.fz3_gate > 0.5 && hpf < p.fz3_g_hp && t - self.mem.last_damage_t > p.fz3_o_s {
            let seen = self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 1.0 && dist(tr.pos_at(t), me.pos) < 200.0 && t - self.ffa.our_hit_t(tr.id) > p.fz3_live_s);
            if seen {
                self.fz3_cnt("fz3_gate_hide");
                return true;
            }
        }
        false
    }

    fn fz3_cover_score(world: &World, q: V3) -> f64 {
        let e = up(q, 6.0);
        let mut n = 0.0;
        for k in 0..8 {
            let a = k as f64 * std::f64::consts::FRAC_PI_4;
            if !world.sight(e, [q[0] + 12.0 * a.cos(), q[1] + 12.0 * a.sin(), e[2]]) {
                n += 1.0;
            }
        }
        n
    }

    fn fz3_hold_pt(&mut self, obs: &Obs, world: &World, nav: &Nav) -> Option<V3> {
        let p = self.p.clone();
        let t = obs.t;
        let z = &obs.zone;
        let pos = obs.me.pos;
        let (c, r) = (z.center, z.radius);
        let fits = |q: V3| -> bool {
            let f = dist2v(q, c) / r.max(1.0);
            let nxt = z.next_radius < 30.0 || dist2v(q, z.next_center) < z.next_radius - 12.0;
            f >= p.fz3_p_lo - 0.05 && f <= p.fz3_p_hi + 0.05 && nxt && r - dist2v(q, c) > 25.0
        };
        if let Some((q, tc)) = self.fz.hold3 {
            if t - tc < p.fz3_p_re && fits(q) {
                return Some(q);
            }
        }
        let mechs: Vec<V3> = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 30.0).map(|tr| tr.pos_at(t)).collect();
        let nb = 16;
        let mut secs: Vec<(f64, f64)> = Vec::new();
        for k in 0..nb {
            let a = k as f64 * 2.0 * std::f64::consts::PI / nb as f64;
            let n = mechs.iter().filter(|m| (m[0] - c[0]).hypot(m[1] - c[1]) > 0.15 * r && adiff((m[1] - c[1]).atan2(m[0] - c[0]), a).abs() < 0.7).count() as f64;
            let q = [c[0] + 0.55 * r * a.cos(), c[1] + 0.55 * r * a.sin()];
            let s = 3.0 * n + (q[0] - pos[0]).hypot(q[1] - pos[1]) / 100.0;
            secs.push((s, a));
        }
        secs.sort_by(|x, y| x.0.total_cmp(&y.0));
        let mut best: Option<(f64, V3)> = None;
        for &(s0, a) in secs.iter().take(3) {
            for f in [p.fz3_p_lo, 0.5 * (p.fz3_p_lo + p.fz3_p_hi), p.fz3_p_hi] {
                let x = c[0] + f * r * a.cos();
                let y = c[1] + f * r * a.sin();
                let q0 = [x, y, fin(world.floor_below(x, y, pos[2] + 40.0), pos[2])];
                let Some(q) = nav.snap(q0) else { continue };
                if !q.iter().all(|v| v.is_finite()) || dist2(q, q0) > 10.0 || !fits(q) {
                    continue;
                }
                let s = s0 - 0.5 * Self::fz3_cover_score(world, q);
                if best.map_or(true, |b| s < b.0) {
                    best = Some((s, q));
                }
            }
        }
        let q = best?.1;
        self.fz.hold3 = Some((q, t));
        Some(q)
    }

    pub(crate) fn fz3_hold(&mut self, obs: &Obs, world: &World, nav: &Nav, mode: Mode, target: Tgt) -> Option<(Mode, Goal, Tgt)> {
        let p = &self.p;
        if p.fz3_pos < 0.5 || obs.t < p.fz3_p_t || !self.fz3(obs) || !matches!(mode, Mode::Idle | Mode::Hunt) {
            return None;
        }
        if self.fz3_last(obs) {
            return None;
        }
        if let Tgt::Mech(id) = target {
            if matches!(mode, Mode::Hunt) && self.mem.tracks.iter().any(|tr| tr.id == id && frac(tr.hp, tr.max_hp) < p.fz3_t_low) {
                return None;
            }
        }
        let q = self.fz3_hold_pt(obs, world, nav)?;
        self.fz3_cnt("fz3_pos");
        Some((Mode::Idle, Goal::Nav { pos: q, arrive: 3.0 }, Tgt::None))
    }

    pub(crate) fn fz3_post(&mut self, obs: &Obs, world: &World, fc: &mut FireOut) {
        if !self.fz3(obs) {
            return;
        }
        let p = self.p.clone();
        let Some(ls) = obs.me.weapons.iter().position(|w| w.as_ref().map_or(false, |w| w.kind == WeaponKind::Laser)) else { return };
        let Some(w) = obs.me.weapons[ls].clone() else { return };
        if self.fz.hide3 && w.charge <= 0.0 {
            fc.fire[ls] = false;
            return;
        }
        if !self.fz3_last(obs) || fc.target.is_some() || w.cooldown > 0.0 {
            return;
        }
        let t = obs.t;
        let pos = obs.me.pos;
        let me_c = up(pos, obs.me.stats.height * 0.6);
        let full = w.stats.charge.max(0.05);
        if w.charge <= 0.0 && frac(obs.me.hp, obs.me.max_hp) < p.fz3_e_hp {
            return;
        }
        let cue = self.mem.sounds.iter().any(|s| t - s.t < p.fz3_e_cue && matches!(s.dist, SoundDist::Near) && !matches!(s.kind.as_str(), "npc_gun" | "crate" | "death" | "drop" | "explosion"));
        let mut near = false;
        let mut come = false;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 4.0 {
                continue;
            }
            let q = tr.pos_at(t);
            if dist(q, pos) > p.fz3_e_r + 40.0 {
                continue;
            }
            if world.sight(up(q, self.cfg.mech.eye_height), me_c) {
                return;
            }
            near = true;
            let v = tr.vel;
            if t - tr.last_seen < p.fz3_e_cue && (v[0] * (pos[0] - q[0]) + v[1] * (pos[1] - q[1])) > 0.0 {
                come = true;
            }
        }
        if !near || (w.charge <= 0.0 && !cue && !come) {
            return;
        }
        fc.fire[ls] = w.charge < full + p.fz3_e_hold;
        fc.charging = fc.fire[ls] || fc.charging;
        self.fz3_cnt("fz3_end_charge");
    }
}
