#!/usr/bin/env bash
# Vault baseline (not part of the loop): same 12 questions via qmd; hit = corrected-rule keyword appears in top-5.
cd "$(dirname "$0")"; miss=0; n=0
python3 -c 'import json;[print(c["question"]+"\t"+c["vault_kw"]) for c in json.load(open("corpus.json"))]' | while IFS=$'\t' read -r q kw; do
  out=$(qmd query "$q" -c brain -n 5 2>/dev/null)
  if echo "$out" | grep -qi -- "$kw"; then r=HIT; else r=MISS; fi
  echo "$r	$kw	$q"
done
