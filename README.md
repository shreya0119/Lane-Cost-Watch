# Lane Cost Watch

Watches freight cost per tonne-km on each route, week by week, flags rises that look out of the ordinary, and checks a small set of context notes to see whether there is a real, documented reason. Every "justified" verdict cites one note that applies to that route and that week; anything else stays flagged for a human.

Output: [`output/flagged_routes.csv`](output/flagged_routes.csv) (21 flagged route-weeks, 5 justified, 16 unexplained), in the exact column format of `sample_output_format_v2.csv`.

## How to run

```bash
pip install pandas
# put shipment_records.csv, context_notes.csv and sample_output_format_v2.csv in data/
python run.py              # replays saved LLM answers from cache/ -- no LLM needed
python eval/check.py       # correctness checks (see below)
python eval/llm_traps.py   # does the LLM read every note correctly?
```

To ask the model again instead of replaying (`--live`), install [Ollama](https://ollama.com) and `ollama pull qwen2.5-coder:7b`. If the input changes, the default run also needs Ollama, because a changed question has no saved answer (see Reproducibility). The program stops with an error rather than guessing.

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

**1. Weekly cost.** `week_of` is the Monday of each shipment's week. For each (route, week), the rate is total cost / total tonne-km, not the average of per-shipment rates. That is the brief's formula applied to the whole week, and it weights each shipment by how much transport it bought, so a 9-tonne load doesn't count as much as a 22-tonne one.

**2. Baselines (exactly as defined in the brief).**
- *Own history*: mean of up to 8 earlier weeks. `shift(1)` removes the current week before the rolling mean, so there is no look-ahead. The first 8 weeks of each route (Jan-Feb 2024) have fewer than 8 earlier weeks, so they use all earlier weeks available (week 1 has none and is never flagged). One flagged row is affected: Delhi-Jaipur 2024-01-29, which uses 4 earlier weeks.
- *Similar routes*: mean rate of the other routes with the same `route_type` that same week, computed as (group sum - own rate) / (group size - 1).
- `rolling(8)` counts rows, not calendar weeks. That is only correct because every route has all 104 weeks. `check_no_week_gaps` asserts this, so a missing week would stop the run instead of silently being wrong.

**3. Flag rule.** A week is flagged if the rate is at least 5% above its own history **and** any of these is true:
- *z-score vs own history* > 3: the rise is more than 3 of the route's usual week-to-week wobbles (trailing std).
- *z-score of the peer gap* > 3. Short and Long routes have only one peer, so a spread across peers can't be computed. Instead I ask whether this week's gap to peers is unusually large compared with this route's usual gap. This also stops Mumbai-Pune, which is always ~12% above its only peer, from being flagged every week.
- *Backstop*: 20%+ above own history, or 25%+ above peers.

Why each part:
- *z > 3 rather than 2*: with 728 route-weeks, a z > 2 cut-off trips on about 1 normal week in 20, which is roughly 36 false alarms.
- *The 5% floor*: with a short history the std is tiny, so even a +1.2% move scored z = 6. The floor stops statistically odd but trivial moves from reaching a reviewer, and 5% is the size of the smallest real cost driver in the notes (diesel, 5-7%).
- *The backstop*: rolling z-scores suffer from **masking**. After the Chennai-Bangalore flood spike, the inflated std made the next three weeks (+14% to +23%) look normal, and a slow creep (Mumbai-Pune from late Oct 2025) drags the trailing mean up with it. Fewer than 1% of normal weeks are 20%+ above their own history, and fewer than 2% are 25%+ above peers.

**4. Note guard (plain code, no AI).** A note can only be considered for a flagged week if:
- it applies to that route or to "All Routes", **and**
- the week falls inside the note's window. The window starts at the note's own week; a note never explains a week before it was written. If the note states an end date (N001: "Feb 24 to Mar 8") the window ends there; otherwise it covers 4 weeks.

**5. LLM judge.** For each note that passes the guard, a local LLM (`qwen2.5-coder:7b` via Ollama, temperature 0, seed 42, JSON output) answers one question: does this note explain a cost *rise*? It must quote the sentence it relied on. The code then decides:
- If the quote is not literally in the note, the "yes" is thrown away.
- If the note states a % range and the rise is more than 1.5x its upper end, the note only partly explains it, and the week stays flagged. Example: N003 says diesel added 5-7%, but Mumbai-Delhi rose 11.6% on 2025-05-12.
- The `reason` text is built from a template using the note's own text, so the explanation cannot say anything the note does not.

The LLM judges meaning ("costs were not significantly affected" is not a reason for a rise), and code enforces the facts (route, dates, size). Retrieval here is a structured filter rather than a vector search: with 10 notes, the hard constraints are route and date, which similarity search does not enforce, so a vector DB would add a dependency without improving recall. With hundreds of notes I would add embedding retrieval *before* this same guard.

## How I convinced myself it was right

`python eval/check.py` (all pass):
1. Output columns match the contract exactly.
2. All 3 rows in FreightTiger's sample match our numbers, flag and note id. This independently confirms the weekly formula (total/total) and both baseline definitions.
3. Every cited note applies to that route and its window covers that week.
4. **21/21 flagged weeks get the verdict I labelled by hand** in `eval/labels.csv`, including the traps: N004 (toll on routes not in the data), N005, N006 and N010 ("no change"), N007 and N009 (improved or back to normal). A wrong "justified" is reported as FABRICATED. There were none.

`python eval/llm_traps.py`: each of the 10 notes is shown to the judge on its own (a matching route, a 6% rise, inside the window), and the answer is compared with my hand label in `eval/note_labels.csv`: **10/10**.

Honest limits of this check: I wrote the labels, and the expected verdicts in `labels.csv` assume my time-window rule. So check 4 confirms the system does what I decided, not that my window rule is the only right one. The sample rows (check 2) are the only labels I did not write.

## Reproducibility

Three untouched live runs (`--live`, cache ignored, the model actually queried each time) gave byte-identical output: `runs/run1..3/flagged_routes.csv`, checked with `diff`. Temperature is 0 and the seed is fixed, so the model is deterministic for the same prompt, and the verdict and note id come from code applied to its yes/no.

The default run replays saved answers from `cache/llm_cache.json`. Each entry is keyed by a SHA-256 hash of the exact request (model, options, full prompt including the route, week and % rise). Replaying is just memoisation: if anything in the question changes, the key changes and the model is asked again. A saved answer can never be reused for a different question.

## Token and cost log (one full live run)

From `runs/run1/token_log.json` (each run writes its own `token_log.json` next to its output):

| Metric | Value |
|---|---|
| LLM calls | 10 (only flagged weeks with a candidate note are sent; 21 flagged weeks) |
| Input tokens | 1,972 |
| Output tokens | 405 |
| Cost | Rs 0. Runs locally on an open-source model (Qwen2.5-Coder 7B, Apache-2.0) |

The eval trap test adds 10 calls (1,945 input / 370 output tokens). A default (cached) run makes 0 calls.

## Known limitations

- Only two Short routes exist, so "similar routes" for Mumbai-Pune (~150 km) is just Delhi-Jaipur (~280 km). Shorter trips cost more per km because loading and unloading are spread over fewer km. The peer-gap z-score handles the constant offset, but a real deployment would want more peers or distance-adjusted peers.
- The 4-week default note window is a judgement call. Notes rarely state how long an effect lasts.
- `qwen2.5-coder:7b` is a code model. A general instruct model would likely read notes as well or better. I used it because it was already installed and it scored 10/10 on the trap test.
- `sample_output_format_v2.csv` has an unquoted comma in its last `reason` field. Our output is written with proper CSV quoting, and `eval/check.py` reads the sample tolerantly.
- Stretch goal (asking questions in plain English) is not built.
