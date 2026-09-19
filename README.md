# tortoise-drift-bench

A 12-case benchmark for one question: when a rule in an agent's memory gets corrected, does recall return the correction or the stale version?

Built against [Tortoise](https://github.com/daniel-ospina/tortoise), a belief-graph memory layer for coding agents. Maintained by [codeclawd](https://codeclawd.com).

## What it measures

Each case is a real stale-to-corrected chain pulled from a Claude Code operator's lessons log. Example (`gtimeout`):

- stale: "macOS has no timeout command; use gtimeout instead."
- corrected: "macOS has no timeout and no gtimeout either unless coreutils is installed; implement the timeout in bash."
- evidence: "which gtimeout returned nothing on the Mac; coreutils is not installed."
- question: "how do I run a command with a timeout on this Mac"

`bench.py` files every case with the strategy in `strategy.py`, asks the 12 questions through `tortoise_recall`, and scores two errors per case:

1. the corrected point is not top-1
2. the stale point outranks it, or still holds confidence above 0.5

Metric is drift errors, 0 to 24. Lower is better. Files are frozen; the loop only edits `strategy.py`.

## How the filing strategy was found

`run_experiment.sh` runs an autoresearch loop: change `strategy.py`, run the bench three times, keep the change if the metric drops, log to `results.tsv`. Eight rounds on 2026-09-16:

| round | strategy | errors (3 runs) | calls/case |
|---|---|---|---|
| r0 | plain statements, no edges | 16 | 3.2 |
| r1 | `tortoise_invalidate` chain stale→corrected, promote corrected | 8 | 5.3 |
| r3 | r1 + corrected born `credibility="high"` | 4 / 5 / 5 | 5.3 |
| **r4** | **r3 + each evidence point `IMPL` → corrected, default prior** | **3 / 3 / 3** | 6.3 |
| r2, r5, r6, r7 | see `results.tsv` | discarded | |

All three r4 errors were top-1 ranking misses. The stale point never outranked the fix and never kept confidence above 0.5 after r1.

Two things the loop taught us that the tool docs do not say:

- Use `tortoise_invalidate` for corrections, not `tortoise_supersede`. Supersede transfers NAND edges by default, so evidence that refuted the old claim ends up counting against the new one.
- Draft points do not promote themselves on first edge. Call `tortoise_promote_point`.

Hosted (api.premiselabs.co) and self-hosted (Docker, FalkorDB) scored identically. Self-hosted ran 10 to 30 times faster.

## Baseline

`vault_baseline.sh` asks the same 12 questions of a plain markdown notes folder through `qmd` (BM25 + vector). Hit means the corrected rule's keyword appears in the result. Top-5: 9/12. Top-1: 5/12. Tortoise r4 top-1: 9/12.

Caveat: the notes folder held about 250 pages of unrelated text; the graph held about 50 points. Part of the gap is scale.

## Running it

```
export TORTOISE_URL=http://127.0.0.1:8000/mcp/
export TORTOISE_API_KEY=...
python3 bench.py
```

Run against an empty graph. The bench tags its points `ar-bench` and deletes them on teardown. It creates points with `dedup: false`; with dedup on, `create_point` returns any pre-existing point with matching content and teardown then deletes data the bench never made. We lost 38 real points learning that.

## Privacy note

Five cases were edited before publishing. One case that named a business and its founders was replaced with a different real chain (`automerge`). Four cases that described the operator's own sync setup were reworded to generic infrastructure terms. The numbers above were measured on the original wording on 2026-09-16 and have not been reproduced on the edited set. If you rerun and the numbers move, the wording is the first suspect.

## License

Code (`bench.py`, `strategy.py`, `*.sh`): MIT. Data (`corpus.json`, `results.tsv`, logs): CC BY 4.0. Both require attribution to codeclawd.
