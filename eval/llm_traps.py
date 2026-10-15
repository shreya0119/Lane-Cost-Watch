"""Does the LLM judge read every note correctly, including the traps? Run: py eval/llm_traps.py [--live]

Each note is shown to the judge as if a matching route had a 6% rise in the note's own week,
so only the note's meaning decides the answer. Labels in eval/note_labels.csv were made by hand.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cost_watch.llm import CachedLLM  # noqa: E402
from cost_watch.notes import ALL_ROUTES, load_notes  # noqa: E402
from cost_watch.verdicts import SYSTEM_PROMPT, _user_prompt  # noqa: E402


def main():
    llm = CachedLLM("cache/llm_cache.json", live="--live" in sys.argv)
    notes = load_notes("data/context_notes.csv")
    labels = pd.read_csv("eval/note_labels.csv").set_index("note_id")["explains_rise"]

    wrong = 0
    for note in notes.itertuples():
        route = "Mumbai-Pune" if note.applies_to == ALL_ROUTES else note.applies_to
        row = SimpleNamespace(route=route, week_of=note.note_week, vs_own_pct=6.0)
        answer = llm.ask_json(SYSTEM_PROMPT, _user_prompt(row, note))
        evidence = str(answer.get("evidence", "")).strip()
        said_yes = answer.get("explains_rise") is True and evidence.rstrip(".") in note.note
        ok = said_yes == bool(labels[note.note_id])
        wrong += not ok
        print(f"[{'ok ' if ok else 'BAD'}] {note.note_id} label={labels[note.note_id]!s:5} judge={said_yes!s:5}")
    llm.save()
    print(f"{len(notes) - wrong}/{len(notes)} notes judged as labelled; {llm.stats}")
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
