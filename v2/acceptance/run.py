"""Run acceptance scenarios through the probe API (:8930), same path as a person in the browser.
Usage: python3 run.py <tag> [model=luna] [repeats=1] [ids...]  → acceptance/results/<tag>.json {scenario: [session ids]}"""
import concurrent.futures as cf, json, os, sys, time, urllib.request
API = os.environ.get("API", "http://127.0.0.1:8930"); SESS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "probe", "data", "sessions")
HERE = os.path.dirname(os.path.abspath(__file__))

def post(body):
    r = urllib.request.Request(API + "/api/ask", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))

def run(sc, model):
    sid = None
    for text in sc["turns"]:
        sid = post({"session": sid, "text": text, "base": True, "web": True, "db": os.environ.get("DB", "v2"),
                    "win": "direct", "model": model, "effort": "default"})["session"]
        time.sleep(5)
        while True:
            last = json.load(open(f"{SESS}/{sid}.json"))["messages"][-1]
            if last["role"] == "assistant" and last.get("status") != "running": break
            time.sleep(10)
    return sc["id"], sid

if __name__ == "__main__":
    tag = sys.argv[1]; model = sys.argv[2] if len(sys.argv) > 2 else "luna"
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 1; ids = sys.argv[4:]
    scs = [s for s in json.load(open(f"{HERE}/scenarios.json"))["scenarios"] if not ids or s["id"] in ids]
    jobs = [s for s in scs for _ in range(reps)]
    res = {}
    with cf.ThreadPoolExecutor(min(len(jobs), 7)) as ex:
        for scid, sid in ex.map(lambda s: run(s, model), jobs):
            res.setdefault(scid, []).append(sid); print(scid, sid, flush=True)
    os.makedirs(f"{HERE}/results", exist_ok=True)
    json.dump({"model": model, "sessions": res}, open(f"{HERE}/results/{tag}.json", "w"), indent=1)
