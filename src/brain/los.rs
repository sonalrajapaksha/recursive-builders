use std::collections::HashMap;

use super::math::*;
use super::strategy::{zone_at, ZoneInfo};
use super::{Brain, Goal, Mode, Tgt};
use crate::nav::Nav;
use crate::proto::{ActorKind, Obs, SoundDist, WeaponKind};
use crate::world::World;

#[derive(Clone, Copy, Debug)]
struct Th {
    id: i64,
    eye: V3,
    pos: V3,
    gun: bool,
    laser: bool,
    lightning: bool,
    k: f64,
    real: bool,
    mz: V3,
}

#[derive(Clone, Copy, Debug, Default)]
struct Ev {
    e: f64,
    e_oth: f64,
    v: f64,
    tid: i64,
    d_t: f64,
    n: u32,
    near2: f64,
    w_pref: f64,
    pref_seen: bool,
    nr: u32,
    base_seen: bool,
}

pub(crate) struct LosSt {
    pub st: u8,
    pub hold: bool,
    pub replans: u32,
    pub n_bel: u32,
    pub one: bool,
    one_p: bool,
    base: i64,
    spot: Option<V3>,
    eval_t: f64,
    tid: i64,
    bad_since: f64,
    lost_since: f64,
    anchor: V3,
    used: Vec<(V3, f64)>,
    cache: HashMap<(i64, i32, i32), (V3, f64, bool, f64)>,
}

impl LosSt {
    pub fn new() -> LosSt {
        LosSt { st: 0, hold: false, replans: 0, n_bel: 0, one: false, one_p: false, base: -1, spot: None, eval_t: -1e9, tid: -1, bad_since: -1.0, lost_since: -1.0, anchor: [0.0; 3], used: Vec::new(), cache: HashMap::new() }
    }
}

const GUN_P: [f64; 4] = [0.77, 0.56, 0.32, 0.07];
const LASER_P: [f64; 4] = [0.58, 0.58, 0.22, 0.14];

fn band(d: f64) -> Option<usize> {
    if d < 45.0 {
        Some(0)
    } else if d < 90.0 {
        Some(1)
    } else if d < 140.0 {
        Some(2)
    } else if d < 200.0 {
        Some(3)
    } else {
        None
    }
}

fn w_of(h: &Th, d: f64) -> f64 {
    let Some(b) = band(d) else { return 0.0 };
    let mut s = 0.0;
    if h.gun {
        s += 150.0 * GUN_P[b];
    }
    if h.laser {
        s += 131.0 * LASER_P[b];
    }
    if h.lightning && d < 45.0 {
        s += 240.0;
    }
    s * h.k
}

fn see(world: &World, cache: &mut HashMap<(i64, i32, i32), (V3, f64, bool, f64)>, canopy: bool, shot: bool, h: &Th, q: V3, top: f64, t: f64) -> bool {
    let d = dist2(h.pos, q);
    if d > 205.0 {
        return false;
    }
    let key = (h.id, q[0].floor() as i32, q[1].floor() as i32);
    if let Some(&(e, z, r, tt)) = cache.get(&key) {
        if dist(e, h.eye) < 2.0 && (z - q[2]).abs() < 1.0 && t - tt < 1.0 {
            return r;
        }
    }
    let c = up(q, top * 0.5);
    let tp = up(q, top);
    let r = if shot {
        world.ray(h.mz, tp).is_none() || world.ray(h.mz, c).is_none()
    } else if d <= 45.0 || !canopy { world.sight_near(h.eye, tp) || world.sight_near(h.eye, c) } else { world.sight(h.eye, tp) || world.sight(h.eye, c) };
    cache.insert(key, (h.eye, q[2], r, t));
    r
}

impl Brain {
    fn los_threats(&self, obs: &Obs, world: &World) -> Vec<Th> {
        let p = &self.p;
        let t = obs.t;
        let pos = obs.me.pos;
        let eh = self.cfg.mech.eye_height;
        let spc = self.cfg.cubes.size_per_cube;
        let mh = self.cfg.mech.muzzle_height;
        let mut v: Vec<(f64, Th)> = Vec::new();
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > p.los_mem_s {
                continue;
            }
            let mut q = tr.pos_at(t);
            if p.los_pred_s > 0.0 && t - tr.last_seen < 1.0 {
                let m = [tr.vel[0] * p.los_pred_s, tr.vel[1] * p.los_pred_s];
                let l = m[0].hypot(m[1]);
                let k = if l > 25.0 { 25.0 / l } else { 1.0 };
                let x = q[0] + m[0] * k;
                let y = q[1] + m[1] * k;
                q = [x, y, fin(world.floor_below(x, y, q[2] + 3.0), q[2])];
            }
            let d = dist(q, pos);
            if d > 260.0 {
                continue;
            }
            let none = tr.weapons.is_empty();
            v.push((d, Th { id: tr.id, eye: up(q, eh * (1.0 + spc * tr.cubes.max(0.0))), pos: q, gun: none || tr.has(WeaponKind::Gun), laser: tr.has(WeaponKind::Laser), lightning: tr.has(WeaponKind::Lightning), k: 1.0 + 0.04 * tr.cubes.max(0.0), real: true, mz: up(q, mh * (1.0 + spc * tr.cubes.max(0.0))) }));
        }
        let mut k = 0i64;
        for s in &self.mem.sounds {
            if t - s.t > p.los_snd_s {
                continue;
            }
            let (gun, laser, lightning) = match s.kind.as_str() {
                "gun" => (true, false, false),
                "laser" | "laser_charge" => (false, true, false),
                "lightning" => (false, false, true),
                _ => continue,
            };
            let r = match s.dist {
                SoundDist::Near => 40.0,
                SoundDist::Mid => 110.0,
                SoundDist::Far => 180.0,
                SoundDist::Unknown => 110.0,
            };
            let explained = v.iter().any(|(_, h)| h.real && adiff((h.pos[1] - pos[1]).atan2(h.pos[0] - pos[0]), s.bearing).abs() < 0.35);
            if explained {
                continue;
            }
            let x = pos[0] + r * s.bearing.cos();
            let y = pos[1] + r * s.bearing.sin();
            let q = [x, y, fin(world.terrain_z(x, y), pos[2])];
            if v.iter().any(|(_, h)| !h.real && dist2(h.pos, q) < 30.0) {
                continue;
            }
            k += 1;
            v.push((r, Th { id: -1000 - k, eye: up(q, eh), pos: q, gun, laser, lightning, k: 1.0, real: false, mz: up(q, mh) }));
        }
        v.sort_by(|a, b| a.0.total_cmp(&b.0));
        v.truncate(p.los_max_h.max(1.0) as usize);
        v.into_iter().map(|x| x.1).collect()
    }

    fn los_our(&self, obs: &Obs, d: f64) -> f64 {
        let me = &obs.me;
        let has = |k: WeaponKind| me.weapons.iter().flatten().any(|w| w.kind == k);
        let mut s = 0.0;
        if has(WeaponKind::Laser) && d <= 200.0 {
            s += 131.0 * if d >= 100.0 { 1.0 } else { 0.8 };
        }
        if has(WeaponKind::Gun) && d <= 140.0 {
            if let Some(b) = band(d) {
                s += 187.0 * GUN_P[b];
            }
        }
        s * (1.0 + 0.04 * me.cubes.max(0.0))
    }

    fn los_in_band(&self, obs: &Obs, d: f64) -> bool {
        let me = &obs.me;
        let has = |k: WeaponKind| me.weapons.iter().flatten().any(|w| w.kind == k);
        (has(WeaponKind::Laser) && (100.0..=200.0).contains(&d)) || (has(WeaponKind::Gun) && d < 140.0)
    }

    fn los_eval(&mut self, obs: &Obs, world: &World, hs: &[Th], q: V3) -> Ev {
        let t = obs.t;
        let top = obs.me.stats.height.max(1.0);
        let canopy = self.p.los_canopy > 0.5;
        let shot = self.p.los_shot > 0.5;
        let mut ev = Ev { tid: -1, near2: f64::INFINITY, ..Default::default() };
        let mut ws: Vec<(i64, f64, f64, bool)> = Vec::with_capacity(hs.len());
        for h in hs {
            if !see(world, &mut self.los.cache, canopy, shot, h, q, top, t) {
                continue;
            }
            let d = dist(h.pos, q);
            let w = w_of(h, d);
            ev.e += w;
            ev.n += 1;
            ws.push((h.id, d, w, h.real));
            if h.real {
                ev.nr += 1;
            }
            if h.id == self.los.base {
                ev.base_seen = true;
            }
            if h.id == self.los.tid {
                ev.w_pref = w;
                ev.pref_seen = true;
            }
            if h.real {
                let mut v = self.los_our(obs, d);
                if h.id == self.los.tid {
                    v *= 1.1;
                }
                if h.id == self.los.base {
                    v *= 1.0 + self.p.los_base_b;
                }
                if v > ev.v {
                    ev.v = v;
                    ev.tid = h.id;
                    ev.d_t = d;
                }
            }
        }
        let mut wt = 0.0;
        for &(id, d, w, real) in &ws {
            if id == ev.tid {
                wt = w;
            } else if real {
                ev.near2 = ev.near2.min(d);
            }
        }
        if ev.tid >= 0 {
            ev.v = self.los_our(obs, ev.d_t);
        }
        ev.e_oth = ev.e - wt;
        ev
    }

    pub(crate) fn los_decide(&mut self, obs: &Obs, world: &World, nav: &Nav, zi: &ZoneInfo, mode: &mut Mode, goal: &mut Goal, target: &mut Tgt) {
        let p = self.p.clone();
        let t = obs.t;
        let active = p.los_on > 0.5 && self.wave.kills as f64 >= p.los_from_k && !zi.urgent && !self.held(t) && (matches!(*mode, Mode::Fight | Mode::Retreat | Mode::Idle | Mode::Hunt) || (p.los_all > 0.5 && matches!(*mode, Mode::Loot | Mode::Drop)));
        let soft = !matches!(*mode, Mode::Fight | Mode::Retreat | Mode::Idle | Mode::Hunt);
        self.los.base = if let Tgt::Mech(id) = *target { id } else { -1 };
        self.los.one = false;
        let hs = if active { self.los_threats(obs, world) } else { Vec::new() };
        if hs.is_empty() {
            self.los.one_p = false;
            if self.los.st != 0 {
                if let Some(s) = self.los.spot.take() {
                    self.los.used.push((s, t));
                }
            }
            self.los.st = 0;
            self.los.hold = false;
            return;
        }
        if self.los.cache.len() > 6000 {
            self.los.cache.retain(|_, v| t - v.3 < 1.0);
        }
        self.los.used.retain(|u| t - u.1 < p.los_used_s);
        let me = &obs.me;
        let pos = me.pos;
        let hpf = frac(me.hp, me.max_hp);
        let cur = self.los_eval(obs, world, &hs, pos);
        self.los.n_bel = cur.n;
        let lea = if self.dq_on() { self.dq_lea(obs, world, nav, zi) } else { None };
        let inl = |q: V3| lea.map_or(true, |l| dist2(q, l.0) <= l.1);
        let kn = p.st_kite_n.max(0.0) as u32;
        if (soft || *mode == Mode::Hunt) && cur.n == 0 && self.los.st != 1 {
            if let Some(s) = self.los.spot.take() {
                self.los.used.push((s, t));
            }
            self.los.st = 0;
            self.los.one_p = false;
            self.los.hold = false;
            return;
        }
        let duel_ok = |b: &Brain, e: &Ev| e.tid >= 0 && b.los_in_band(obs, e.d_t) && e.e_oth <= p.los_e_ok;
        let near_real = hs.iter().filter(|h| h.real).map(|h| dist(h.pos, pos)).fold(f64::INFINITY, f64::min);

        if self.los.st == 1 {
            let tid = self.los.tid;
            let t_los = cur.pref_seen;
            if cur.e - cur.w_pref > p.los_e_ok {
                if self.los.bad_since < 0.0 {
                    self.los.bad_since = t;
                }
            } else {
                self.los.bad_since = -1.0;
            }
            if t_los {
                self.los.lost_since = -1.0;
            } else if self.los.lost_since < 0.0 {
                self.los.lost_since = t;
            }
            let second = cur.nr >= 2 && cur.near2 < 100.0;
            let leave = second || (self.los.bad_since >= 0.0 && t - self.los.bad_since > 0.3) || (self.los.lost_since >= 0.0 && t - self.los.lost_since > p.los_lost_s) || !hs.iter().any(|h| h.id == tid) || (p.st_duel_free < 0.5 && !inl(self.los.anchor));
            if leave {
                self.los.used.push((self.los.anchor, t));
                self.los.st = 2;
                self.los.spot = None;
                self.los.eval_t = -1e9;
            }
        }
        if self.los.st != 1 && duel_ok(self, &cur) && (p.st_duel_free >= 0.5 || inl(pos)) && !(self.los.st == 3 && hpf < p.los_hide_exit && near_real > 45.0) {
            self.los.st = 1;
            self.los.tid = cur.tid;
            self.los.anchor = pos;
            self.los.bad_since = -1.0;
            self.los.lost_since = -1.0;
            if let Some(s) = self.los.spot.take() {
                if dist(s, pos) > p.los_used_r {
                    self.los.used.push((s, t));
                }
            }
        }
        if self.los.st == 1 {
            self.los.one = true;
            self.los.hold = false;
            *mode = Mode::Fight;
            *target = Tgt::Mech(self.los.tid);
            let tp = hs.iter().find(|h| h.id == self.los.tid).map(|h| h.pos);
            *goal = match tp {
                Some(tp) if dist2(pos, self.los.anchor) <= p.los_anchor => Goal::Range { pos: tp, pref: dist2(tp, self.los.anchor) },
                _ => Goal::Nav { pos: self.los.anchor, arrive: p.los_anchor * 0.5 },
            };
            return;
        }
        if self.los.st == 3 && (hpf >= p.los_hide_exit || near_real < 45.0) {
            self.los.st = 2;
            self.los.eval_t = -1e9;
        }
        if self.los.st == 0 {
            self.los.st = 2;
        }
        let spot_bad = match self.los.spot {
            None => true,
            Some(s) => {
                let (zc, zr) = zone_at(&obs.zone, t, t + p.los_zone_ahead, self.zone_b);
                dist2v(s, zc) > zr - self.los_margin(obs) * 0.5 || !inl(s)
            }
        };
        if spot_bad || t - self.los.eval_t >= p.los_eval_s {
            self.los.eval_t = t;
            self.los_plan(obs, world, nav, &hs, &cur, hpf, spot_bad, lea);
        }
        self.los.one = cur.n <= kn || self.los.one_p;
        if self.los.st == 3 {
            self.los.hold = cur.n == 0;
            *mode = Mode::Retreat;
        } else {
            self.los.hold = false;
            if cur.base_seen {
                *mode = Mode::Fight;
            } else if cur.tid >= 0 {
                *mode = Mode::Fight;
                *target = Tgt::Mech(cur.tid);
            } else if *mode != Mode::Fight {
                *mode = Mode::Retreat;
            }
        }
        if let Some(s) = self.los.spot {
            *goal = Goal::Nav { pos: s, arrive: 2.0 };
        }
    }

    pub(crate) fn los_off(&mut self, t: f64) {
        if let Some(s) = self.los.spot.take() {
            self.los.used.push((s, t));
        }
        self.los.st = 0;
        self.los.one = false;
        self.los.one_p = false;
        self.los.hold = false;
    }

    fn los_margin(&self, obs: &Obs) -> f64 {
        if obs.zone.next_radius <= 140.0 {
            self.p.los_margin3
        } else {
            self.p.los_margin
        }
    }

    fn los_plan(&mut self, obs: &Obs, world: &World, nav: &Nav, hs: &[Th], cur: &Ev, hpf: f64, spot_bad: bool, lea: Option<(V3, f64, V3)>) {
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        let pos = me.pos;
        let walk = me.stats.walk_speed.max(1.0);
        let (zc, zr) = zone_at(&obs.zone, t, t + p.los_zone_ahead, self.zone_b);
        let margin = self.los_margin(obs);
        let rings = [p.los_r1, p.los_r2, p.los_r3, p.los_r4, p.los_r5];
        let nd = (p.los_dirs as usize).clamp(4, 32);
        let used = self.los.used.clone();
        let pen = |q: V3| if used.iter().any(|u| dist2(u.0, q) < p.los_used_r) { p.los_used_pen } else { 0.0 };
        let mut pts: Vec<(V3, Ev, f64)> = Vec::new();
        let in_zone = |q: V3| dist2v(q, zc) <= zr - margin && lea.map_or(true, |l| dist2(q, l.0) <= l.1);
        if in_zone(pos) {
            pts.push((pos, *cur, cur.e));
        }
        if let Some((_, _, cq)) = lea {
            if dist2v(cq, zc) <= zr - margin {
                let ev = self.los_eval(obs, world, hs, cq);
                pts.push((cq, ev, (cur.e + ev.e) * 0.5));
            }
        }
        let mut prev: Vec<Option<f64>> = vec![None; nd];
        let mut any_duel = false;
        for &r in rings.iter().filter(|r| **r > 0.5) {
            for k in 0..nd {
                if self.spent_ms() > p.los_ms {
                    break;
                }
                let a = k as f64 * std::f64::consts::TAU / nd as f64;
                let x = pos[0] + r * a.cos();
                let y = pos[1] + r * a.sin();
                let q0 = [x, y, fin(world.floor_below(x, y, pos[2] + 3.0), pos[2])];
                let Some(q) = nav.snap(q0) else { prev[k] = None; continue };
                if dist(q, q0) > 4.0 || !q.iter().all(|v| v.is_finite()) || (q[2] - pos[2]).abs() > 3.5 || !in_zone(q) {
                    prev[k] = None;
                    continue;
                }
                let ev = self.los_eval(obs, world, hs, q);
                let mid = prev[k].unwrap_or((cur.e + ev.e) * 0.5);
                prev[k] = Some(ev.e);
                pts.push((q, ev, mid));
            }
        }
        if let Some(s) = self.los.spot {
            if !spot_bad && self.spent_ms() <= p.los_ms + 2.0 {
                let ev = self.los_eval(obs, world, hs, s);
                pts.push((s, ev, (cur.e + ev.e) * 0.5));
            }
        }
        let kn = p.st_kite_n.max(0.0) as u32;
        self.los.one_p = pts.iter().any(|x| x.1.n <= kn);
        for (_, ev, _) in &pts {
            if ev.tid >= 0 && self.los_in_band(obs, ev.d_t) && ev.e_oth <= p.los_e_ok {
                any_duel = true;
            }
        }
        if self.los.st == 2 && !any_duel && hpf < p.los_hide_hp {
            self.los.st = 3;
        }
        let hide = self.los.st == 3;
        let score = |q: V3, ev: &Ev, mid: f64| -> f64 {
            let tr = dist(q, pos) / walk;
            if hide {
                -ev.e - 0.05 * dist(q, pos) - 0.3 * tr * mid
            } else {
                ev.v - p.los_k_e * ev.e - p.los_k_path * tr * mid / 100.0 - pen(q)
            }
        };
        let mut best: Option<(f64, V3)> = None;
        let mut cur_s: Option<f64> = None;
        for (q, ev, mid) in &pts {
            let s = score(*q, ev, *mid);
            if let Some(sp) = self.los.spot {
                if dist(*q, sp) < 1.0 {
                    cur_s = Some(cur_s.map_or(s, |c: f64| c.max(s)));
                }
            }
            if best.map_or(true, |b| s > b.0) {
                best = Some((s, *q));
            }
        }
        let Some((bs, bq)) = best else { return };
        let take = match (self.los.spot, cur_s) {
            (None, _) | (_, None) => true,
            (Some(_), Some(c)) => spot_bad || bs > c + p.los_replan * c.abs().max(10.0),
        };
        if take {
            if let Some(old) = self.los.spot {
                if dist(old, bq) > 1.0 {
                    self.los.used.push((old, t));
                    self.los.replans += 1;
                }
            }
            self.los.spot = Some(bq);
        }
    }
}
