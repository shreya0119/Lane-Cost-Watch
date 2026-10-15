"""Stage A: weekly cost per tonne-km per route, plus the two comparison baselines."""
import pandas as pd

HISTORY_WEEKS = 8


def load_shipments(path):
    df = pd.read_csv(path, parse_dates=["shipment_date"])
    df["route"] = df["origin"] + "-" + df["destination"]
    # Monday of the shipment's week: pandas counts Monday as weekday 0.
    df["week_of"] = df["shipment_date"] - pd.to_timedelta(df["shipment_date"].dt.weekday, unit="D")
    df["tonne_km"] = df["quantity_tonnes"] * df["distance_km"]
    return df


def weekly_costs(shipments):
    """One row per (route, week). Rate = total cost / total tonne-km, so big loads weigh more."""
    weekly = shipments.groupby(["route", "route_type", "week_of"], as_index=False).agg(
        freight_cost_inr=("freight_cost_inr", "sum"),
        tonne_km=("tonne_km", "sum"),
        shipments=("shipment_id", "count"),
    )
    weekly["cost_per_tonne_km"] = weekly["freight_cost_inr"] / weekly["tonne_km"]
    return weekly.sort_values(["route", "week_of"]).reset_index(drop=True)


def check_no_week_gaps(weekly):
    """rolling(8) counts rows, not calendar weeks, so it is only correct if no week is missing."""
    gaps = weekly.groupby("route")["week_of"].diff().dropna()
    assert (gaps == pd.Timedelta(days=7)).all(), "a route skips a week; rolling window would be wrong"


def add_baselines(weekly):
    w = weekly.copy()
    rates = w.groupby("route")["cost_per_tonne_km"]

    # Own history: mean of up to 8 earlier weeks. shift(1) drops the current week (no look-ahead).
    w["own_history_avg"] = rates.transform(
        lambda s: s.shift(1).rolling(HISTORY_WEEKS, min_periods=1).mean()
    )
    w["history_weeks_used"] = w.groupby("route").cumcount().clip(upper=HISTORY_WEEKS)

    # Peers: same route_type, same week, this route left out -> (group sum - self) / (group size - 1).
    same_type_week = w.groupby(["route_type", "week_of"])["cost_per_tonne_km"]
    total = same_type_week.transform("sum")
    count = same_type_week.transform("count")
    w["peer_avg"] = (total - w["cost_per_tonne_km"]) / (count - 1)

    w["vs_own_pct"] = (w["cost_per_tonne_km"] / w["own_history_avg"] - 1) * 100
    w["vs_peer_pct"] = (w["cost_per_tonne_km"] / w["peer_avg"] - 1) * 100
    return w
