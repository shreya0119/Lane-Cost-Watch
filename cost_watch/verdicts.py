"""Stage C, part 2: the LLM reads each surviving note and says whether it explains the rise.

Code decides which notes are eligible (route, dates). The LLM only judges meaning.
The reason text is built from a template, so it can't invent anything the note doesn't say.
"""
import re

from cost_watch.notes import candidate_notes

MAX_OVER_STATED_RANGE = 1.5  # a rise above 1.5x the note's own % range is only partly explained

SYSTEM_PROMPT = """You check whether a logistics note explains a freight cost increase.
Answer true ONLY if the note says or clearly implies that transport costs went UP.
Answer false if the note says costs were not affected, stayed stable, had no rate change,
reports normal conditions or improvements, or is about routes not in scope.
Reply as JSON: {"explains_rise": true or false, "evidence": "<the exact sentence from the note you relied on>"}"""


def _user_prompt(row, note):
    return (f"Route: {row.route}\n"
            f"Week starting: {row.week_of.date()}\n"
            f"Cost per tonne-km rose {row.vs_own_pct:.1f}% vs this route's past average.\n\n"
            f"Note {note.note_id} (dated {note.date.date()}, applies to {note.applies_to}):\n{note.note}")


def stated_max_pct(text):
    """Upper end of a % range the note itself gives, e.g. 'roughly 5-7%' -> 7.0. None if no range."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*%", text)
    return float(match.group(2)) if match else None


def judge(row, notes, llm):
    """Return (matched_note_id or '', matched note, list of (note, why_rejected))."""
    rejected = []
    for note in candidate_notes(notes, row.route, row.week_of).itertuples():
        answer = llm.ask_json(SYSTEM_PROMPT, _user_prompt(row, note))
        evidence = str(answer.get("evidence", "")).strip()
        # Guardrail: the quoted evidence must really be in the note, or we don't trust the "yes".
        grounded = bool(evidence) and evidence.rstrip(".") in note.note
        if answer.get("explains_rise") is not True or not grounded:
            rejected.append((note, "does not describe a reason for a cost rise"))
            continue
        cap = stated_max_pct(note.note)
        if cap is not None and row.vs_own_pct > cap * MAX_OVER_STATED_RANGE:
            rejected.append((note, f"accounts for up to {cap:g}% but the rise was {row.vs_own_pct:.1f}%, "
                                   f"so it is only partly explained"))
            continue
        return note.note_id, note, rejected
    return "", None, rejected


def reason_text(note, rejected):
    if note is not None:
        return (f"Matches note {note.note_id} dated {note.date.date()} ({note.applies_to}): "
                f"\"{note.note}\" The cost rise has a documented explanation.")
    if rejected:
        checked = "; ".join(f"{n.note_id} ({n.date.date()}) {why}" for n, why in rejected)
        return f"Notes checked for this route and week: {checked}. No full justification found; flagged for human review."
    return ("No note covers this route and week. "
            "Cost rise looks unexplained and is worth a human review.")
