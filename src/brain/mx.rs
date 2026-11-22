use super::math::*;
use super::memory::Track;
use super::Brain;
use crate::proto::{ActorKind, Obs, WeaponKind};
use crate::world::World;

impl Brain {
    pub(crate) fn mx_two(&self, obs: &Obs, world: &World, tgt: Option<&Track>) -> bool {
        let p = &self.p;
        if p.mx_two <= 0.5 {
            return false;
        }
        let t = obs.t;
        let pos = obs.me.pos;
        if frac(obs.me.hp, obs.me.max_hp) > p.mx_two_hp {
            return false;
        }
        if p.mx_two_nl > 0.5 && obs.me.weapons.iter().flatten().any(|w| w.kind == WeaponKind::Laser) {
            return false;
        }
        if let Some(tr) = tgt {
            if frac(tr.hp, tr.max_hp) < p.mx_two_finish && dist(tr.pos_at(t), pos) < 120.0 && t - tr.last_seen < 0.5 {
                return false;
            }
        }
        let me_c = up(pos, obs.me.stats.height * 0.6);
        let mut n = 0;
        for tr in &self.mem.tracks {
            if tr.kind != ActorKind::Mech || t - tr.last_seen > 1.0 {
                continue;
            }
            let tp = tr.pos_at(t);
            let d = dist(tp, pos);
            if d > p.mx_two_r {
                continue;
            }
            let dangerous = tr.has(WeaponKind::Laser) || t - tr.last_dmg_t < 3.0;
            if !dangerous {
                continue;
            }
            if world.sight(up(tp, self.cfg.mech.eye_height), me_c) {
                n += 1;
            }
        }
        n as f64 >= p.mx_two_n
    }

    pub(crate) fn mx_allow(&self, obs: &Obs, tr: &Track, attacker: bool) -> bool {
        let p = &self.p;
        if attacker {
            return true;
        }
        let tf = frac(tr.hp, tr.max_hp);
        if p.mx_end_alive > 0.0 && (obs.alive as f64) <= p.mx_end_alive && tf > p.mx_end_hp {
            return false;
        }
        if p.mx_quiet_t > 0.0 && obs.t < p.mx_quiet_t && tf > p.mx_end_hp && !obs.me.weapons.iter().flatten().any(|w| w.kind == WeaponKind::Laser) {
            return false;
        }
        true
    }

    pub(crate) fn mx_bonus(&self, obs: &Obs, tr: &Track) -> f64 {
        let p = &self.p;
        if p.mx_third <= 0.0 {
            return 0.0;
        }
        if obs.t - self.ffa.foreign_t(tr.id) < 3.0 {
            p.mx_third * (1.5 - frac(tr.hp, tr.max_hp))
        } else {
            0.0
        }
    }
}
