"""Public "bring your own agent" MCP endpoint for the AI hardware advisor (Sanity Challenge demo).

Visitors add https://<host>/mcp to ChatGPT / Claude / Codex / Cursor; their own model and subscription do the thinking.
This server:
  * forwards MCP calls to the real Sanity Context MCP (dataset v2, embeddings on) with our token, which never leaves it;
  * prepends the advisor instructions to `initial_context` and to the `initialize` instructions;
  * adds one tool, `check_answer`, that recomputes the agent's math with the `law` formulas stored in Sanity
    (same validator as the app, answer_check.py);
  * limits use per visitor and per day; past the daily cap `groq_query` falls back to the public dataset API.
Stdlib only. Env: SANITY_CONTEXT_TOKEN, PORT (9890), BIND (127.0.0.1), LOG_DIR."""
import hashlib, json, os, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import answer_check

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = "https://api.sanity.io/v2026-02-27/context/mcp/onwa0wvs/v2"
PUBLIC_GROQ = "https://onwa0wvs.apicdn.sanity.io/v2025-09-01/data/query/v2?"
TOKEN = os.environ["SANITY_CONTEXT_TOKEN"]
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(HERE, "logs"))
PER_IP_HOUR, PER_DAY_UPSTREAM, MAX_BODY = 1500, 4000, 512 * 1024
PROMPT = open(os.path.join(HERE, "prompt_public.md")).read()
INDEX = os.path.join(HERE, "index.html")
SALT = os.urandom(8)

CHECK_TOOL = {
    "name": "check_answer",
    "title": "Check the answer against the base",
    "description": ("Validate a draft answer before showing it. Pass the whole draft including the final ```check JSON block "
                    "(see initial_context). The server recomputes every calculation with the law formula stored in Sanity, "
                    "checks that every solutionPath got a verdict, that products are not mapped to a different base document, "
                    "that facts of items outside the base came from the web, and that every price has date, region and source. "
                    "Returns {ok, errors[], summary}. Fix the errors and call again (max 3 rounds)."),
    "inputSchema": {"type": "object", "properties": {
        "answer": {"type": "string", "description": "Full draft answer ending with the ```check block."},
        "searched_web": {"type": "boolean", "description": "True only if you actually searched the web in this turn."}},
        "required": ["answer"]},
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
}

_lock = threading.Lock()
_hits, _day = {}, {"d": "", "n": 0}
_ctx_cache = {"t": 0, "body": None, "d": ""}
_drafts = {}  # draft id -> {"t": time, "parts": {n: text}} — for browse-only agents whose URLs must stay short


def log(kind, **kw):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, time.strftime("%Y-%m-%d") + ".jsonl"), "a") as f:
        f.write(json.dumps({"t": time.strftime("%H:%M:%S"), "kind": kind, **kw}, ensure_ascii=False) + "\n")


def allow_ip(ip):
    now = time.time()
    with _lock:
        q = [t for t in _hits.get(ip, []) if t > now - 3600]
        if len(q) >= PER_IP_HOUR: _hits[ip] = q; return False
        q.append(now); _hits[ip] = q; return True


def take_upstream():
    with _lock:
        d = time.strftime("%Y-%m-%d")
        if _day["d"] != d: _day.update(d=d, n=0)
        if _day["n"] >= PER_DAY_UPSTREAM: return False
        _day["n"] += 1
    log("up"); return True


def upstream(msg):
    req = urllib.request.Request(UPSTREAM, data=json.dumps(msg).encode(), method="POST", headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        return {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32000, "message": f"upstream {e.code}: {e.read().decode()[:300]}"}}
    if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):  # SSE framing, take the last data line
        raw = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")][-1]
    return json.loads(raw)


def text_result(mid, text, is_error=False):
    return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}


def public_groq(mid, query):
    try:
        with urllib.request.urlopen(PUBLIC_GROQ + urllib.parse.urlencode({"query": query}), timeout=30) as r:
            res = json.load(r).get("result")
        return text_result(mid, json.dumps({"result": res, "note": "daily Context MCP budget used up; answered from the public dataset API"}, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        return text_result(mid, f"GROQ error: {e.read().decode()[:500]}", True)


def do_check(mid, args):
    ans = args.get("answer") or ""
    trace = [{"kind": "web"}] if args.get("searched_web") else []
    try:
        _, block, errs = answer_check.check(ans, trace, {})
    except Exception as ex:  # base unreachable etc. — say so, do not pretend it passed
        return text_result(mid, json.dumps({"ok": False, "errors": [f"checker failed: {ex}"]}), True)
    b = block or {}
    summary = {"calculations_recomputed": len([c for c in b.get("calculations") or [] if isinstance(c, dict)]),
               "paths_walked": len(b.get("paths") or []), "paths_in_base": len(answer_check.base_facts()["paths"])}
    log("check", ok=not errs, n_err=len(errs), **summary)
    return text_result(mid, json.dumps({"ok": not errs, "errors": errs, "summary": summary}, ensure_ascii=False))


def handle(msg, ip):
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None: return None  # notification
    if method == "initialize":
        r = upstream(msg)
        if "result" in r:
            r["result"]["serverInfo"] = {"name": "ai-hardware-advisor", "version": "1.0"}
            r["result"]["instructions"] = ("AI hardware advisor over a Sanity knowledge base. Call `initial_context` first: "
                                           "it returns the advisor instructions and the schema. Before showing an answer, "
                                           "validate it with `check_answer`.")
        return r
    if method == "ping": return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        r = upstream(msg)
        for t in r.get("result", {}).get("tools", []):
            t.setdefault("annotations", {})["readOnlyHint"] = True
            t.pop("execution", None)
        r.get("result", {}).setdefault("tools", []).append(CHECK_TOOL)
        return r
    if method == "tools/call":
        name, args = msg.get("params", {}).get("name"), msg.get("params", {}).get("arguments") or {}
        log("call", ip=ip, tool=name, q=str(args.get("query", ""))[:300])
        if name == "check_answer": return do_check(mid, args)
        if name == "initial_context" and _ctx_cache["body"] and _ctx_cache["t"] > time.time() - 600 and _ctx_cache["d"] == time.strftime("%Y-%m-%d"):
            return text_result(mid, _ctx_cache["body"])
        if not take_upstream():
            if name == "groq_query": return public_groq(mid, args.get("query", ""))
            return text_result(mid, "Daily budget of this free demo is used up; try tomorrow, or groq_query still works.", True)
        r = upstream(msg)
        if name == "initial_context" and "result" in r:
            body = f"Today is {time.strftime('%Y-%m-%d')}.\n\n" + PROMPT + "\n\n---\n\n" + "".join(c.get("text", "") for c in r["result"].get("content", []))
            _ctx_cache.update(t=time.time(), body=body, d=time.strftime("%Y-%m-%d"))
            return text_result(mid, body)
        return r
    return upstream(msg)  # resources/list, prompts/list, … — whatever Sanity supports


STATIC = {"/setup.md": ("setup.md", "text/markdown; charset=utf-8"), "/SKILL.md": ("SKILL.md", "text/markdown; charset=utf-8"),
          "/llms.txt": ("llms.txt", "text/plain; charset=utf-8")}


def tool_text(name, args, ip):
    """Run one MCP tool through handle() and return (text, is_error) — for the plain HTTP API."""
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, ip)
    if "error" in r: return r["error"].get("message", "error"), True
    res = r.get("result", {})
    return "".join(c.get("text", "") for c in res.get("content", [])), bool(res.get("isError"))


class H(BaseHTTPRequestHandler):
    server_version = "hw-advisor"

    def ip(self):
        raw = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        return hashlib.sha256(SALT + raw.encode()).hexdigest()[:10]

    def send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Mcp-Session-Id, Mcp-Protocol-Version, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body: self.wfile.write(body)

    def do_OPTIONS(self): self.send(204)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"): return self.send(200, open(INDEX, "rb").read(), "text/html; charset=utf-8")
        if p == "/health": return self.send(200, json.dumps({"ok": True, "upstream_today": _day["n"], "cap": PER_DAY_UPSTREAM}).encode())
        if p == "/mcp": return self.send(405, b"", extra={"Allow": "POST"})
        if p in STATIC:
            f, ct = STATIC[p]; return self.send(200, open(os.path.join(HERE, f), "rb").read(), ct)
        if p.startswith("/api/"): return self.api(p, {k: v[-1] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()})
        self.send(404, b"not found", "text/plain")

    def do_DELETE(self): self.send(405, b"", extra={"Allow": "POST"})

    def api(self, p, q):
        ip = self.ip()
        if not allow_ip(ip): return self.send(429, b"Too many requests from you this hour.", "text/plain")
        if p == "/api/context": text, err = tool_text("initial_context", {}, ip)
        elif p == "/api/query":
            if not q.get("q"): return self.send(400, b"Pass a GROQ query in ?q=", "text/plain")
            text, err = tool_text("groq_query", {"query": q["q"]}, ip)
        elif p == "/api/schema": text, err = tool_text("schema_explorer", {"type": q.get("type", "")}, ip) if q.get("type") else ("Pass ?type=<documentType>", True)
        elif p == "/api/part":
            d, n, t = q.get("draft", "")[:40], q.get("n", ""), q.get("text", "")
            if not d or not n.isdigit() or not t: return self.send(400, b"Pass draft=<any id>&n=<1,2,3...>&text=<URL-encoded piece>", "text/plain")
            with _lock:
                for k in [k for k, v in _drafts.items() if v["t"] < time.time() - 3600]: del _drafts[k]
                if len(_drafts) > 500 or int(n) > 60: return self.send(429, b"too many drafts/parts", "text/plain")
                e = _drafts.setdefault(d, {"t": time.time(), "parts": {}}); e["parts"][int(n)] = t; e["t"] = time.time()
                total = sum(len(x) for x in e["parts"].values())
            text, err = f"stored part {n} of draft {d}: {len(e['parts'])} parts, {total} chars. When all parts are sent: /api/check?draft={d}", False
        elif p == "/api/check" and q.get("draft") and not q.get("answer"):
            e = _drafts.get(q["draft"][:40])
            if not e: return self.send(404, b"No such draft (parts expire after 1 hour). Send it with /api/part first.", "text/plain")
            ans = "".join(e["parts"][k] for k in sorted(e["parts"]))
            text, err = tool_text("check_answer", {"answer": ans, "searched_web": str(q.get("searched_web", "")).lower() in ("1", "true", "yes")}, ip)
            text = f"(checked draft {q['draft']}: {len(e['parts'])} parts joined in order, {len(ans)} chars)\n" + text
        elif p == "/api/check":
            if not q.get("answer"): return self.send(400, b"Pass the draft answer (with its ```check block) in ?answer= or POST JSON {answer, searched_web}", "text/plain")
            text, err = tool_text("check_answer", {"answer": q["answer"], "searched_web": str(q.get("searched_web", "")).lower() in ("1", "true", "yes")}, ip)
        else: return self.send(404, b"not found", "text/plain")
        self.send(400 if err else 200, text.encode(), "text/plain; charset=utf-8")

    def do_POST(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/"):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY: return self.send(413, b"body size", "text/plain")
            try: body = json.loads(self.rfile.read(n))
            except ValueError: return self.send(400, b"POST JSON", "text/plain")
            return self.api(p, {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in body.items()} if isinstance(body, dict) else {})
        if p != "/mcp": return self.send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY: return self.send(413, b'{"error":"body size"}')
        ip = self.ip()
        if not allow_ip(ip):
            return self.send(429, json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32029, "message": "Too many requests from you this hour."}}).encode())
        try: msg = json.loads(self.rfile.read(n))
        except ValueError: return self.send(400, b'{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"parse error"}}')
        try:
            out = [r for r in (handle(m, ip) for m in msg) if r] if isinstance(msg, list) else handle(msg, ip)
        except Exception as ex:
            log("error", err=repr(ex)[:300])
            out = {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None, "error": {"code": -32603, "message": "internal error"}}
        if not out: return self.send(202)
        self.send(200, json.dumps(out, ensure_ascii=False).encode())

    def log_message(self, *a): pass


if __name__ == "__main__":
    try:  # the daily budget survives restarts: count today's upstream calls from the log
        with open(os.path.join(LOG_DIR, time.strftime("%Y-%m-%d") + ".jsonl")) as f:
            _day.update(d=time.strftime("%Y-%m-%d"), n=sum('"kind": "up"' in l for l in f))
    except FileNotFoundError: pass
    srv = ThreadingHTTPServer((os.environ.get("BIND", "127.0.0.1"), int(os.environ.get("PORT", 9890))), H)
    srv.daemon_threads = True
    srv.serve_forever()
