"""recursive-builders: mechfight/1 bot. Policy (policy.py) + Nav (nav.py); degrades to straight-line if Nav is missing."""
import sys
import mechfight as mf

try:
    from nav import Nav
except Exception as e:  # nav is optional at runtime
    print("nav import failed:", repr(e), file=sys.stderr, flush=True)
    Nav = None
from policy import Policy


class Bot:
    name = "recursive-builders"

    def __init__(self, hello: mf.Hello):
        nav = None
        if Nav is not None:
            try:
                nav = Nav(hello["map"]["dir"], hello.get("config"))
            except Exception as e:
                print("nav init failed:", repr(e), file=sys.stderr, flush=True)
        self.policy = Policy(hello, nav)

    def act(self, obs: mf.Observation) -> mf.Action:
        return self.policy.act(obs)


mf.run(Bot)
