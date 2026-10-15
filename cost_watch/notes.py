"""Stage C, part 1: the hard guard. Only notes for the right route and the right weeks get past here."""
import re

import pandas as pd

ALL_ROUTES = "All Routes"
NOTE_WINDOW_WEEKS = 4  # without a stated end date, a note covers its own week and the 3 after


def _stated_end(note_text, note_date):
    """End date the note states itself, e.g. 'from Feb 24 to Mar 8' -> Mar 8 of the note's year."""
    match = re.search(r"from \w{3} \d{1,2} to (\w{3} \d{1,2})", note_text)
    if not match:
        return pd.NaT
    return pd.to_datetime(f"{match.group(1)} {note_date.year}", format="%b %d %Y")


def load_notes(path):
    notes = pd.read_csv(path, parse_dates=["date"])
    notes["note_week"] = notes["date"] - pd.to_timedelta(notes["date"].dt.weekday, unit="D")
    stated_end = pd.Series([_stated_end(n, d) for n, d in zip(notes["note"], notes["date"])], index=notes.index)
    default_end = notes["note_week"] + pd.Timedelta(weeks=NOTE_WINDOW_WEEKS) - pd.Timedelta(days=1)
    notes["covers_until"] = stated_end.fillna(default_end)
    return notes


def candidate_notes(notes, route, week_of):
    """Notes that apply to this route (or all routes) and whose window overlaps this week.

    A note never explains a week before it was written (that would be hindsight),
    and a note with a stated end date never explains a week that starts after it.
    """
    right_route = notes["applies_to"].isin([route, ALL_ROUTES])
    right_time = (week_of >= notes["note_week"]) & (week_of <= notes["covers_until"])
    # closest note first, so the verdict is the same on every run
    return notes[right_route & right_time].sort_values(["date", "note_id"], ascending=[False, True])
