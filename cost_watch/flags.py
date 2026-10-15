"""Stage B: decide which route-weeks are rising in an out-of-the-ordinary way."""
import pandas as pd

from cost_watch.metrics import HISTORY_WEEKS

Z_THRESHOLD = 3.0    # "3 normal wobbles" above usual
MIN_RISE_PCT = 5.0   # ignore moves too small to matter; diesel note N003 is 5-7%

# Backstop for what z-scores miss: after a spike (or during a slow creep) the trailing
# std/mean absorb the rise, so later weeks stop looking surprising. <1% of normal weeks
# are 20%+ above their own history, <2% are 25%+ above peers.
OWN_BACKSTOP_PCT = 20.0
PEER_BACKSTOP_PCT = 25.0


def _trailing(series_by_route, stat):
    """Mean or std of up to 8 earlier weeks (current week excluded)."""
    return series_by_route.transform(
        lambda s: getattr(s.shift(1).rolling(HISTORY_WEEKS, min_periods=2), stat)()
    )


def add_flags(w):
    w = w.copy()
    by_route = w.groupby("route")

    # How surprising is this week's rate compared to the route's own recent weeks?
    own_std = _trailing(by_route["cost_per_tonne_km"], "std")
    w["z_own"] = (w["cost_per_tonne_km"] - w["own_history_avg"]) / own_std

    # Short/Long routes have a single peer, so we can't take a spread across peers.
    # Instead: is this week's gap to peers unusually large compared to this route's usual gap?
    gap_mean = _trailing(by_route["vs_peer_pct"], "mean")
    gap_std = _trailing(by_route["vs_peer_pct"], "std")
    w["z_peer"] = (w["vs_peer_pct"] - gap_mean) / gap_std

    surprising = (w["z_own"] > Z_THRESHOLD) | (w["z_peer"] > Z_THRESHOLD)
    far_above = (w["vs_own_pct"] >= OWN_BACKSTOP_PCT) | (w["vs_peer_pct"] >= PEER_BACKSTOP_PCT)
    unusual = surprising | far_above
    rising = w["vs_own_pct"] >= MIN_RISE_PCT
    w["is_flagged"] = unusual & rising
    return w
