"""ASSET — the filing strategy. The loop edits this file only.

file_case(api, case) -> {"stale": [point ids], "corrected": point id}
case = {"chain": [oldest .. newest claim], "evidence": [...], ...}
"""


def file_case(api, case):
    # Round 4: r3 + evidence IMPL->corrected at default prior.
    # Round 3: r1 + corrected born with credibility=high.
    # Round 1: supersession chain. Each newer claim invalidates the older one
    # (tortoise_invalidate = no edge transfer). Corrected claim promoted live.
    ids = [api.create_point("statement", c)["id"] for c in case["chain"][:-1]]
    ids.append(api.create_point("statement", case["chain"][-1], credibility="high")["id"])
    for old, new in zip(ids, ids[1:]):
        api.call("tortoise_invalidate", {"id": old, "corrected_by_id": new})
    api.call("tortoise_promote_point", {"point_id": ids[-1]})
    for ev in case["evidence"]:
        eid = api.create_point("observation", ev)["id"]
        api.call("tortoise_create_operator", {"op_type": "IMPL", "source_id": eid,
                                              "target_ids": [ids[-1]], "direction": "unidirectional"})
    return {"stale": ids[:-1], "corrected": ids[-1]}
