#!/usr/bin/env python3
"""FROZEN benchmark. Never edit. Files corpus via strategy.py, asks the 12 questions, scores drift errors.

metric  = drift errors (0..24). Per case: +1 if recall top-1 is not the corrected point;
          +1 if any stale point of the case is returned with confidence > 0.5 OR ranked above the corrected point.
mem_mb  = mean API calls per case (cost proxy).
correct = true iff audit has no 'high' severity check AND every point the strategy created was deleted.
"""
import json, os, sys, time, urllib.request, importlib

def _key():
    k = os.environ.get("TORTOISE_API_KEY")
    if k:
        return k
    cfg = json.load(open(os.path.expanduser("~/.claude.json")))
    return cfg["mcpServers"]["tortoise"]["headers"]["Authorization"].split()[-1]


KEY = _key()
URL = os.environ.get("TORTOISE_URL", "http://127.0.0.1:8000/mcp/")
TAG = "ar-bench"


class API:
    def __init__(self):
        self.calls = 0
        self.created = []  # every id created (points + operators)

    def call(self, tool, args):
        self.calls += 1
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": tool, "arguments": args}}).encode()
        req = urllib.request.Request(URL, data=body, headers={
            "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        for attempt in range(3):
            try:
                raw = urllib.request.urlopen(req, timeout=60).read().decode()
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(1)
        line = next(l for l in raw.splitlines() if l.startswith("data: ") or l.startswith("{"))
        d = json.loads(line.removeprefix("data: "))
        r = d.get("result", {})
        sc = r.get("structuredContent")
        if sc is None and r.get("content"):
            try:
                sc = json.loads(r["content"][0]["text"])
            except Exception:
                sc = {"text": r["content"][0]["text"]}
        if isinstance(sc, dict):
            sc.pop("embedding", None)
            if tool in ("tortoise_create_point", "tortoise_create_operator") and sc.get("id"):
                self.created.append(sc["id"])
        return sc

    # convenience used by strategies; still counted as calls
    def create_point(self, kind, content, **kw):
        props = kw.pop("props", {}) or {}
        props.setdefault("tags", [])
        if TAG not in props["tags"]:
            props["tags"] = list(props["tags"]) + [TAG]
        # dedup=False: with dedup on, create_point returns a PRE-EXISTING point whose
        # content matches, and teardown would then delete data this bench never created.
        return self.call("tortoise_create_point", {"kind": kind, "content": content, "props": props,
                                                   "dedup": False, **kw})


def cleanup(api):
    """Delete leftovers tagged ar-bench (from crashed runs) — not counted toward cost."""
    saved = api.calls
    try:
        res = api.call("tortoise_query_points_by_tag", {"tag": TAG})
        items = res.get("result") or res.get("results") or res.get("points") or []
        for it in items:
            pid = it.get("id") if isinstance(it, dict) else it
            if pid:
                api.call("tortoise_delete_point", {"id": pid})
    except Exception as e:
        print(f"cleanup warn: {e}", file=sys.stderr)
    api.calls = saved


def main():
    strategy = importlib.import_module("strategy")
    corpus = json.load(open(os.path.join(os.path.dirname(__file__), "corpus.json")))
    api = API()
    cleanup(api)

    filed = {}
    per_case_calls = []
    for case in corpus:
        before = api.calls
        filed[case["id"]] = strategy.file_case(api, case)  # -> {"stale": [ids], "corrected": id}
        per_case_calls.append(api.calls - before)
    try:
        api.call("tortoise_compute_confidence", {})
    except Exception as e:
        print(f"compute warn: {e}", file=sys.stderr)

    errors = 0
    for case in corpus:
        f = filed[case["id"]]
        res = api.call("tortoise_recall", {"query": case["question"], "limit": 10})
        results = res.get("results", []) if isinstance(res, dict) else []
        ids = [r.get("id") for r in results]
        conf = {r.get("id"): (r.get("ep") or {}).get("confidence_mean") for r in results}
        top1_ok = bool(ids) and ids[0] == f["corrected"]
        stale_bad = False
        corr_rank = ids.index(f["corrected"]) if f["corrected"] in ids else 99
        for s in f["stale"]:
            if s in ids:
                c = conf.get(s)
                if (c is not None and c > 0.5) or ids.index(s) < corr_rank:
                    stale_bad = True
        e = (0 if top1_ok else 1) + (1 if stale_bad else 0)
        errors += e
        print(f"case {case['id']:<9} top1_ok={top1_ok!s:<5} stale_bad={stale_bad!s:<5} corr_rank={corr_rank} err={e}")

    # correctness gate
    audit = api.call("tortoise_audit", {})
    high = [c for c in (audit.get("checks") or []) if c.get("severity") == "high" and c.get("count")]
    # teardown: delete everything we created
    saved = api.calls
    leftover = 0
    for pid in reversed(api.created):
        try:
            api.call("tortoise_delete_point", {"id": pid})
        except Exception:
            leftover += 1
    api.calls = saved
    correct = (not high) and leftover == 0

    print(f"metric:  {errors}")
    print(f"mem_mb:  {sum(per_case_calls)/len(per_case_calls):.2f}")
    print(f"correct: {'true' if correct else 'false'}")
    if high:
        print("audit_high:", json.dumps(high)[:500])


if __name__ == "__main__":
    main()
