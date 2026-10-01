"""Build the static replay page data (docs/runs.json) from recorded probe sessions.
Shows EVERY run of one graded measurement (no picking) + optional labelled featured runs; long tool results are cut.
Usage: python3 tools/build_replay.py <sessions_dir> <measured.graded.json> [extra.graded.json[,more]] [scenario=session ...]"""
import json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = {s["id"]: s for s in json.load(open(os.path.join(HERE, "v2", "acceptance", "scenarios.json")))["scenarios"]}
CUT = 1500
PRIVATE = re.compile(r"/home/\w+|192\.168\.\d+\.\d+|helgard", re.I)

def english(t): return len(re.findall("[а-яА-ЯёЁіїєІЇЄ]", t)) < len(t) * 0.02

def clean(x):
    x = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    x = PRIVATE.sub("[local]", x)
    return x if len(x) <= CUT else x[:CUT] + f"\n… [{len(x) - CUT} more characters]"

def session(path, scid, grade):
    s = json.load(open(path)); turns = []
    for m in s["messages"]:
        if m["role"] == "user":
            turns.append({"role": "user", "text": clean(m["text"])}); continue
        steps = [{"kind": t.get("kind"), "tool": t.get("tool") or t.get("query") or "", "args": clean(t.get("args", "")),
                  "result": clean(t.get("result", ""))} for t in m.get("trace") or []]
        turns.append({"role": "assistant", "text": PRIVATE.sub("[local]", m["text"]), "sec": m.get("sec"), "steps": steps,
                      "calculations": (m.get("check") or {}).get("calculations") if isinstance(m.get("check"), dict) else None,
                      "validator": [{"round": v.get("round"), "errors": [clean(e) for e in v.get("errors", [])]}
                                    for v in m.get("validator") or []]})
    return {"scenario": scid, "title": SC[scid].get("title", scid), "checklist": SC[scid]["judge"], "session": s["id"],
            "grade": grade, "turns": turns}

if __name__ == "__main__":
    # ALL runs of the measured run (no picking), plus optional featured runs from other runs, labelled.
    sess_dir = sys.argv[1]; graded = json.load(open(sys.argv[2]))
    extra = [g for f in (sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []) for g in json.load(open(f))]
    featured = dict(a.split("=") for a in sys.argv[4:])  # scenario=session from the extra runs
    def one(g, note=None):
        j = g["judge"]; r = session(f"{sess_dir}/{g['session']}.json", g["scenario"],
                                    {"pass": sum(1 for x in j if x.get("pass")), "of": len(j), "items": j})
        last = [t for t in r["turns"] if t["role"] == "assistant"][-1]["text"]
        r["english"] = english(last); r["note"] = note; return r
    out = []
    for scid in sorted(SC):
        runs = [one(g) for g in graded if g["scenario"] == scid]
        if scid in featured:
            g = next(g for g in extra if g["session"] == featured[scid])
            runs.append(one(g, "featured trace from an EARLIER v3.1 run (not part of the 59/78 measurement); that run's checker "
                               "had two bugs, so some validator rounds in it are false alarms"))
        out.append({"scenario": scid, "runs": runs})
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "docs", "runs.json"), "w"), ensure_ascii=False, indent=1)
    open(os.path.join(HERE, "docs", "runs.js"), "w").write("window.RUNS=" + json.dumps(out, ensure_ascii=False) + ";\n")
    tot = sum(r["grade"]["pass"] for x in out for r in x["runs"] if not r["note"]); of = sum(r["grade"]["of"] for x in out for r in x["runs"] if not r["note"])
    print(sum(len(x["runs"]) for x in out), "runs; measured total", f"{tot}/{of}")
