"""Checks I ran before submitting. Run after run.py: py eval/check.py"""
import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cost_watch.notes import ALL_ROUTES, load_notes  # noqa: E402

DATA = Path("data")
OUTPUT = Path("output/flagged_routes.csv")
LABELS = Path("eval/labels.csv")


def read_sample():
    """The sample's last row has an unquoted comma inside `reason`, so glue any extra fields back on."""
    with open(DATA / "sample_output_format_v2.csv", newline="", encoding="utf-8") as f:
        header, *rows = list(csv.reader(f))
    n = len(header)
    rows = [r[:n - 1] + [",".join(r[n - 1:])] for r in rows]
    return pd.DataFrame(rows, columns=header)


def check_numbers_match_sample(out):
    """The 3 rows in FreightTiger's sample are known-good numbers; ours must agree."""
    sample = read_sample().replace("", pd.NA)
    problems = []
    for s in sample.itertuples():
        mine = out[(out.route == s.route) & (out.week_of == s.week_of)]
        if mine.empty:
            problems.append(f"{s.route} {s.week_of}: sample row not flagged by us")
            continue
        m = mine.iloc[0]
        for col in ["cost_per_tonne_km", "vs_own_history", "vs_similar_routes", "flagged", "matched_note_id"]:
            if str(getattr(s, col)) != str(m[col]):
                problems.append(f"{s.route} {s.week_of} {col}: sample={getattr(s, col)!r} ours={m[col]!r}")
    return problems


def check_columns(out):
    expected = list(read_sample().columns)
    return [] if list(out.columns) == expected else [f"columns {list(out.columns)} != {expected}"]


def check_citations_are_grounded(out, notes):
    """Every justified row must cite a real note for that route (or all routes) and that week."""
    problems = []
    for row in out[out.matched_note_id.notna()].itertuples():
        note = notes[notes.note_id == row.matched_note_id]
        if note.empty:
            problems.append(f"{row.route} {row.week_of}: cites unknown note {row.matched_note_id}")
            continue
        note = note.iloc[0]
        if note.applies_to not in (row.route, ALL_ROUTES):
            problems.append(f"{row.route} {row.week_of}: {note.note_id} is for {note.applies_to}")
        week = pd.Timestamp(row.week_of)
        if not note.note_week <= week <= note.covers_until:
            problems.append(f"{row.route} {row.week_of}: {note.note_id} is outside its time window")
        if row.flagged != "No (justified)":
            problems.append(f"{row.route} {row.week_of}: has a note id but flagged={row.flagged}")
    return problems


def check_against_labels(out):
    """Hand-labelled expected verdict for each flagged week. A wrong 'justified' counts as fabricated."""
    labels = pd.read_csv(LABELS, dtype=str).fillna("")
    merged = labels.merge(out.fillna(""), on=["route", "week_of"], how="left", suffixes=("_label", ""))
    problems = []
    for r in merged.itertuples():
        if r.matched_note_id != r.expected_note_id:
            kind = "FABRICATED" if r.matched_note_id and r.matched_note_id != r.expected_note_id else "missed"
            problems.append(f"{kind}: {r.route} {r.week_of} expected {r.expected_note_id or 'none'} "
                            f"got {r.matched_note_id or 'none'}")
    correct = len(merged) - len(problems)
    print(f"  verdicts matching labels: {correct}/{len(merged)}")
    return problems


def main():
    out = pd.read_csv(OUTPUT, dtype={"matched_note_id": str})
    out["cost_per_tonne_km"] = out["cost_per_tonne_km"].map(lambda x: f"{x:.2f}")
    notes = load_notes(DATA / "context_notes.csv")

    checks = {"output columns match the contract": check_columns(out),
              "numbers match FreightTiger's sample rows": check_numbers_match_sample(out),
              "every citation is the right route and time": check_citations_are_grounded(out, notes)}
    if LABELS.exists():
        checks["verdicts match hand labels"] = check_against_labels(out)

    failed = False
    for name, problems in checks.items():
        print(f"[{'PASS' if not problems else 'FAIL'}] {name}")
        for p in problems:
            print("   -", p)
        failed |= bool(problems)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
