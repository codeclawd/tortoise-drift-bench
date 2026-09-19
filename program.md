# program.md — Tortoise keep/reject autoresearch

GOAL: decide whether Tortoise (hosted belief graph) should stay in the operator's memory stack.
ASSET: strategy.py — the filing strategy an agent would follow (kinds, edges, priors, supersede vs invalidate, promotion).
SCORING (frozen): bench.py + corpus.json — 12 real stale→corrected drift cases from the operator's own history.
  metric  = drift errors (0..24): per case, (a) recall top-1 != corrected point, (b) stale point still believed (>0.5) or ranked above corrected.
  mem_mb  = API calls per case (cost proxy).
  correct = graph audit has no high-severity check AND all bench points cleaned up.
CONSENSUS RULE (fixed before round 0):
  KEEP  iff best strategy metric < vault baseline (same 12 questions via qmd, keyword hit in top-5) with clean separation over 3 runs,
        AND mem_mb <= 4 calls/claim, AND correct: true.
  REJECT otherwise.
RULES: never edit bench.py / corpus.json. One hypothesis per round. Log to results.tsv.
