# Lane Cost Watch

Tracks freight cost per tonne-km on each route, week by week, flags rises that look out of the ordinary, and checks a set of context notes for a documented reason. A "justified" verdict always cites one note that applies to that route and week; everything else stays flagged for a human.

Output: [`output/flagged_routes.csv`](output/flagged_routes.csv): 21 flagged route-weeks (5 justified, 16 unexplained), in the column format of `sample_output_format_v2.csv`.

## How to run

```bash
pip install pandas
# put shipment_records.csv, context_notes.csv and sample_output_format_v2.csv in data/
python run.py              # replays saved LLM answers from cache/, no LLM needed
python eval/check.py       # correctness checks
python eval/llm_traps.py   # does the LLM read every note correctly?
```

`python run.py --live` asks the model again instead of replaying. It needs [Ollama](https://ollama.com) and `ollama pull qwen2.5-coder:7b`. If the input data changes, the default run needs Ollama too, since a changed question has no saved answer; without it the program stops with an error rather than guessing.

## How it works

```
shipment_records.csv
  -> 1. weekly table        cost_watch/metrics.py   one row per (route, week)
  -> 2. two baselines       cost_watch/metrics.py   own 8-week history, same-type peers
  -> 3. flag rule           cost_watch/flags.py     is the rise unusual?
  -> 4. note guard          cost_watch/notes.py     right route, right weeks only
  -> 5. LLM judge + reason  cost_watch/verdicts.py  does the note explain a rise?
  -> output/flagged_routes.csv                       run.py
```

**1. Weekly cost.** `week_of` is the Monday of the shipment's week. The weekly rate is total cost / total tonne-km, not the average of per-shipment rates, so each shipment counts in proportion to the transport it bought (a 9-tonne load doesn't weigh the same as a 22-tonne one).

**2. Baselines, as defined in the brief.**
- Own history: mean of up to 8 earlier weeks. `shift(1)` drops the current week first, so there is no look-ahead. In each route's first 8 weeks (Jan-Feb 2024) I use all earlier weeks available; week 1 has none and is never flagged. One flagged row is affected: Delhi-Jaipur 2024-01-29 uses 4 earlier weeks.
- Similar routes: mean rate of the other routes with the same `route_type` that week, computed as (group sum - own rate) / (group size - 1).
- `rolling(8)` counts rows, not calendar weeks. That only works because every route has all 104 weeks, so `check_no_week_gaps` asserts it.

**3. Flag rule.** A week is flagged if its rate is at least 5% above its own history and any of these holds:
- z-score vs own history > 3 (more than 3 of the route's usual week-to-week wobbles).
- z-score of the gap to peers > 3. Short and Long routes have only one peer, so I compare this week's gap with the route's usual gap instead. This also keeps Mumbai-Pune, always ~12% above its only peer, from being flagged every week.
- Backstop: 20%+ above own history or 25%+ above peers.

Why:
- z > 3, not 2: in this data 42 of 714 route-weeks (5.9%) have an own-history z above 2, too many false alarms. 12 are above 3.
- 5% floor: with little history the std is tiny, so a +1.2% move scored z = 6. 5% is also the smallest real cost driver in the notes (diesel, 5-7%).
- Backstop: rolling z-scores suffer from masking. After the Chennai-Bangalore flood spike, the inflated std made the next three weeks (+14% to +23%) look normal, and a slow creep (Mumbai-Pune from late Oct 2025) pulls the trailing mean up with it. Under 1% of weeks are 20%+ above their own history, and under 2% are 25%+ above peers.

**4. Note guard (plain code).** A note is considered only if it applies to that route or "All Routes", and the week falls in the note's window. The window starts at the note's week, since a note can't explain a rise before it was written. It ends at the note's stated end date if it has one (N001: "Feb 24 to Mar 8"), otherwise after 4 weeks.

**5. LLM judge.** For each note that passes the guard, a local model (`qwen2.5-coder:7b` via Ollama, temperature 0, seed 42, JSON output) answers one question: does this note explain a cost rise? It must quote the sentence it relied on. Then the code decides:
- If the quote isn't literally in the note, the "yes" is discarded.
- If the note gives a % range and the rise is over 1.5x its upper end, the note only partly explains it and the week stays flagged. Example: N003 says diesel added 5-7%; Mumbai-Delhi rose 11.6% on 2025-05-12.
- The `reason` is a template filled with the note's own text, so it can't claim anything the note doesn't.

So the LLM reads meaning ("costs were not significantly affected" is not a reason for a rise) and the code enforces route, dates and size. I used a structured filter instead of a vector database: with 10 notes the deciding constraints are route and date, which similarity search doesn't enforce. With hundreds of notes I'd add embedding search in front of the same guard.

## How I checked it

`python eval/check.py` (all pass):
1. Output columns match the contract.
2. All 3 rows in FreightTiger's sample match my numbers, flag and note id. This confirms the weekly formula and both baseline definitions.
3. Every cited note applies to that route and its window covers that week.
4. 21/21 flagged weeks get the verdict I labelled by hand in `eval/labels.csv`, including the trap notes: N004 (routes not in the data), N005, N006 and N010 (no change), N007 and N009 (improved or back to normal). A wrong "justified" would be reported as FABRICATED; there were none.

`python eval/llm_traps.py` shows each of the 10 notes to the judge on its own and compares the answer with my labels in `eval/note_labels.csv`: 10/10.

Limit: I wrote the labels, and `labels.csv` assumes my time-window rule, so check 4 shows the system does what I decided, not that the window rule is the only right one. The sample rows are the only labels I didn't write.

## Reproducibility

Three untouched live runs (`--live`, cache ignored, model queried each time) produced byte-identical output: `runs/run1..3/flagged_routes.csv`, compared with `diff`. Temperature 0 and a fixed seed make the model's yes/no repeatable, and the verdict and note id are set by code from that answer.

The default run replays answers from `cache/llm_cache.json`, keyed by a SHA-256 hash of the exact request (model, options, and the full prompt with route, week and % rise). If anything in the question changes, the key changes and the model is asked again, so a saved answer is never reused for a different question.

## Token and cost log (one full live run)

From `runs/run1/token_log.json` (each run writes one next to its output):

| Metric | Value |
|---|---|
| LLM calls | 10 (only flagged weeks with a candidate note; 21 flagged) |
| Input tokens | 1,972 |
| Output tokens | 405 |
| Cost | Rs 0, local open-source model (Qwen2.5-Coder 7B, Apache-2.0) |

The trap test adds 10 calls (1,945 input / 370 output tokens). A cached run makes 0 calls.

## Known limitations

- Only two Short routes exist, so the peer for Mumbai-Pune (~150 km) is Delhi-Jaipur (~280 km). Shorter trips cost more per km since loading and unloading are spread over fewer km. The peer-gap z-score absorbs the constant offset, but more or distance-adjusted peers would be better.
- The 4-week default note window is a judgement call; most notes don't say how long an effect lasts.
- `qwen2.5-coder:7b` is a code model. I used it because it was installed and scored 10/10 on the trap test; a general instruct model may read notes better.
- `sample_output_format_v2.csv` has an unquoted comma in its last `reason`. My output uses proper CSV quoting, and `eval/check.py` reads the sample tolerantly.
- The stretch goal (plain-English Q&A) is not built.
