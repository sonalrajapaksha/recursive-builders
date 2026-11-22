use super::aim::FireOut;
use super::math::*;
use super::memory::Track;
use super::plan::MoveOut;
use super::strategy::ZoneInfo;
use super::{Brain, Goal, Mode, Tgt};
use crate::nav::Nav;
use crate::proto::{ActorKind, BeamKind, Event, Obs, SoundDist, WeaponKind};
use crate::world::World;

#[derive(Clone, Debug, Default)]
pub(crate) struct Fz4 {
    pub on: bool,
    pub on_t: f64,
    pub why: u8,
    alive0: i64,
    kills: i64,
    excused: i64,
    used: Vec<i64>,
    pend_t: f64,
    hits: Vec<(i64, f64)>,
    last: Vec<(i64, f64, f64, f64)>,
    pub spawn: V3,
    pub contact: bool,
    pub spot: Option<V3>,
    spot_nr: f64,
    pub ans: Option<(i64, f64, u32)>,
    expo_los: bool,
    pub mf: Option<(i64, f64)>,
    pub moved: bool,
    ls_cd: f64,
    pub grp: Option<usize>,
    slow_t: f64,
    bad: Vec<V3>,
    bad_nr: f64,
    pub st: [f64; 8],
    hurt: Vec<i64>,
    pub open_ok: bool,
}

static T0: std::sync::OnceLock<f64> = std::sync::OnceLock::new();

pub(crate) fn open_gate(p: &super::Params) -> bool {
    if p.fz4_o_from <= 0.0 {
        return true;
    }
    let now = if p.fz4_o_now > 0.0 {
        p.fz4_o_now
    } else {
        *T0.get_or_init(|| std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs() as f64).unwrap_or(0.0))
    };
    now >= p.fz4_o_from
}

impl Fz4 {
    pub(crate) fn with_gate(open_ok: bool) -> Fz4 {
        Fz4 { open_ok, ..Default::default() }
    }
}

impl Brain {
    pub(crate) fn fz4_scan(&self) -> f64 {
        if let Some(g) = self.fz4.grp {
            if let Some(v) = self.p.grp_scan.get(g) {
                if *v > 0.0 {
                    return *v;
                }
            }
        }
        self.p.scan_period
    }

    pub(crate) fn zone_hash(obs: &Obs) -> u64 {
        let z = &obs.zone;
        let mut h: u64 = 0xcbf2_9ce4_8422_2325;
        for v in [z.center[0], z.center[1], z.next_center[0], z.next_center[1]] {
            let q = (v * 100.0).round() as i64;
            for b in q.to_le_bytes() {
                h ^= b as u64;
                h = h.wrapping_mul(0x0100_0000_01b3);
            }
        }
        h
    }

    fn fz4_group(obs: &Obs) -> usize {
        (Self::zone_hash(obs) % 4) as usize
    }

    pub(crate) fn fz4_pa(&self, obs: &Obs) -> bool {
        let p = &self.p;
        p.fz4_hide > 0.5 && self.fz4.on && (obs.alive as f64) > p.fz4_end_alive && obs.t < p.fz4_end_t
    }

    pub(crate) fn fz4_pb(&self, obs: &Obs) -> bool {
        let p = &self.p;
        p.fz4_end > 0.5 && self.fz4.on && !((obs.alive as f64) > p.fz4_end_alive && obs.t < p.fz4_end_t)
    }

    fn fz4_set(&mut self, t: f64, why: u8) {
        if self.fz4.on || t >= self.p.fz4_det_t {
            return;
        }
        self.fz4.on = true;
        self.fz4.on_t = t;
        self.fz4.why = why;
        if std::env::var_os("FZ4_LOG").is_some() {
            eprintln!("FZ4DET seed={} t={:.1} why={}", self.ffa.seed, t, why);
        }
    }

    pub(crate) fn fz4_update(&mut self, obs: &Obs, world: &World) {
        let p = self.p.clone();
        if p.fz4_grp > 0.5 && self.fz4.grp.is_none() {
            self.fz4.grp = Some(Self::fz4_group(obs));
        }
        if p.fz4_det < 0.5 && p.fz4_open < 0.5 {
            return;
        }
        let t = obs.t;
        let me = &obs.me;
        if obs.zone.next_radius != self.fz4.bad_nr {
            self.fz4.bad_nr = obs.zone.next_radius;
            self.fz4.bad.clear();
        }
        if self.fz4.alive0 <= 0 {
            self.fz4.alive0 = obs.alive.max(1);
            self.fz4.spawn = me.pos;
            self.fz4.pend_t = -1.0;
        }
        if !self.fz4.contact && (obs.mechs.iter().any(|m| m.kind == ActorKind::Mech && m.id != me.id) || t - self.mem.last_damage_t < 0.5) {
            self.fz4.contact = true;
        }
        for ev in &obs.events {
            match ev {
                Event::Kill(_) => self.fz4.kills += 1,
                Event::Damaged(d) if p.fz4_open > 1.5 => {
                    if let Some(b) = d.by {
                        if d.weapon != "zone" && !self.fz4.hurt.contains(&b) {
                            self.fz4.hurt.push(b);
                        }
                    }
                }
                Event::Hit(h) if h.target >= 0 && h.target < 16 => {
                    if let Some(x) = self.fz4.hits.iter_mut().find(|x| x.0 == h.target) {
                        x.1 = t;
                    } else {
                        self.fz4.hits.push((h.target, t));
                    }
                }
                _ => {}
            }
        }
        if p.fz4_det > 0.5 && !self.fz4.on {
            self.fz4_beams(obs);
            let deaths = self.fz4.alive0 - obs.alive;
            self.fz4.excused = self.fz4.excused.min((deaths - self.fz4.kills).max(0));
            let mut un = deaths - self.fz4.kills - self.fz4.excused;
            while un > 0 {
                let cand = self.fz4.last.iter().find(|x| {
                    let hit = self.fz4.hits.iter().find(|h| h.0 == x.0).map_or(-1e9, |h| h.1);
                    !self.fz4.used.contains(&x.0) && t - hit < p.fz4_ex_s && x.1 < p.fz4_ex_hp && !obs.mechs.iter().any(|m| m.id == x.0)
                });
                let Some(c) = cand.map(|c| c.0) else { break };
                self.fz4.used.push(c);
                self.fz4.excused += 1;
                un -= 1;
            }
            if un > 0 {
                if self.fz4.pend_t < 0.0 {
                    self.fz4.pend_t = t;
                } else if t - self.fz4.pend_t >= p.fz4_pend_s - 1e-6 {
                    let one = t < p.fz4_d1_t && (p.fz4_d1_snd < 0.5 || self.fz4_heard(obs));
                    if (one || un >= 2) && std::env::var_os("FZ4_LOG").is_some() {
                        let ids: Vec<(i64, f64, f64)> = self.fz4.last.iter().filter(|x| !obs.mechs.iter().any(|m| m.id == x.0)).map(|x| (x.0, (x.1 * 100.0).round() / 100.0, t - self.fz4.hits.iter().find(|h| h.0 == x.0).map_or(-1e9, |h| h.1))).collect();
                        eprintln!("FZ4WHY deaths={} kills={} exc={} gone={:?}", deaths, self.fz4.kills, self.fz4.excused, ids);
                    }
                    if one || un >= 2 {
                        self.fz4_set(t, 1);
                    }
                }
            } else {
                self.fz4.pend_t = -1.0;
            }
        }
        for m in &obs.mechs {
            if m.kind != ActorKind::Mech || m.id == me.id {
                continue;
            }
            let Some(hp) = m.hp else { continue };
            let mx = m.max_hp.unwrap_or(1400.0).max(1.0);
            if let Some(x) = self.fz4.last.iter_mut().find(|x| x.0 == m.id) {
                x.1 = hp / mx;
                x.2 = hp;
                x.3 = t;
            } else {
                self.fz4.last.push((m.id, hp / mx, hp, t));
            }
        }
        self.fz4_react(obs, world);
    }

    fn fz4_heard(&self, obs: &Obs) -> bool {
        let t = obs.t;
        let me = obs.me.pos;
        let r = self.p.fz4_b_npc;
        let band = |d: SoundDist| match d {
            SoundDist::Near => (0.0, 60.0, 0),
            SoundDist::Mid => (60.0, 160.0, 1),
            _ => (160.0, 600.0, 2),
        };
        self.mem.sounds.iter().any(|s| {
            if s.kind != "death" || t - s.t > 2.0 {
                return false;
            }
            let (lo, hi, k) = band(s.dist);
            let trk = self.mem.tracks.iter().any(|tr| {
                if tr.kind != ActorKind::Npc || t - tr.last_seen > 3.0 {
                    return false;
                }
                let q = tr.pos_at(t);
                let d = dist2(q, me);
                let a = (q[1] - me[1]).atan2(q[0] - me[0]);
                adiff(a, s.bearing).abs() < 0.35f64.max(r.atan2(d.max(1.0))) && d >= lo - r && d <= hi + r
            });
            let gun = self.mem.sounds.iter().any(|n| {
                if n.kind != "npc_gun" || (s.t - n.t).abs() > 3.0 {
                    return false;
                }
                let (_, _, j) = band(n.dist);
                let tol = if k == 0 && j == 0 { 1.2 } else { 0.4 };
                (k as i32 - j as i32).abs() <= 1 && adiff(n.bearing, s.bearing).abs() < tol
            });
            !trk && !gun
        })
    }

    fn fz4_beams(&mut self, obs: &Obs) {
        let p = &self.p;
        let t = obs.t;
        let me = &obs.me;
        let mut hit = false;
        for b in &obs.beams {
            if b.by == me.id || b.by < 0 || b.by >= 16 || b.path.len() < 2 {
                continue;
            }
            if !b.path.iter().all(|q| q.iter().all(|v| v.is_finite())) || b.path.iter().any(|q| dist2(*q, me.pos) < p.fz4_b_me) {
                continue;
            }
            let pt = match b.kind {
                BeamKind::Laser => b.path[b.path.len() - 1],
                BeamKind::Lightning if p.fz4_b_lt > 0.5 => continue,
                BeamKind::Lightning => b.path[1],
                BeamKind::Unknown => continue,
            };
            let m0 = b.path[0];
            let Some(v) = obs.mechs.iter().find(|m| m.kind == ActorKind::Mech && m.id != b.by && m.id != me.id && dist2(m.pos, pt) < 4.0 && pt[2] > m.pos[2] - 1.0 && pt[2] < m.pos[2] + 11.0) else { continue };
            let a1 = (pt[1] - m0[1]).atan2(pt[0] - m0[0]);
            let a2 = (me.pos[1] - m0[1]).atan2(me.pos[0] - m0[0]);
            if adiff(a1, a2).abs() < p.fz4_b_ang {
                continue;
            }
            if obs.mechs.iter().any(|n| n.kind == ActorKind::Npc && (dist2(n.pos, v.pos) < p.fz4_b_npc || dist2(n.pos, m0) < p.fz4_b_npc)) {
                continue;
            }
            if self.fz4.hits.iter().any(|h| h.0 == v.id && t - h.1 < 0.35) {
                continue;
            }
            let Some(hp) = v.hp else { continue };
            let Some(prev) = self.fz4.last.iter().find(|x| x.0 == v.id) else { continue };
            if t - prev.3 > 0.25 || prev.2 - hp < p.fz4_b_drop {
                continue;
            }
            hit = true;
            if t < p.fz4_d1_t && std::env::var_os("FZ4_LOG").is_some() {
                eprintln!("FZ4WHY beam by={} on={} kind={:?} drop={:.0} ang={:.2} dme={:.0}", b.by, v.id, b.kind, prev.2 - hp, adiff(a1, a2).abs(), dist2(pt, me.pos));
            }
        }
        if hit && t < p.fz4_d1_t {
            self.fz4_set(t, 2);
        }
    }

    fn fz4_out(&self, obs: &Obs, tr: &Track) -> bool {
        tr.hp - obs.me.hp > self.p.fz4_out_lead || frac(obs.me.hp, obs.me.max_hp) < self.p.fz4_out_hp
    }

    fn fz4_react(&mut self, obs: &Obs, world: &World) {
        if !self.fz4_pa(obs) {
            self.fz4.ans = None;
            self.fz4.mf = None;
            return;
        }
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        let ls = me.weapons.iter().flatten().find(|w| w.kind == WeaponKind::Laser).map(|w| (w.cooldown, w.charge));
        let fired = match ls {
            Some((cd, _)) => {
                let f = cd > self.fz4.ls_cd + 0.3;
                self.fz4.ls_cd = cd;
                f
            }
            None => false,
        };
        let has_ls = ls.is_some();
        for ev in &obs.events {
            let Event::Damaged(d) = ev else { continue };
            let Some(by) = d.by else { continue };
            if by < 0 || by >= 16 {
                continue;
            }
            let t_f = self.fz4.mf.map_or(t, |f| f.1);
            let Some(tr) = self.mem.tracks.iter().find(|x| x.id == by) else {
                if self.fz4.ans.map_or(true, |r| r.0 != by) {
                    self.fz4.mf = Some((by, t_f));
                }
                continue;
            };
            if self.fz4_out(obs, tr) {
                self.fz4.mf = Some((by, t_f));
                self.fz4.ans = None;
            } else if let Some(r) = self.fz4.ans.filter(|r| r.0 == by) {
                if !has_ls {
                    self.fz4.ans = Some((by, t, r.2));
                }
            } else if self.fz4.mf.map_or(true, |f| f.0 != by) {
                self.fz4.ans = Some((by, t, 0));
                self.fz4.expo_los = false;
            }
        }
        if let Some((a, t0, n)) = self.fz4.ans {
            let mut n = n;
            if fired {
                n += 10;
            }
            if let Some(tr) = self.mem.tracks.iter().find(|x| x.id == a) {
                let los = world.sight(up(tr.pos_at(t), self.cfg.mech.eye_height), up(me.pos, me.stats.height * 0.6));
                if los && !self.fz4.expo_los && has_ls {
                    n += 1;
                }
                self.fz4.expo_los = los;
                if self.fz4_out(obs, tr) {
                    n += 100;
                }
            }
            if (has_ls && (n >= 10 || (n as f64) > p.fz4_expo)) || n >= 100 || t - t0 > p.fz4_reply_s {
                self.fz4.ans = None;
                self.fz4.mf = Some((a, t));
            } else {
                self.fz4.ans = Some((a, t0, n));
            }
        }
        if let Some((_, tf)) = self.fz4.mf {
            if t - self.mem.last_damage_t > p.fz4_flee_s && t - tf > p.fz4_flee_s {
                self.fz4.mf = None;
                self.fz4.spot = None;
                self.fz4.moved = true;
            }
        }
    }

    fn fz4_lo(&self, obs: &Obs, tr: &Track, d: f64) -> bool {
        let p = &self.p;
        let t = obs.t;
        if frac(tr.hp, tr.max_hp) >= p.fz4_steal_hp || d > p.fz4_steal_r {
            return false;
        }
        !self.mem.tracks.iter().any(|o| o.kind == ActorKind::Mech && o.id != tr.id && t - o.last_seen < 5.0 && frac(o.hp, o.max_hp) >= 0.5 && dist(o.pos_at(t), obs.me.pos) < p.fz4_steal_clear)
    }

    pub(crate) fn fz4_fire_ok(&self, obs: &Obs, tr: &Track, attacker: bool, d: f64) -> bool {
        let p = &self.p;
        if p.fz4_hide < 0.5 && p.fz4_end < 0.5 && p.fz4_open < 0.5 {
            return true;
        }
        let t = obs.t;
        if self.fz4_pa(obs) {
            if self.fz4_lo(obs, tr, d) {
                return true;
            }
            if let Some((a, _, _)) = self.fz4.ans {
                return a == tr.id;
            }
            if let Some((a, tf)) = self.fz4.mf {
                let cn = t - tf > p.fz4_corner_s && t - self.mem.last_damage_t < 1.0;
                return attacker && (cn || (a == tr.id && d < p.fz4_close_r) || frac(tr.hp, tr.max_hp) < p.fz4_steal_hp);
            }
            return attacker && d < p.fz4_close_r;
        }
        if self.fz4_pb(obs) {
            if attacker || frac(tr.hp, tr.max_hp) < p.fz4_steal_hp {
                return true;
            }
            if t >= p.fz4_fin_t && frac(obs.me.hp, obs.me.max_hp) < p.fz4_fin_hp {
                return false;
            }
            return d <= p.fz4_e_r && tr.hp <= obs.me.hp + p.fz4_e_lead;
        }
        if !self.fz4.open_ok {
        } else if p.fz4_open > 1.5 {
            if !self.fz4.on && t < p.fz4_o2_t && !attacker && tr.dmg_to_us <= 0.0 && !self.fz4.hurt.contains(&tr.id) {
                let full = tr.hp >= tr.max_hp * 0.999;
                let me = obs.me.pos;
                let brg = (me[1] - tr.pos[1]).atan2(me[0] - tr.pos[0]);
                let off = adiff(tr.aim[0], brg).abs();
                if full && d > p.fz4_o2_r && off >= p.fz4_o2_a.to_radians() && t - tr.last_seen < 0.3 {
                    return false;
                }
            }
        } else if p.fz4_open > 0.5 && !self.fz4.on && t < p.fz4_o_t && !attacker && tr.dmg_to_us <= 0.0 {
            let full = tr.hp >= tr.max_hp * 0.999;
            if full && (d > p.fz4_o_r || tr.has(WeaponKind::Laser) || tr.has(WeaponKind::Lightning)) {
                return false;
            }
        }
        true
    }

    pub(crate) fn fz4_bonus(&self, obs: &Obs, tr: &Track) -> f64 {
        if !self.fz4_pb(obs) {
            return 0.0;
        }
        100.0 * (1.0 - frac(tr.hp, tr.max_hp))
    }

    fn fz4_band(&self, t: f64) -> (f64, f64) {
        let p = &self.p;
        if t < p.fz4_b_t1 {
            (p.fz4_b1_lo, p.fz4_b1_hi)
        } else {
            (p.fz4_b2_lo, p.fz4_b2_hi)
        }
    }

    fn fz4_valid(&self, obs: &Obs, q: V3) -> bool {
        let z = &obs.zone;
        let dc = dist2v(q, z.center);
        if dc > z.radius - 20.0 {
            return false;
        }
        z.next_radius < 30.0 || dist2v(q, z.next_center) < z.next_radius - 15.0
    }

    fn fz4_hidden(&self, world: &World, q: V3, c: V2) -> f64 {
        let e = up(q, 6.0);
        let dx = c[0] - q[0];
        let dy = c[1] - q[1];
        let l = dx.hypot(dy).max(1.0);
        let mut s = 0.0;
        for r in [40.0f64, 90.0] {
            let x = q[0] + dx / l * r.min(l);
            let y = q[1] + dy / l * r.min(l);
            let g = world.floor_below(x, y, q[2] + 60.0);
            if !world.sight(e, [x, y, fin(g, q[2]) + 6.0]) {
                s += 1.0;
            }
        }
        let mut n = 0.0;
        for k in 0..8 {
            let a = k as f64 * std::f64::consts::FRAC_PI_4;
            if !world.sight(e, [q[0] + 14.0 * a.cos(), q[1] + 14.0 * a.sin(), e[2]]) {
                n += 1.0;
            }
        }
        2.0 * s + 0.5 * n
    }

    fn fz4_spot(&mut self, obs: &Obs, world: &World, nav: &Nav) -> Option<V3> {
        let t = obs.t;
        let z = &obs.zone;
        if let Some(q) = self.fz4.spot {
            if self.fz4_valid(obs, q) && (z.next_radius - self.fz4.spot_nr).abs() < 1.0 {
                return Some(q);
            }
        }
        let p = self.p.clone();
        let pos = obs.me.pos;
        let (lo, hi) = self.fz4_band(t);
        let c = z.center;
        let r = z.radius.max(1.0);
        let mechs: Vec<V3> = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 30.0).map(|tr| tr.pos_at(t.min(tr.last_seen + 1.0))).collect();
        let away: Option<V3> = self.fz4.mf.and_then(|(a, _)| self.mem.tracks.iter().find(|x| x.id == a)).map(|x| x.pos_at(t));
        let mut cands: Vec<(f64, V3)> = Vec::new();
        let walk = obs.me.stats.walk_speed.max(1.0);
        for k in 0..24 {
            let a = k as f64 * std::f64::consts::PI / 12.0;
            for f in [lo, 0.5 * (lo + hi), hi, 0.5 * lo, 0.3] {
                let x = c[0] + f * r * a.cos();
                let y = c[1] + f * r * a.sin();
                let q0 = [x, y, fin(world.floor_below(x, y, pos[2] + 40.0), pos[2])];
                let Some(ni) = nav.snap_node(q0) else { continue };
                if nav.node_roof(ni) {
                    continue;
                }
                let q = nav.node_pos(ni);
                if !q.iter().all(|v| v.is_finite()) || dist2(q, q0) > 12.0 || !self.fz4_valid(obs, q) || self.fz4.bad.iter().any(|b| dist2(*b, q) < 25.0) {
                    continue;
                }
                let fr = dist2v(q, c) / r;
                let band = if fr < lo { lo - fr } else if fr > hi { fr - hi } else { 0.0 };
                let crowd = mechs.iter().filter(|m| dist2(**m, q) < p.fz4_spread).count() as f64;
                let near = mechs.iter().map(|m| dist2(*m, q)).fold(f64::INFINITY, f64::min).min(400.0);
                let d = dist2(q, pos);
                let mut s = 1000.0 * crowd + 300.0 * band + d / walk * p.fz4_travel - 0.05 * near;
                if t < z.shrink_start && d / walk > (z.shrink_start - t) + 20.0 {
                    s += 200.0;
                }
                if let Some(fp) = away {
                    if dist2(q, fp) < 60.0 {
                        s += 500.0;
                    }
                }
                cands.push((s, q));
            }
        }
        cands.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut best: Option<(f64, V3)> = None;
        for &(s0, q) in cands.iter().take(8) {
            let mut s = s0 - 12.0 * self.fz4_hidden(world, q, c);
            if let Some(fp) = away {
                if world.sight(up(fp, self.cfg.mech.eye_height), up(q, obs.me.stats.height * 0.6)) {
                    s += 300.0;
                }
            }
            if best.map_or(true, |b| s < b.0) {
                best = Some((s, q));
            }
        }
        let q = best?.1;
        self.fz4.spot = Some(q);
        self.fz4.spot_nr = z.next_radius;
        Some(q)
    }

    fn fz4_loot_ok(&self, obs: &Obs, world: &World, q: V3, id: i64) -> bool {
        let p = &self.p;
        let t = obs.t;
        if !(5000..20000).contains(&id) {
            return false;
        }
        let d = dist(q, obs.me.pos);
        if id >= 8000 && !self.fz4.contact && dist(q, self.fz4.spawn) < p.fz4_spawn_laser && obs.pickups.iter().any(|k| k.id == id && k.kind == WeaponKind::Laser) {
            return true;
        }
        if d > p.fz4_loot_r {
            return false;
        }
        let seen = self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < p.fz4_loot_s);
        if seen {
            let e = up(q, 6.0);
            let mut n = 0;
            for k in 0..8 {
                let a = k as f64 * std::f64::consts::FRAC_PI_4;
                if !world.sight(e, [q[0] + 14.0 * a.cos(), q[1] + 14.0 * a.sin(), e[2]]) {
                    n += 1;
                }
            }
            if n < 3 {
                return false;
            }
        }
        true
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn fz4_hold(&mut self, obs: &Obs, world: &World, nav: &Nav, zi: &ZoneInfo, mode: Mode, goal: Goal, goal_id: i64, target: Tgt) -> Option<(Mode, Goal, i64, Tgt)> {
        let p = self.p.clone();
        let t = obs.t;
        if self.fz4_pb(obs) {
            if t >= p.fz4_fin_t && !matches!(mode, Mode::Retreat) {
                let z = &obs.zone;
                return Some((Mode::Zone, Goal::Field { center: z.next_center, arrive: 0.8 }, -1, target));
            }
            return None;
        }
        if !self.fz4_pa(obs) {
            return None;
        }
        self.allow_crates = false;
        if matches!(mode, Mode::Zone) {
            return None;
        }
        if self.fz4.mf.is_some() {
            if matches!(mode, Mode::Retreat) && !matches!(goal, Goal::None) {
                return Some((mode, goal, goal_id, Tgt::None));
            }
            let g = self.cover_goal(obs, world, nav, zi);
            if !matches!(g, Goal::None) {
                return Some((Mode::Retreat, g, -1, Tgt::None));
            }
        }
        if matches!(mode, Mode::Loot) && goal_id >= 0 {
            if let Goal::Nav { pos, .. } = goal {
                if self.fz4_loot_ok(obs, world, pos, goal_id) {
                    return None;
                }
            }
        }
        let tg = match self.fz4.ans {
            Some((a, _, _)) => Tgt::Mech(a),
            None => match target {
                Tgt::Mech(id) => {
                    let ok = self.mem.tracks.iter().find(|x| x.id == id).map_or(false, |tr| self.fz4_lo(obs, tr, dist(tr.pos_at(t), obs.me.pos)));
                    if ok {
                        return None;
                    }
                    Tgt::None
                }
                _ => Tgt::None,
            },
        };
        let q = self.fz4_spot(obs, world, nav)?;
        Some((Mode::Idle, Goal::Nav { pos: q, arrive: 1.5 }, -1, tg))
    }

    pub(crate) fn fz4_post(&mut self, obs: &Obs, world: &World, fc: &mut FireOut, mv: &mut MoveOut) {
        let p = self.p.clone();
        let t = obs.t;
        let me = &obs.me;
        if self.fz4_pa(obs) {
            let gun = me.weapons.iter().position(|w| w.as_ref().map_or(false, |w| w.kind == WeaponKind::Gun));
            let ls = me.weapons.iter().position(|w| w.as_ref().map_or(false, |w| w.kind == WeaponKind::Laser));
            let mor = me.weapons.iter().position(|w| w.as_ref().map_or(false, |w| w.kind == WeaponKind::Mortar));
            if let Some(m) = mor {
                fc.fire[m] = false;
            }
            if let Some((a, _, _)) = self.fz4.ans.filter(|_| ls.is_some()) {
                let close = self.mem.tracks.iter().find(|x| x.id == a).map_or(false, |tr| dist(tr.pos_at(t), me.pos) < p.fz4_close_r);
                if !close {
                    if let Some(g) = gun {
                        fc.fire[g] = false;
                    }
                }
            }
            if fc.target.is_none() {
                if let Some(g) = gun {
                    fc.fire[g] = false;
                }
                if let Some(l) = ls {
                    let ch = me.weapons[l].as_ref().map_or(0.0, |w| w.charge);
                    if ch <= 0.0 {
                        fc.fire[l] = false;
                    }
                }
            }
            let zone_push = !me.in_zone || matches!(self.mode, Mode::Zone);
            let at_spot = self.fz4.spot.map_or(false, |q| dist2(q, me.pos) < 3.0);
            let want = mv.dir[0].hypot(mv.dir[1]) > 0.3 && !at_spot;
            if !want || me.vel[0].hypot(me.vel[1]) > 2.0 {
                self.fz4.slow_t = t;
            }
            let stuck = t - self.fz4.slow_t > 1.0;
            if let (Some(q), Mode::Idle) = (self.fz4.spot, self.mode) {
                if self.goal_unreachable || t - self.fz4.slow_t > 3.0 {
                    if self.fz4.bad.len() >= 32 {
                        self.fz4.bad.remove(0);
                    }
                    self.fz4.bad.push(q);
                    self.fz4.spot = None;
                    self.fz4.slow_t = t;
                }
            }
            if !zone_push && !stuck && self.fz4.mf.is_none() {
                mv.boost = false;
            }
            if !zone_push && !stuck {
                mv.jump = false;
            }
            if stuck && std::env::var_os("FZ4_LOG").is_some() {
                self.fz4.st[7] += 1.0;
            }
            if let (Some(q), Mode::Idle) = (self.fz4.spot, self.mode) {
                if matches!(self.goal, Goal::Nav { pos, .. } if dist2(pos, q) < 0.5) && dist2(q, me.pos) < 2.5 && t - self.mem.last_damage_t > 0.5 {
                    mv.dir = [0.0, 0.0];
                    mv.boost = false;
                }
            }
            if std::env::var("FZ4_LOG").map_or(false, |v| v == "2") && obs.tick % 10 == 0 {
                let near = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 2.0).map(|tr| (tr.id, dist(tr.pos_at(t), me.pos).round(), tr.hp.round())).collect::<Vec<_>>();
                eprintln!("FZ4TR t={:.1} hp={:.0} mode={:?} pos={:.0},{:.0} spot={:?} a={:?} m={:?} fire={:?} near={:?} ld={:.1}", t, me.hp, self.mode, me.pos[0], me.pos[1], self.fz4.spot.map(|q| (q[0].round(), q[1].round())), self.fz4.ans, self.fz4.mf, fc.fire, near, self.mem.last_damage_t);
            }
            if std::env::var_os("FZ4_LOG").is_some() {
                let v = me.vel[0].hypot(me.vel[1]);
                self.fz4.st[0] += 1.0;
                if v < 1.0 {
                    self.fz4.st[1] += 1.0;
                } else if v < 6.0 {
                    self.fz4.st[2] += 1.0;
                } else {
                    self.fz4.st[3] += 1.0;
                }
                if fc.fire[0] || fc.fire[1] {
                    self.fz4.st[4] += 1.0;
                }
            }
        } else if self.fz4_pb(obs) {
            self.fz4_pc(obs, world, fc);
        }
        if std::env::var_os("FZ4_LOG").is_some() && self.fz4.on {
            if (30.0..150.0).contains(&t) {
                self.fz4.st[5] += 1.0;
                let far = !self.mem.tracks.iter().any(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 5.0 && dist2(tr.pos_at(t), me.pos) < 150.0);
                if far {
                    self.fz4.st[6] += 1.0;
                }
            }
            if obs.tick % 50 == 0 {
                eprintln!("FZ4ST seed={} t={:.0} hide={} still={} slow={} fast={} fire={} mid={} far={} maxms={:.2} stuck={}", self.ffa.seed, t, self.fz4.st[0], self.fz4.st[1], self.fz4.st[2], self.fz4.st[3], self.fz4.st[4], self.fz4.st[5], self.fz4.st[6], self.fz.max_ms, self.fz4.st[7]);
            }
        }
    }

    fn fz4_pc(&self, obs: &Obs, world: &World, fc: &mut FireOut) {
        let p = &self.p;
        let Some(ls) = obs.me.weapons.iter().position(|w| w.as_ref().map_or(false, |w| w.kind == WeaponKind::Laser)) else { return };
        let Some(w) = obs.me.weapons[ls].clone() else { return };
        if fc.target.is_some() || w.cooldown > 0.0 {
            return;
        }
        let t = obs.t;
        let pos = obs.me.pos;
        let me_c = up(pos, obs.me.stats.height * 0.6);
        let full = w.stats.charge.max(0.05);
        let cue = self.mem.sounds.iter().any(|s| t - s.t < 1.5 && matches!(s.dist, SoundDist::Near) && !matches!(s.kind.as_str(), "npc_gun" | "crate" | "death" | "drop" | "explosion"));
        let mut near = false;
        let mut come = false;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 4.0 || tr.hp > obs.me.hp + p.fz4_e_lead {
                continue;
            }
            let q = tr.pos_at(t);
            if dist(q, pos) > p.fz4_e_r + 40.0 {
                continue;
            }
            if world.sight(up(q, self.cfg.mech.eye_height), me_c) {
                return;
            }
            near = true;
            let v = tr.vel;
            if t - tr.last_seen < 1.5 && (v[0] * (pos[0] - q[0]) + v[1] * (pos[1] - q[1])) > 0.0 {
                come = true;
            }
        }
        if !near || (w.charge <= 0.0 && !cue && !come) {
            return;
        }
        fc.fire[ls] = w.charge < full + p.fz4_e_hold;
        fc.charging = fc.fire[ls] || fc.charging;
    }
}

