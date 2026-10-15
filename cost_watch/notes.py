"""Stage C, part 1: the hard guard. Only notes for the right route and the right weeks get past here."""
import pandas as pd

ALL_ROUTES = "All Routes"
NOTE_WINDOW_WEEKS = 4  # a note can explain the week it was written in and the 3 weeks after


def load_notes(path):
    notes = pd.read_csv(path, parse_dates=["date"])
    notes["note_week"] = notes["date"] - pd.to_timedelta(notes["date"].dt.weekday, unit="D")
    return notes


def candidate_notes(notes, route, week_of):
    """Notes that apply to this route (or all routes) and whose window covers this week.

    A note never explains a week before it was written: that would be using hindsight.
    """
    right_route = notes["applies_to"].isin([route, ALL_ROUTES])
    weeks_after_note = (week_of - notes["note_week"]).dt.days // 7
    right_time = (weeks_after_note >= 0) & (weeks_after_note < NOTE_WINDOW_WEEKS)
    # closest note first, so the verdict is the same on every run
    return notes[right_route & right_time].sort_values(["date", "note_id"], ascending=[False, True])
