use std::collections::VecDeque;

use super::math::*;
use super::memory::Track;
use super::strategy::{zone_at, ZoneInfo};
use super::{Brain, Goal, Mode, Tgt};
use crate::nav::Nav;
use crate::proto::{ActorKind, DropObs, Event, Obs, WeaponKind};
use crate::world::World;

#[derive(Default)]
pub(crate) struct Dq {
    pub dmg: VecDeque<(f64, f64)>,
    pub last_hp: f64,
    pub cap: Option<i64>,
    pub cap_in: f64,
    pub deny: Option<(i64, i64, f64)>,
    pub ban: Vec<(i64, f64)>,
    pub anchor: Option<i64>,
    pub cover: Option<(i64, V3, f64)>,
    pub cover_t: f64,
    pub busy: bool,
    pub boost: bool,
    pub avoid: Vec<(V3, f64)>,
    pub k: u32,
    pub init: bool,
    pub cap_t0: f64,
    pub cap_tr: f64,
    pub prog: f64,
    pub prog_t: f64,
    pub lea: Option<(i64, V3, f64)>,
}

impl Brain {
    pub(crate) fn dq_on(&self) -> bool {
        self.p.dp_on >= 0.5
    }

    pub(crate) fn dq_busy(&self) -> bool {
        self.dq_on() && self.dq.busy
    }

    fn dq_log(&self, msg: &str) {
        if crate::runtime::log_enabled() || std::env::var("MECH_LOG").map_or(false, |v| v == "1") {
            eprintln!("[automata] dq {msg}");
        }
    }

    fn dq_ok(&self, d: &DropObs, zi: &ZoneInfo) -> bool {
        d.pos.iter().all(|x| x.is_finite()) && dist2v(d.pos, zi.cur_c) < zi.cur_r - 3.0 && !self.dq.ban.iter().any(|b| b.0 == d.id)
    }

    fn dq_pass_s(&self, obs: &Obs, d: &DropObs) -> f64 {
        let t = obs.t;
        let mut tau = t;
        while tau <= t + self.p.dp_exp_s + 1e-9 {
            let (c, r) = zone_at(&obs.zone, t, tau, self.zone_b);
            if dist2v(d.pos, c) > r - 2.0 {
                return tau - t;
            }
            tau += 0.5;
        }
        f64::INFINITY
    }

    fn dq_travel(&self, obs: &Obs, d: &DropObs) -> f64 {
        (dist2(obs.me.pos, d.pos) - d.radius * 0.5).max(0.0) * self.p.path_factor / obs.me.stats.walk_speed.max(1.0)
    }

    fn dq_pick(&self, obs: &Obs, zi: &ZoneInfo, slack: f64, hpf: f64) -> Option<DropObs> {
        let p = &self.p;
        let z = &obs.zone;
        let me = obs.me.id;
        let mut best: Option<(f64, &DropObs)> = None;
        for d in &obs.drops {
            if !self.dq_ok(d, zi) {
                continue;
            }
            let tr = self.dq_travel(obs, d);
            if d.lands_in > tr + slack {
                continue;
            }
            if d.holder.map_or(false, |h| h != me) && d.progress > d.capture_s * 0.6 {
                continue;
            }
            if hpf >= 0.9 && self.dq_pass_s(obs, d) < p.dp_exp_s {
                continue;
            }
            let deep = (dist2v(d.pos, z.next_center) / z.next_radius.max(1.0)).clamp(0.0, 2.0);
            let mut s = tr + p.dp_deep_w * deep;
            if self.dq.anchor == Some(d.id) {
                s -= 5.0;
            }
            if best.map_or(true, |b| s < b.0) {
                best = Some((s, d));
            }
        }
        best.map(|b| b.1.clone())
    }

    fn dq_orbit(&self, obs: &Obs, d: &DropObs) -> Goal {
        let c = d.pos;
        let dd = dist2(obs.me.pos, c);
        if dd > d.radius + 4.0 {
            return Goal::Nav { pos: c, arrive: 2.0 };
        }
        let a = obs.t * 1.3;
        let r = (d.radius * 0.4).min(3.0);
        Goal::Nav { pos: [c[0] + r * a.cos(), c[1] + r * a.sin(), c[2]], arrive: 1.0 }
    }

    fn dq_inside(&self, obs: &Obs, d: &DropObs, extra: f64) -> Option<i64> {
        let t = obs.t;
        let mut best: Option<(f64, i64)> = None;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 1.0 {
                continue;
            }
            let q = tr.pos_at(t);
            let dd = dist2(q, d.pos);
            if dd < d.radius + extra && (q[2] - d.pos[2]).abs() < 6.0 && best.map_or(true, |b| dd < b.0) {
                best = Some((dd, tr.id));
            }
        }
        best.map(|b| b.1)
    }

    fn dq_threat(&self, obs: &Obs, d: &DropObs) -> Option<(i64, f64)> {
        let t = obs.t;
        let me = obs.me.id;
        if let Some(h) = d.holder {
            if h != me {
                return Some((h, (d.capture_s - d.progress).max(0.0)));
            }
        }
        let mut best: Option<(f64, i64)> = None;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 2.0 {
                continue;
            }
            let q = tr.pos_at(t);
            let dd = dist2(q, d.pos);
            let end = if dd < d.radius + 0.5 {
                d.capture_s
            } else if dd < d.radius + self.p.dp_deny_r {
                let u = unit2(d.pos[0] - q[0], d.pos[1] - q[1]);
                let close = tr.vel[0] * u[0] + tr.vel[1] * u[1];
                if close < 2.0 {
                    continue;
                }
                (dd - d.radius) / close + d.capture_s
            } else {
                continue;
            };
            if best.map_or(true, |b| end < b.0) {
                best = Some((end, tr.id));
            }
        }
        best.map(|b| (b.1, b.0))
    }
    pub(crate) fn dq_decide(&mut self, obs: &Obs, zi: &ZoneInfo, tgt: Option<&Track>, n_att: usize) -> Option<(Mode, Goal, Tgt)> {
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        let pos = me.pos;
        let hpf = frac(me.hp, me.max_hp);
        self.dq.busy = false;
        self.dq.boost = false;
        if !self.dq.init {
            self.dq.init = true;
            self.dq.last_hp = me.hp;
            self.dq.cap_in = -1.0;
        }
        if me.hp < self.dq.last_hp {
            self.dq.dmg.push_back((t, self.dq.last_hp - me.hp));
        }
        self.dq.last_hp = me.hp;
        while self.dq.dmg.front().map_or(false, |x| x.0 < t - 3.0) {
            self.dq.dmg.pop_front();
        }
        let inc = self.dq.dmg.iter().map(|x| x.1).sum::<f64>() / 3.0;
        for ev in &obs.events {
            if let Event::Drop(e) = ev {
                self.dq_log(&format!("done t={t:.1} id={} hp={:.0}/{:.0} kills={}", e.id, me.hp, me.max_hp, self.wave.kills));
                if self.dq.cap == Some(e.id) {
                    self.dq.cap = None;
                }
                if self.dq.deny.map_or(false, |x| x.0 == e.id) {
                    self.dq.deny = None;
                }
            }
        }
        self.dq.ban.retain(|b| b.1 > t);
        self.dq.avoid = obs.drops.iter().filter(|d| d.lands_in <= 1.0 && d.pos.iter().all(|x| x.is_finite())).map(|d| (d.pos, d.radius + 1.5)).collect();
        let find = |id: i64| obs.drops.iter().find(|d| d.id == id).cloned();
        if let Some(id) = self.dq.cap {
            if find(id).is_none() {
                self.dq_log(&format!("gone t={t:.1} id={id} hp={hpf:.2}"));
                self.dq.cap = None;
            }
        }
        if let Some((id, _, _)) = self.dq.deny {
            if find(id).is_none() {
                self.dq.deny = None;
            }
        }
        if self.dq.cap.is_none() {
            self.dq.cap_in = -1.0;
        }
        if zi.urgent {
            return None;
        }
        let walk = me.stats.walk_speed.max(1.0);
        let fast = if me.energy > 30.0 { me.stats.boost_speed.max(walk) } else { walk };

        // contest
        if self.dq.cap.is_none() {
            if let Some((id, hid, t0)) = self.dq.deny {
                let d = find(id);
                let keep = d.as_ref().map_or(false, |d| self.dq_ok(d, zi) && t - t0 < 20.0 && (self.dq_threat(obs, d).is_some() || self.dq_inside(obs, d, 10.0).is_some()));
                if !keep {
                    self.dq.deny = None;
                    if let Some(d) = d.filter(|d| dist2(pos, d.pos) < d.radius && hpf < 0.9 && self.dq_ok(d, zi)) {
                        self.dq.cap = Some(d.id);
                        self.dq.cap_t0 = t;
                        self.dq.cap_tr = 0.0;
                        self.dq.prog = 0.0;
                        self.dq.prog_t = t;
                        self.dq_log(&format!("start t={t:.1} id={} hp={hpf:.2} why=after inc={inc:.0} kills={}", d.id, self.wave.kills));
                    }
                } else {
                    let _ = hid;
                }
            }
            if self.dq.deny.is_none() {
                let mut best: Option<(f64, i64, i64)> = None;
                for d in &obs.drops {
                    if d.lands_in > 1.0 || !self.dq_ok(d, zi) {
                        continue;
                    }
                    let dd = dist2(pos, d.pos);
                    if dd > 130.0 {
                        continue;
                    }
                    let our = (dd - d.radius + 1.0).max(0.0) * p.path_factor / fast;
                    if let Some((hid, end)) = self.dq_threat(obs, d) {
                        if our < end && best.map_or(true, |b| dd < b.0) {
                            best = Some((dd, d.id, hid));
                        }
                    }
                }
                if let Some((_, id, hid)) = best {
                    self.dq.deny = Some((id, hid, t));
                    self.dq_log(&format!("deny t={t:.1} id={id} by={hid} hp={hpf:.2}"));
                }
            }
            if let Some((id, hid, _)) = self.dq.deny {
                if let Some(d) = find(id) {
                    self.dq.busy = true;
                    self.dq.boost = dist2(pos, d.pos) > d.radius;
                    let tg = self.dq_inside(obs, &d, 2.0).or_else(|| self.mem.tracks.iter().find(|tr| tr.id == hid && t - tr.last_seen < 2.0).map(|tr| tr.id));
                    let target = tg.map_or(tgt.map_or(Tgt::None, |tr| Tgt::Mech(tr.id)), Tgt::Mech);
                    return Some((Mode::Drop, self.dq_orbit(obs, &d), target));
                }
            }
        }

        // capture
        if let Some(id) = self.dq.cap {
            if let Some(d) = find(id) {
                let inr = dist2(pos, d.pos) <= d.radius - 0.5;
                if !(inr && d.lands_in <= 0.0) {
                    self.dq.prog_t = t;
                    self.dq.prog = if d.holder == Some(me.id) { d.progress } else { 0.0 };
                } else if d.holder == Some(me.id) && d.progress > self.dq.prog + 1e-6 {
                    self.dq.prog = d.progress;
                    self.dq.prog_t = t;
                } else if d.holder != Some(me.id) || d.progress < self.dq.prog {
                    self.dq.prog = if d.holder == Some(me.id) { d.progress } else { 0.0 };
                }
                let slow_in = p.dp_in_s > 0.0 && !inr && t - self.dq.cap_t0 > self.dq.cap_tr.max(d.lands_in) + p.dp_in_s;
                let stall = p.dp_stall_s > 0.0 && inr && d.lands_in <= 0.0 && t - self.dq.prog_t > p.dp_stall_s;
                if !self.dq_ok(&d, zi) {
                    self.dq.cap = None;
                } else if (self.dq.cap_in >= 0.0 && t - self.dq.cap_in > p.dp_wait && hpf < 0.2) || slow_in || stall {
                    self.dq_log(&format!("abort t={t:.1} id={id} hp={hpf:.2}"));
                    self.dq.ban.push((id, t + p.dp_ban_s));
                    self.dq.cap = None;
                    return None;
                }
            }
        } else {
            let late = t >= p.dp_late_s;
            if let Some(d) = self.dq_pick(obs, zi, p.dp_land_slack, hpf) {
                let tr = self.dq_travel(obs, &d);
                let live = hpf - inc * (tr + 4.0) / me.max_hp.max(1.0) >= p.dp_end;
                if dist2(pos, d.pos) <= p.dp_far && d.lands_in <= tr + p.dp_land_slack && live {
                    let need = (inc * (tr + 5.0) / me.max_hp.max(1.0)).min(p.dp_hp_cap);
                    let exp = hpf < 0.9 && self.dq_pass_s(obs, &d) < p.dp_exp_s;
                    let why = if hpf < p.dp_hp.max(need) {
                        "hp"
                    } else if hpf < p.dp_hp2 && n_att >= 3 {
                        "multi"
                    } else if exp {
                        "exp"
                    } else if late {
                        "late"
                    } else {
                        ""
                    };
                    if !why.is_empty() {
                        self.dq.cap = Some(d.id);
                        self.dq.cap_in = -1.0;
                        self.dq.cap_t0 = t;
                        self.dq.cap_tr = tr;
                        self.dq.prog = 0.0;
                        self.dq.prog_t = t;
                        self.dq_log(&format!("start t={t:.1} id={} hp={hpf:.2} why={why} inc={inc:.0} travel={tr:.1} kills={}", d.id, self.wave.kills));
                    }
                }
            }
        }
        let id = self.dq.cap?;
        let d = find(id)?;
        let dd = dist2(pos, d.pos);
        if dd <= d.radius - 0.5 && self.dq.cap_in < 0.0 {
            self.dq.cap_in = t;
        }
        self.dq.busy = true;
        self.dq.boost = dd > d.radius;
        let target = match self.dq_inside(obs, &d, 1.0) {
            Some(h) => Tgt::Mech(h),
            None => tgt.map_or(Tgt::None, |tr| Tgt::Mech(tr.id)),
        };
        Some((Mode::Drop, self.dq_orbit(obs, &d), target))
    }

    fn dq_cover(&mut self, obs: &Obs, world: &World, nav: &Nav, zi: &ZoneInfo, d: &DropObs) -> V3 {
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        let pos = me.pos;
        let c = d.pos;
        if let Some((id, q, _)) = self.dq.cover {
            if id == d.id && t - self.dq.cover_t < 0.5 {
                return q;
            }
        }
        self.dq.cover_t = t;
        let mut eyes: Vec<(f64, V3)> = self
            .mem
            .tracks
            .iter()
            .filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 8.0)
            .map(|tr| {
                let q = tr.pos_at(t);
                (dist(q, pos), up(q, self.cfg.mech.eye_height))
            })
            .collect();
        eyes.sort_by(|a, b| a.0.total_cmp(&b.0));
        eyes.truncate(6);
        let h = me.stats.height.max(1.0);
        let z = &obs.zone;
        let score = |q: V3| -> f64 {
            let seen = eyes.iter().filter(|e| world.sight(e.1, up(q, h * 0.6))).count() as f64;
            seen * 12.0 + 0.04 * dist2(q, c) + 0.03 * dist2(q, pos) + 0.3 * (dist2v(q, z.next_center) - z.next_radius + 10.0).max(0.0)
        };
        let mut best: Option<(f64, V3)> = None;
        if let Some((id, q, _)) = self.dq.cover {
            if id == d.id && dist2(q, c) <= p.dp_r + 1.0 && dist2v(q, zi.cur_c) < zi.cur_r - 8.0 {
                best = Some((score(q) - 1.0, q));
            }
        }
        let rmax = p.dp_r.max(d.radius + 5.0);
        for j in 0..10 {
            if self.spent_ms() > 10.0 {
                break;
            }
            self.dq.k = self.dq.k.wrapping_add(1);
            let k = self.dq.k as f64;
            let r = d.radius + 4.0 + (rmax - d.radius - 4.0) * (((k * 0.618) % 1.0) + 0.0).clamp(0.0, 1.0);
            let a = k * 2.39996 + j as f64 * 0.1;
            let x = c[0] + r * a.cos();
            let y = c[1] + r * a.sin();
            let q0 = [x, y, fin(world.floor_below(x, y, c[2] + 3.0), c[2])];
            let Some(q) = nav.snap(q0) else { continue };
            if dist(q, q0) > 4.0 || !q.iter().all(|v| v.is_finite()) || dist2(q, c) < d.radius + 3.0 || (q[2] - c[2]).abs() > 5.0 || dist2v(q, zi.cur_c) > zi.cur_r - 8.0 {
                continue;
            }
            let s = score(q);
            if best.map_or(true, |b| s < b.0) {
                best = Some((s, q));
            }
        }
        let q = best.map_or(c, |b| b.1);
        let s = best.map_or(0.0, |b| b.0);
        self.dq.cover = Some((d.id, q, s));
        q
    }
    pub(crate) fn dq_post(&mut self, obs: &Obs, world: &World, nav: &Nav, zi: &ZoneInfo, mode: &mut Mode, goal: &mut Goal, goal_id: &mut i64) {
        let p = self.p.clone();
        self.dq.lea = None;
        if self.dq.busy || zi.urgent || matches!(*mode, Mode::Zone | Mode::Drop | Mode::Roof) {
            return;
        }
        let t = obs.t;
        let pos = obs.me.pos;
        let hpf = frac(obs.me.hp, obs.me.max_hp);
        let phase = self.wave.kills as f64 >= p.dp_kills || t >= p.dp_t0;
        let pre = !phase && p.dp_pre >= 0.5 && !obs.drops.is_empty();
        if !phase && !pre {
            return;
        }
        let Some(d) = self.dq_pick(obs, zi, if phase { 3.0 } else { 1e9 }, hpf) else {
            return;
        };
        if self.dq.anchor != Some(d.id) {
            self.dq_log(&format!("anchor t={t:.1} id={} dist={:.0} kills={}", d.id, dist2(pos, d.pos), self.wave.kills));
        }
        self.dq.anchor = Some(d.id);
        let c = d.pos;
        if phase {
            self.dq.lea = Some((d.id, c, p.dp_leash + p.st_leash));
        }
        let gp = match *goal {
            Goal::Nav { pos: g, .. } => Some(g),
            Goal::Range { pos: g, .. } => Some(g),
            Goal::Field { .. } | Goal::None => None,
        };
        let leash = p.dp_leash;
        let far = |g: Option<V3>, lim: f64| g.map_or(true, |g| dist2(g, c) > lim);
        if pre {
            if *mode == Mode::Idle {
                let q = self.dq_cover(obs, world, nav, zi, &d);
                *goal = Goal::Nav { pos: q, arrive: 2.0 };
            }
            return;
        }
        let dme = dist2(pos, c);
        let m0 = *mode;
        if (t * 10.0).round() as i64 % 10 == 0 {
            self.dq_log(&format!("st t={t:.1} id={} mode={m0:?} dme={dme:.0} gd={:.0} hp={hpf:.2}", d.id, gp.map_or(-1.0, |g| dist2(g, c))));
        }
        match *mode {
            Mode::Fight => {
                let calm = t - self.mem.last_damage_t > 2.0;
                let reach = p.dp_reach > 0.0 && dme * p.path_factor / obs.me.stats.walk_speed.max(1.0) < d.lands_in + p.dp_reach;
                if (dme < 2.0 * leash || calm || reach) && (dme > leash || far(gp, leash + 30.0)) {
                    let q = self.dq_cover(obs, world, nav, zi, &d);
                    *goal = Goal::Nav { pos: q, arrive: 2.0 };
                }
            }
            Mode::Hunt | Mode::Idle => {
                if far(gp, leash) || *mode == Mode::Idle {
                    let q = self.dq_cover(obs, world, nav, zi, &d);
                    *mode = Mode::Idle;
                    *goal = Goal::Nav { pos: q, arrive: 2.0 };
                    *goal_id = -1;
                }
            }
            Mode::Loot => {
                let laser = self.mem.pickups.iter().any(|it| it.id == *goal_id && it.kind == WeaponKind::Laser);
                if far(gp, leash) && !laser {
                    let q = self.dq_cover(obs, world, nav, zi, &d);
                    *mode = Mode::Idle;
                    *goal = Goal::Nav { pos: q, arrive: 2.0 };
                    *goal_id = -1;
                }
            }
            Mode::Retreat => {
                if dme <= leash && far(gp, p.dp_r + 10.0) {
                    let q = self.dq_cover(obs, world, nav, zi, &d);
                    *goal = Goal::Nav { pos: q, arrive: 1.5 };
                    self.cover = Some((q, t));
                }
            }
            _ => {}
        }
    }
    pub(crate) fn dq_lea(&mut self, obs: &Obs, world: &World, nav: &Nav, zi: &ZoneInfo) -> Option<(V3, f64, V3)> {
        let (id, c, r) = self.dq.lea?;
        let d = obs.drops.iter().find(|d| d.id == id)?.clone();
        let q = self.dq_cover(obs, world, nav, zi, &d);
        Some((c, r, q))
    }
    pub(crate) fn dq_ring_cost(&self, q: V3) -> f64 {
        if !self.dq_on() || self.dq.busy {
            return 0.0;
        }
        let mut s = 0.0;
        for (c, r) in &self.dq.avoid {
            let d = dist2(q, *c);
            if d < *r && (q[2] - c[2]).abs() < 6.0 {
                s += self.p.dp_ring_w * (r - d + 2.0);
            }
        }
        s
    }
}
