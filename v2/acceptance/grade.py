"""Blind grading of acceptance runs. Judge = Sol via codex exec (no tools, no web), sees only the dialogue and
the checklist — not which version produced it. Code checks read the probe trace.
Usage: python3 grade.py <tag>  → results/<tag>.graded.json + summary table on stdout"""
import concurrent.futures as cf, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SESS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "probe", "data", "sessions")
ROOT = os.path.dirname(os.path.dirname(HERE)); CH, CWD = f"{ROOT}/luna_home", f"{ROOT}/luna_cwd"  # clean codex home: no hooks, no memory
JUDGE = os.environ.get("JUDGE_MODEL", "gpt-6.1-sol")
SC = {s["id"]: s for s in json.load(open(f"{HERE}/scenarios.json"))["scenarios"]}

def dialogue(s):
    out = []
    for m in s["messages"]:
        out.append(("PERSON: " if m["role"] == "user" else "ADVISOR: ") + m["text"])
    return "\n\n".join(out)

def code_checks(sc, s):
    last = [m for m in s["messages"] if m["role"] == "assistant"][-1]
    tr = last.get("trace") or []
    base = [t for t in tr if t.get("kind") == "base"]; web = [t for t in tr if t.get("kind") == "web"]
    res = {}
    c = sc.get("code", {})
    if "min_base_calls" in c: res["min_base_calls"] = len(base) >= c["min_base_calls"]
    if "min_web_calls" in c: res["min_web_calls"] = len(web) >= c["min_web_calls"]
    if c.get("web_before_answer"): res["web_before_answer"] = len(web) > 0
    res["_counts"] = {"base": len(base), "web": len(web), "sec": last.get("sec"),
                      "validator_rounds": len(last.get("validator", []))}
    return res

def judge(sc, s):
    items = "\n".join(f"{i+1}. {x}" for i, x in enumerate(sc["judge"]))
    prompt = ("You are a strict, blind grader of an AI hardware advisor. Below is a dialogue and a checklist. "
              "Grade ONLY the advisor's LAST answer (use earlier turns for context). For each item answer pass or fail "
              "and quote the shortest phrase from the answer that proves it (empty quote if fail). Do not reward effort, "
              "length or tone. Do not use tools.\n\n"
              f"CHECKLIST:\n{items}\n\nDIALOGUE:\n{dialogue(s)}\n\n"
              'Reply with JSON only: {"items":[{"n":1,"pass":true,"quote":"...","why":"one short reason"}, ...]}')
    p = subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", JUDGE,
                        "-c", 'web_search="disabled"', "-"], input=prompt, capture_output=True, text=True, timeout=900,
                       cwd=CWD, env=dict(os.environ, CODEX_HOME=CH))
    m = re.search(r"\{.*\}", p.stdout, re.S)
    try: return json.loads(m.group(0))["items"]
    except Exception: return [{"n": 0, "pass": None, "quote": "JUDGE PARSE ERROR: " + p.stdout[-300:] + p.stderr[-300:]}]

def one(job):
    scid, sid = job; s = json.load(open(f"{SESS}/{sid}.json")); sc = SC[scid]
    return {"scenario": scid, "session": sid, "code": code_checks(sc, s), "judge": judge(sc, s)}

if __name__ == "__main__":
    tag = sys.argv[1]; r = json.load(open(f"{HERE}/results/{tag}.json"))
    jobs = [(scid, sid) for scid, sids in r["sessions"].items() for sid in sids]
    with cf.ThreadPoolExecutor(7) as ex: out = list(ex.map(one, jobs))
    json.dump(out, open(f"{HERE}/results/{tag}.graded.json", "w"), indent=1, ensure_ascii=False)
    tot = ok = 0
    for g in sorted(out, key=lambda x: x["scenario"]):
        j = [x.get("pass") for x in g["judge"]]; c = [v for k, v in g["code"].items() if not k.startswith("_")]
        tot += len(j) + len(c); ok += sum(1 for x in j + c if x)
        print(f'{g["scenario"]:20s} {g["session"]} judge {"".join("✓" if x else "✗" for x in j)} code {"".join("✓" if x else "✗" for x in c)} {g["code"]["_counts"]}')
    print(f"TOTAL {ok}/{tot}")
