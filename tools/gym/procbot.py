"""Run an external bot (any language) as a subprocess speaking mechfight/1 on stdin/stdout.

Lockstep like the real server: begin(obs) writes one obs line, collect() waits for the action whose
tick matches (stale lines are dropped).  Never trust the child's stdout: non-JSON lines are ignored.
"""
import json
import os
import select
import subprocess
import time

TIMEOUT = float(os.environ.get("GYM_TICK_TIMEOUT", "1.0"))  # generous: the gym has no 50 ms CPU model


class ProcBot:
    def __init__(self, cmd, cwd, hello, env=None, name="proc", errlog=None):
        self.name = name
        self.last_ms = 0.0
        self.misses = 0
        self.buf = b""
        e = dict(os.environ)
        e.update(env or {})
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=open(errlog, "ab") if errlog else subprocess.DEVNULL, env=e, bufsize=0)
        self.fd = self.p.stdout.fileno()
        self._send(hello)
        t0 = time.time()
        while True:
            msg = self._readline(20.0 - (time.time() - t0))
            if msg is None:
                raise RuntimeError("%s: no ready within 20 s" % name)
            if msg.get("type") == "ready":
                break

    def _send(self, obj):
        try:
            self.p.stdin.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
        except (BrokenPipeError, OSError):
            pass

    def _readline(self, timeout):
        end = time.time() + timeout
        while True:
            i = self.buf.find(b"\n")
            if i >= 0:
                line, self.buf = self.buf[:i], self.buf[i + 1:]
                try:
                    m = json.loads(line)
                    if isinstance(m, dict):
                        return m
                except ValueError:
                    pass
                continue
            rem = end - time.time()
            if rem <= 0:
                return None
            r, _, _ = select.select([self.fd], [], [], rem)
            if not r:
                return None
            chunk = os.read(self.fd, 1 << 16)
            if not chunk:
                return None
            self.buf += chunk

    def begin(self, obs):
        self.tick = obs["tick"]
        self.t0 = time.perf_counter()
        self._send(obs)

    def collect(self):
        end = time.time() + TIMEOUT
        while True:
            m = self._readline(max(0.0, end - time.time()))
            if m is None:
                self.misses += 1
                self.last_ms = TIMEOUT * 1000
                return {}
            if m.get("tick") == self.tick and "type" not in m:
                self.last_ms = (time.perf_counter() - self.t0) * 1000
                return m

    def close(self):
        try:
            self._send({"type": "end"})
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=1)
        except Exception:
            self.p.kill()
