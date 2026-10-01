"""Probe site: a person chats with Luna (gpt-5.6-luna via codex) who answers from the REAL Sanity Context MCP.
Every answer carries its trace: each MCP call with arguments and result, web searches, shell attempts.
All dialogs are stored in data/sessions/<id>.json (Claude reads them). Stdlib only.
Run: python3 server.py  → http://<host>:8930"""
import json, os, subprocess, sys, threading, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data", "sessions"); os.makedirs(DATA, exist_ok=True)
CH = os.path.join(ROOT, "luna_home"); CWD = os.path.join(ROOT, "luna_cwd")
sys.path.insert(0, ROOT); from secrets_env import tok
sys.path.insert(0, os.path.join(ROOT, "v2")); import answer_check, text_kb
TOKEN = tok("SANITY_CONTEXT_TOKEN")
MCP_URL = "https://api.sanity.io/v1/context/organizations/ocr92wo5l/mcp/hw-lab"
PORT = int(os.environ.get("PORT", 8930))
MODELS = {"luna": "gpt-5.6-luna", "sol": "gpt-6-sol"}
LOCK = threading.Lock(); RUNNING = set()

PREFACE_BASE = ('You are the assistant of a hardware compatibility app. Your knowledge source is the MCP server "sanity" '
                "(call initial_context first, then query it). Do not use shell or files. "
                "Answer in the language the user writes in.\n\n")
PREFACE_NOBASE = "You are a helpful hardware advisor. Do not use shell or files. Answer in the language the user writes in.\n\n"

def path(sid): return os.path.join(DATA, f"{sid}.json")
def load(sid):
    with open(path(sid)) as f: return json.load(f)
def save(s):
    tmp = path(s["id"]) + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path(s["id"]))

WINDOW = {"direct": "MODE: direct answer (left window). Do not ask questions; turn unknowns into explicit conditions.\n\n",
          "dialogue": "MODE: dialogue (right window). Ask at most 3 questions per turn, only those that change the answer.\n\n"}
V2_READ = os.path.join(ROOT, "v2", "mcp_read.py")
REAL_V2 = "https://api.sanity.io/v2026-02-27/context/mcp/onwa0wvs/v2"  # real Sanity Context MCP on dataset v2
SNAP_FILE = os.path.join(ROOT, "v2", "export", "v2_2026-09-30_1311_pre_v3.ndjson")  # frozen "before v3" base

def prompt_for(s, mode):
    pre = PREFACE_BASE if mode["base"] else PREFACE_NOBASE
    if mode["base"] and mode.get("db") in ("v2", "v3", "v2snap", "v31"):
        pre = (f"Today is {time.strftime('%Y-%m-%d')}. " 'Your knowledge source is the MCP server "sanity". Call initial_context first: it has your full working '
               "instructions. Do not use shell or files. Answer in the language the user writes in.\n\n"
               + WINDOW.get(mode.get("win"), WINDOW["direct"]))
    hist = ""
    for m in s["messages"][:-1]:  # previous turns, text only
        hist += ("User: " if m["role"] == "user" else "Assistant: ") + m["text"] + "\n\n"
    if mode["base"] and mode.get("db") == "v31real":
        pre = (f"Today is {time.strftime('%Y-%m-%d')}. " 'Your knowledge source is the Sanity Context MCP server "sanity" (call initial_context first). '
               "Do not use shell or files. Answer in the language the user writes in.\n"
               "The APP INSTRUCTIONS below are your working instructions and take priority over the generic text returned by "
               "initial_context: in particular you MUST compute with the base's laws and run its rules (that is drawing "
               "conclusions from the data, and it is required), marking derived values as calculated.\n\n"
               + WINDOW.get(mode.get("win"), WINDOW["direct"])
               + "# APP INSTRUCTIONS\n" + open(os.path.join(ROOT, "v2", "prompt_use_v31.md")).read() + "\n\n")
    if mode["base"] and mode.get("db") in ("v3text", "v3textnv"):
        pre = (f"Today is {time.strftime('%Y-%m-%d')}. Your knowledge source is the knowledge base given below as plain-text notes "
               "(the same base; tool names in the instructions refer to it — here you read it directly). Do not use shell or files. "
               "Answer in the language the user writes in.\n\n" + WINDOW.get(mode.get("win"), WINDOW["direct"])
               + "# INSTRUCTIONS\n" + open(os.path.join(ROOT, "v2", "prompt_use_v3.md")).read()
               + "\n\n" + text_kb.build() + "\n\n")
    if mode.get("db") in ("v3", "v3text", "v31", "v31real", "v3textnv") and s.get("situation"):
        pre += "Stored situation (validated by the app from earlier turns):\n" + json.dumps(s["situation"], ensure_ascii=False) + "\n\n"
    tail = "\n\n(Reply in the language of this last User message.)" if mode.get("db") == "v31real" else ""
    return pre + ("Conversation so far:\n\n" + hist if hist else "") + "User: " + s["messages"][-1]["text"] + tail

def exec_codex(prompt, mode, cfg, msg, sid, t0):
    p = subprocess.Popen(["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
                          "-m", MODELS.get(mode.get("model"), "gpt-5.6-luna"), *cfg, "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=CWD,
                         env=dict(os.environ, CODEX_HOME=CH, SANITY_CONTEXT_TOKEN=TOKEN))
    p.stdin.write(prompt); p.stdin.close()
    texts, usage = [], None
    for line in p.stdout:
        try: ev = json.loads(line)
        except ValueError: continue
        it = ev.get("item") or {}
        if ev.get("type") == "item.completed":
            k = it.get("type")
            if k == "agent_message": texts.append(it.get("text", ""))
            elif k == "mcp_tool_call":
                res = it.get("result") or {}
                txt = "\n".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
                msg["trace"].append({"kind": "base", "tool": it.get("tool"), "args": it.get("arguments"),
                                     "result": txt[:20000], "error": it.get("error"), "t": round(time.time() - t0, 1)})
            elif k == "web_search":
                msg["trace"].append({"kind": "web", "query": it.get("query") or (it.get("action") or {}).get("query"),
                                     "t": round(time.time() - t0, 1)})
            elif k == "command_execution":
                msg["trace"].append({"kind": "shell", "command": it.get("command"), "t": round(time.time() - t0, 1)})
            if k != "agent_message":
                msg["text"] = texts[-1] if texts else msg["text"]; save_msg(sid, msg)
        elif ev.get("type") == "turn.completed":
            usage = ev.get("usage")
    p.wait()
    return texts, p.returncode, p.stderr.read()[-800:], usage

V3_ROUNDS = 2  # validator fix rounds

def run_turn(sid, mode):
    s = load(sid)
    cfg = ["-c", f'web_search="{"live" if mode["web"] else "disabled"}"',
           ] + ([] if mode.get("effort", "default") == "default" else ["-c", f'model_reasoning_effort="{mode["effort"]}"'])
    if mode["base"] and mode.get("db") in ("v2", "v3", "v2snap", "v31"):
        cfg += ["-c", 'mcp_servers.sanity.command="python3"', "-c", f'mcp_servers.sanity.args=["{V2_READ}"]',
                "-c", 'mcp_servers.sanity.default_tools_approval_mode="approve"']
        if mode.get("db") == "v3": cfg += ["-c", 'mcp_servers.sanity.env={PROMPT_USE="prompt_use_v3.md"}']
        if mode.get("db") == "v31": cfg += ["-c", 'mcp_servers.sanity.env={PROMPT_USE="prompt_use_v31.md"}']
        if mode.get("db") == "v2snap": cfg += ["-c", f'mcp_servers.sanity.env={{SNAPSHOT="{SNAP_FILE}", SCHEMA_JSON="schema.json.bak_v2", SCHEMA_TS="index.ts.bak_v2"}}']
    elif mode["base"] and mode.get("db") == "v31real":
        cfg += ["-c", f'mcp_servers.sanity.url="{REAL_V2}"',
                "-c", 'mcp_servers.sanity.bearer_token_env_var="SANITY_CONTEXT_TOKEN"',
                "-c", 'mcp_servers.sanity.default_tools_approval_mode="approve"']
    elif mode["base"] and mode.get("db") == "v1":
        cfg += ["-c", f'mcp_servers.sanity.url="{MCP_URL}"',
                "-c", 'mcp_servers.sanity.bearer_token_env_var="SANITY_CONTEXT_TOKEN"',
                "-c", 'mcp_servers.sanity.default_tools_approval_mode="approve"']
    msg = {"role": "assistant", "text": "", "trace": [], "mode": mode, "started": time.time(), "status": "running"}
    s["messages"].append(msg); save(s)
    t0 = time.time()
    prompt = prompt_for({"messages": s["messages"][:-1], "situation": s.get("situation")}, mode)
    texts, rc, err, usage = exec_codex(prompt, mode, cfg, msg, sid, t0)
    msg["notes"] = texts[:-1]  # intermediate "I will now..." messages
    answer = texts[-1] if texts else "(no answer — see stderr)"
    usages = [usage]
    if mode.get("db") in ("v3", "v3text", "v31", "v31real", "v3textnv") and rc == 0:
        msg["validator"] = []
        for rnd in range(V3_ROUNDS + 1):
            try: visible, block, errs = answer_check.check(answer, msg["trace"], s.get("situation") or {})
            except Exception as e: visible, block, errs = answer, None, []; msg["validator"].append({"round": rnd, "crash": str(e)[:300]}); break
            msg["validator"].append({"round": rnd, "errors": errs})
            if not errs or rnd == V3_ROUNDS or mode.get("db") == "v3textnv": break  # nv = no validator feedback (control)
            save_msg(sid, msg)
            fix = (prompt + "\n\nYour previous answer:\n\n" + answer +
                   "\n\nThe app's validator (code, checking your answer against the base) found these problems:\n- " + "\n- ".join(errs) +
                   "\n\nWrite the FULL corrected answer for the person (not a diff), in the language of the person's last message, with the ```check block at the end. Use the tools as needed.")
            t2, rc2, err2, u2 = exec_codex(fix, mode, cfg, msg, sid, t0); usages.append(u2)
            if rc2 != 0 or not t2: break
            answer = t2[-1]
        msg["check"] = block
        if block and isinstance(block.get("situation"), dict):
            s2 = load(sid); s2["situation"] = block["situation"]; s2["messages"][-1] = msg; save(s2)
        answer = visible
    msg["text"] = answer
    msg["usage"] = usages[0] if len(usages) == 1 else usages
    msg["status"] = "done" if rc == 0 else f"error {rc}: {err}"
    msg["sec"] = round(time.time() - t0, 1)
    save_msg(sid, msg)
    with LOCK: RUNNING.discard(sid)

def save_msg(sid, msg):
    s = load(sid); s["messages"][-1] = msg; save(s)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html")
        if self.path == "/api/sessions":
            out = []
            for f in sorted(os.listdir(DATA), reverse=True):
                if f.endswith(".json"):
                    s = json.load(open(os.path.join(DATA, f)))
                    first = next((m["text"] for m in s["messages"] if m["role"] == "user"), "")
                    out.append({"id": s["id"], "created": s["created"], "title": first[:80], "n": len(s["messages"])})
            return self.send(200, sorted(out, key=lambda x: -x["created"]))
        if self.path.startswith("/api/session/"):
            sid = self.path.rsplit("/", 1)[1]
            if not os.path.exists(path(sid)): return self.send(404, {"error": "no session"})
            s = load(sid); s["running"] = sid in RUNNING
            return self.send(200, s)
        self.send(404, {"error": "not found"})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/ask":
            text = (body.get("text") or "").strip()
            if not text: return self.send(400, {"error": "empty"})
            sid = body.get("session") or uuid.uuid4().hex[:12]
            with LOCK:
                if sid in RUNNING: return self.send(409, {"error": "Luna is still answering"})
                RUNNING.add(sid)
            s = load(sid) if os.path.exists(path(sid)) else {"id": sid, "created": time.time(), "messages": []}
            s["messages"].append({"role": "user", "text": text, "t": time.time()}); save(s)
            mode = {"base": bool(body.get("base", True)), "web": bool(body.get("web", False)),
                    "db": body.get("db", "v2") if body.get("db") in ("v1", "v2", "v3", "v3text", "v2snap", "v31", "v31real", "v3textnv") else "v2",
                    "win": body.get("win", "direct") if body.get("win") in ("direct", "dialogue") else "direct",
                    "model": body.get("model") if body.get("model") in MODELS else "luna",
                    "effort": body.get("effort") if body.get("effort") in ("none", "low", "medium", "high", "xhigh") else "default"}
            threading.Thread(target=run_turn, args=(sid, mode), daemon=True).start()
            return self.send(200, {"session": sid})
        self.send(404, {"error": "not found"})

if __name__ == "__main__":
    print(f"probe on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
