use super::math::*;
use super::{Brain, Goal, Mode, Tgt};
use crate::nav::Nav;
use crate::proto::{ActorKind, Obs, SoundDist, WeaponKind};
use crate::world::World;

static TAB: &[u8] = include_bytes!("rat.bin");
const NX: i64 = 268;
const NY: i64 = 182;
const OX: f64 = -513.0;
const OY: f64 = -334.0;
const ST: f64 = 4.0;

#[derive(Clone, Debug, Default)]
pub(crate) struct Rat {
    pub hide: Option<(V3, f64)>,
    pub next_t: f64,
    pub fight_until: f64,
    pub fought: bool,
    pub bans: Vec<(V3, f64)>,
    pub ctl: bool,
    pub ended: bool,
    pub quiet: bool,
    pub at_hide: bool,
    pub gear: bool,
    pub log: Option<bool>,
    pub dmg_logged: bool,
    pub hide_s: f64,
    pub ctl_s: f64,
}

fn cell(x: f64, y: f64) -> Option<(f64, f64)> {
    let i = ((x - OX) / ST).round() as i64;
    let j = ((y - OY) / ST).round() as i64;
    if i < 0 || j < 0 || i >= NX || j >= NY {
        return None;
    }
    let k = ((j * NX + i) * 2) as usize;
    let v = *TAB.get(k)?;
    if v == 255 {
        return None;
    }
    let yaw = (*TAB.get(k + 1)? as i8) as f64 / 40.0;
    let a = v as f64 / 255.0;
    Some((125.664 * a * a, yaw))
}

fn expo(x: f64, y: f64) -> f64 {
    cell(x, y).map_or(60.0, |c| c.0)
}

impl Brain {
    fn rat_sound_pos(&self, obs: &Obs, b: f64, d: SoundDist) -> V3 {
        let r = match d {
            SoundDist::Near => 35.0,
            SoundDist::Mid => 110.0,
            _ => 240.0,
        };
        let p = obs.me.pos;
        [p[0] + r * b.cos(), p[1] + r * b.sin(), p[2]]
    }

    fn rat_choose(&mut self, obs: &Obs, world: &World, nav: &Nav) {
        let p = self.p.clone();
        let t = obs.t;
        let pos = obs.me.pos;
        let z = &obs.zone;
        let nr = z.next_radius.max(0.0);
        let margin = p.rat_margin.min(nr * 0.35);
        let cr = z.radius.max(0.0);
        let mechs: Vec<V3> = self.mem.tracks.iter().filter(|tr| tr.kind == ActorKind::Mech && t - tr.last_seen < 6.0).map(|tr| tr.pos_at(t)).collect();
        let noise: Vec<V3> = self.mem.sounds.iter().filter(|s| s.kind != "step" && s.kind != "boost" && s.kind != "jet" && t - s.t < 6.0).map(|s| self.rat_sound_pos(obs, s.bearing, s.dist)).collect();
        self.rat.bans.retain(|b| b.1 > t);
        let cur = self.rat.hide.map(|h| h.0);
        let rs = p.rat_search;
        let (ci, cj) = (((pos[0] - OX) / ST).round() as i64, ((pos[1] - OY) / ST).round() as i64);
        let n = (rs / ST).ceil() as i64;
        let mut cands: Vec<(f64, f64, f64, f64)> = Vec::new();
        let mut j = cj - n;
        while j <= cj + n {
            let mut i = ci - n;
            while i <= ci + n {
                let x = OX + ST * i as f64;
                let y = OY + ST * j as f64;
                i += 2;
                let dh = (x - pos[0]).hypot(y - pos[1]);
                if dh > rs {
                    continue;
                }
                let Some((a, yaw)) = cell(x, y) else { continue };
                let q = [x, y, pos[2]];
                if dist2v(q, z.next_center) > nr - margin || dist2v(q, z.center) > cr - 6.0 {
                    continue;
                }
                if self.fz.rec && dist2(q, self.fz.rec_from) < p.fz_move {
                    continue;
                }
                let mut s = a + p.rat_w_d * dh / 100.0;
                let dc = dist2v(q, z.next_center);
                if nr > 1.0 {
                    s += p.rat_w_c * (1.0 - dc / (0.5 * nr)).max(0.0);
                }
                for m in &mechs {
                    let d = dist2(*m, q);
                    if d < 110.0 {
                        s += 15.0 * (1.0 - d / 110.0);
                    }
                }
                for m in &noise {
                    let d = dist2(*m, q);
                    if d < 80.0 {
                        s += 8.0 * (1.0 - d / 80.0);
                    }
                }
                for b in &self.rat.bans {
                    if dist2(b.0, q) < 35.0 {
                        s += 40.0;
                    }
                }
                if let Some(c) = cur {
                    if dist2(c, q) < 6.0 {
                        s -= p.rat_hyst;
                    }
                }
                cands.push((s, x, y, yaw));
            }
            j += 2;
        }
        cands.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
        let mut best: Option<(f64, V3, f64)> = None;
        for c in cands.iter().take(14) {
            let Some(nd) = nav.snap([c.1, c.2, pos[2] + 2.0]) else { continue };
            if (nd[0] - c.1).hypot(nd[1] - c.2) > 3.5 || nav.node_roof(nav.snap_node(nd).unwrap_or(0)) {
                continue;
            }
            let mut s = c.0;
            let k = (dist2(pos, nd) / 10.0).ceil().clamp(1.0, 30.0) as usize;
            let mut acc = 0.0;
            for u in 1..=k {
                let f = u as f64 / k as f64;
                acc += expo(pos[0] + (nd[0] - pos[0]) * f, pos[1] + (nd[1] - pos[1]) * f);
            }
            s += p.rat_w_path * acc / k as f64;
            let top = up(nd, self.cfg.mech.height * 0.9);
            for m in &mechs {
                if dist(*m, nd) < 210.0 && world.sight(up(*m, self.cfg.mech.eye_height), top) {
                    s += 25.0;
                }
            }
            if best.map_or(true, |b| s < b.0) {
                best = Some((s, nd, c.3));
            }
        }
        self.rat.hide = best.map(|b| (b.1, b.2));
    }

    fn rat_log(&mut self, obs: &Obs) {
        let on = self.p.rat_log > 0.5 && *self.rat.log.get_or_insert_with(|| std::env::var_os("RAT_LOG").is_some());
        if !on {
            return;
        }
        if self.rat.ctl {
            self.rat.ctl_s += 0.1;
            if self.rat.at_hide {
                self.rat.hide_s += 0.1;
            }
        }
        if !self.rat.dmg_logged && self.mem.tracks.iter().any(|tr| tr.dmg_to_us > 0.0) {
            self.rat.dmg_logged = true;
            eprintln!("RATDMG t={:.1}", self.mem.last_damage_t);
        }
        if obs.tick % 50 == 0 {
            eprintln!("RATST t={:.1} ctl={:.1} hide={:.1} ffa={} h={:?} fu={:.1} ld={:.1} inz={} ms={:.1} pos={:.0},{:.0} q={} g={} mode={:?} zr={:.0}", obs.t, self.rat.ctl_s, self.rat.hide_s, self.ffa.on as u8, self.rat.hide, self.rat.fight_until, self.mem.last_damage_t, obs.me.in_zone, self.spent_ms(), obs.me.pos[0], obs.me.pos[1], self.rat.quiet as u8, self.rat.gear as u8, self.mode, obs.zone.next_radius);
        }
    }

    pub(crate) fn rat_pre(&mut self, obs: &Obs, world: &World, nav: &Nav, unreach: bool) -> bool {
        self.rat_log(obs);
        let p = self.p.clone();
        self.rat.ctl = false;
        let fzm = self.fz_hide(obs);
        if !fzm && (p.rat_on <= 0.5 || !self.ffa.on || self.ffa.on_t > p.rat_on_t || self.rat.ended) {
            return false;
        }
        let t = obs.t;
        let me = &obs.me;
        if !fzm && (p.rat_end_alive > 0.0 && obs.alive as f64 <= p.rat_end_alive) || (p.rat_end_r > 0.0 && obs.zone.radius <= p.rat_end_r) {
            if p.rat_end_fight > 0.5 {
                self.rat.ended = true;
                return false;
            }
        }
        if !me.in_zone {
            self.rat.hide = None;
            return false;
        }
        let pos = me.pos;
        let mut close = false;
        let mut near60 = false;
        let mut near150 = false;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech {
                continue;
            }
            let d = dist(tr.pos_at(t), pos);
            if t - tr.last_seen < 0.6 && d < p.rat_close {
                close = true;
            }
            if t - tr.last_seen < 5.0 && d < 60.0 {
                near60 = true;
            }
            if t - tr.last_seen < 5.0 && d < 150.0 {
                near150 = true;
            }
        }
        if self.mem.sounds.iter().any(|s| t - s.t < 5.0 && s.dist == SoundDist::Near) {
            near60 = true;
        }
        let hit = t - self.mem.last_damage_t < 1.5;
        if hit || (close && p.rat_silent <= 0.5 && !fzm) {
            self.rat.fight_until = t + p.rat_fight_s;
            self.rat.fought = true;
        }
        if t < self.rat.fight_until {
            return false;
        }
        if self.rat.fought {
            self.rat.fought = false;
            if let Some(h) = self.rat.hide {
                self.rat.bans.push((h.0, t + 60.0));
            }
            self.rat.hide = None;
            self.rat.next_t = 0.0;
        }
        if unreach {
            if let Some(h) = self.rat.hide {
                self.rat.bans.push((h.0, t + 90.0));
            }
            self.rat.next_t = 0.0;
        }
        let need = self.rat.hide.map_or(true, |h| dist2v(h.0, obs.zone.next_center) > obs.zone.next_radius - 3.0);
        if need || t >= self.rat.next_t {
            if self.spent_ms() < 6.0 {
                self.rat_choose(obs, world, nav);
                self.rat.next_t = t + p.rat_every;
            }
        }
        let Some((h, _)) = self.rat.hide else { return false };
        let mut goal = h;
        self.rat.gear = false;
        if !near150 && p.rat_gear_r > 0.0 {
            let has_laser = me.weapons.iter().flatten().any(|w| w.kind == WeaponKind::Laser);
            let mut g: Option<(f64, V3)> = None;
            if !has_laser {
                for it in &self.mem.pickups {
                    let d = dist(it.pos, pos);
                    if it.kind == WeaponKind::Laser && d < p.rat_gear_r && d > 1.5 && t - it.last_seen < 3.0 && !self.mem.blacklisted(it.id, t) && expo(it.pos[0], it.pos[1]) < p.rat_gear_expo && g.map_or(true, |x| d < x.0) {
                        g = Some((d, it.pos));
                    }
                }
            }
            for it in &self.mem.cubes {
                let d = dist(it.pos, pos);
                if d < p.rat_gear_r * 0.5 && d > 1.5 && t - it.last_seen < 3.0 && !self.mem.blacklisted(it.id, t) && expo(it.pos[0], it.pos[1]) < p.rat_gear_expo && g.map_or(true, |x| d < x.0) {
                    g = Some((d, it.pos));
                }
            }
            if let Some((_, q)) = g {
                goal = q;
                self.rat.gear = true;
            }
        }
        self.mode = Mode::Idle;
        self.target = Tgt::None;
        self.goal_id = -1;
        self.goal = Goal::Nav { pos: goal, arrive: if self.rat.gear { 0.8 } else { 1.5 } };
        self.rat.quiet = near60;
        self.rat.at_hide = !self.rat.gear && dist2(pos, h) < 2.5;
        self.rat.ctl = true;
        true
    }

    pub(crate) fn rat_post(&mut self, obs: &Obs, aim: &mut V2, fire: &mut [bool; 2], dir: &mut V2, boost: &mut bool, jump: &mut bool) {
        if !self.rat.ctl {
            return;
        }
        *fire = [false, false];
        let me = &obs.me;
        if self.rat.at_hide {
            *dir = [0.0, 0.0];
            *boost = false;
            *jump = false;
            let yaw = self.rat.hide.and_then(|h| cell(h.0[0], h.0[1])).map_or(me.aim[0], |c| c.1);
            *aim = [yaw, 0.0];
            return;
        }
        if self.rat.quiet {
            let walk = me.stats.walk_speed.max(1.0);
            let k = (self.cfg.sound.step_speed * 0.9 / walk).clamp(0.2, 1.0);
            *dir = [dir[0] * k, dir[1] * k];
            *boost = false;
            *jump = false;
        } else if self.jet.is_none() {
            *boost = false;
        }
        let l = dir[0].hypot(dir[1]);
        if l > 0.1 {
            *aim = [dir[1].atan2(dir[0]), 0.0];
        }
    }
}
