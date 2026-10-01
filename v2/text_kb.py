"""Control arm for the "does STRUCTURE matter" test (judge j0028): the same facts as dataset v2, rendered as a plain
text knowledge base (wiki-like notes). No schema, no field descriptions, no query tools; references become names.
build() -> markdown string. python3 text_kb.py → prints size."""
import json, time, urllib.parse, urllib.request
DS = "v2"; _C = {}
SKIP = {"_rev", "_createdAt", "_updatedAt", "_key", "_type", "_id", "_ref"}

SNAP = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),
                                   "export", "v2_2026-09-30_1318_v3.ndjson")  # pinned: same state as the v3 structured arm

def _all():
    if SNAP:
        docs = [json.loads(l) for l in open(SNAP) if l.strip()]
        return [d for d in docs if not d["_id"].startswith("_.") and not d["_type"].startswith("sanity.")
                and not d["_id"].startswith("drafts.")]
    q = '*[!(_id in path("_.**")) && !(_type match "sanity.*")]'
    u = f"https://onwa0wvs.api.sanity.io/v2025-09-01/data/query/{DS}?" + urllib.parse.urlencode({"query": q})
    return json.load(urllib.request.urlopen(u, timeout=30))["result"]

def _title(d): return d.get("name") or d.get("title") or d.get("claim", "")[:60] or d["_id"]

def _val(v, names):
    if isinstance(v, dict):
        if "_ref" in v: return names.get(v["_ref"], v["_ref"])
        parts = [f"{k} {_val(x, names)}" for k, x in v.items() if k not in SKIP and x not in (None, "", [])]
        return "(" + "; ".join(parts) + ")"
    if isinstance(v, list): return ", ".join(_val(x, names) for x in v)
    return str(v)

def build():
    if _C.get("t", 0) > time.time() - 300: return _C["text"]
    docs = _all(); names = {d["_id"]: _title(d) for d in docs}
    out = ["# Knowledge base: AI hardware advisor (plain-text notes)\n"]
    for d in sorted(docs, key=lambda d: (d["_type"], d["_id"])):
        out.append(f"## {_title(d)}\nid: {d['_id']} · kind: {d['_type']}")
        for k, v in d.items():
            if k in SKIP or k in ("name", "title") or v in (None, "", []): continue
            out.append(f"- {k}: {_val(v, names)}")
        out.append("")
    _C.update(t=time.time(), text="\n".join(out)); return _C["text"]

if __name__ == "__main__":
    t = build(); print(len(t)); print(t[:1500])
