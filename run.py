"""Run the whole pipeline: shipments -> weekly rates -> flags -> note check -> output CSV."""
import argparse
import json

import pandas as pd

from cost_watch.flags import add_flags
from cost_watch.llm import MODEL, CachedLLM
from cost_watch.metrics import add_baselines, check_no_week_gaps, load_shipments, weekly_costs
from cost_watch.notes import load_notes
from cost_watch.verdicts import judge, reason_text

OUTPUT_COLUMNS = ["route", "week_of", "cost_per_tonne_km", "vs_own_history", "vs_similar_routes",
                  "flagged", "matched_note_id", "reason"]


def build_report(shipments_path, notes_path, llm):
    weekly = weekly_costs(load_shipments(shipments_path))
    check_no_week_gaps(weekly)
    weeks = add_flags(add_baselines(weekly))
    notes = load_notes(notes_path)

    rows = []
    for row in weeks[weeks["is_flagged"]].itertuples():
        note_id, note, rejected = judge(row, notes, llm)
        rows.append({
            "route": row.route,
            "week_of": row.week_of.date().isoformat(),
            "cost_per_tonne_km": round(row.cost_per_tonne_km, 2),
            "vs_own_history": f"{row.vs_own_pct:+.1f}% vs this route's past average",
            "vs_similar_routes": f"{row.vs_peer_pct:+.1f}% vs similar-length routes this week",
            "flagged": "No (justified)" if note_id else "Yes",
            "matched_note_id": note_id,
            "reason": reason_text(note, rejected),
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shipments", default="data/shipment_records.csv")
    parser.add_argument("--notes", default="data/context_notes.csv")
    parser.add_argument("--out", default="output/flagged_routes.csv")
    parser.add_argument("--cache", default="cache/llm_cache.json")
    parser.add_argument("--live", action="store_true", help="ignore cached answers and ask the model again")
    args = parser.parse_args()

    llm = CachedLLM(args.cache, live=args.live)
    report = build_report(args.shipments, args.notes, llm)
    llm.save()

    pd.io.common.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.out, index=False)
    print(f"{len(report)} flagged weeks written to {args.out}")
    print(json.dumps({"model": MODEL, "live": args.live, **llm.stats}))


if __name__ == "__main__":
    main()
