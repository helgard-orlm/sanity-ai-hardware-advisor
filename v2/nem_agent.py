"""Run the acceptance scenarios with Nemotron-3.5 30B (local llama.cpp server :9803, OpenAI chat API with tools) as the advisor,
through the REAL Sanity Context MCP on dataset v2 — same instructions (prompt_use_v31) and same code validator
(answer_check, up to 2 fix rounds) as the v31real arm. No web search (hosted tool is OpenAI-only).
Sessions are saved in the probe format so grade.py can blind-grade them.
Usage: python3 nem_agent.py <tag> [repeats=1] [scenario ids...]"""
import asyncio, json, os, sys, time, uuid, urllib.request
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from secrets_env import tok
import answer_check
NEM = os.environ.get("NEM_URL", "http://127.0.0.1:9803/v1/chat/completions")
MCP_URL = os.environ.get("MCP_URL", "https://api.sanity.io/v2026-02-27/context/mcp/onwa0wvs/v2")
SESS = os.path.join(ROOT, "probe", "data", "sessions"); RES = os.path.join(HERE, "acceptance", "results")
MAX_TOOL_CALLS, ROUNDS, CLIP = int(os.environ.get("MAX_CALLS", 20)), 2, int(os.environ.get("CLIP", 12000))
MODEL = os.environ.get("NEM_MODEL", "nemotron-30b")

PLAIN = os.environ.get("PLAIN") == "1"  # KB-mode test: the endpoint's own instructions, no check block, no validator

def preface():
    if PLAIN:
        return (f"Today is {time.strftime('%Y-%m-%d')}. You are an AI hardware advisor. Your source is the knowledge base behind the MCP tools: "
                "call initial_context first, then search and read entries. You have no web search. Answer in the language of the user's last message. "
                "Do not ask questions; state assumptions. Show the numbers.")
    return (f"Today is {time.strftime('%Y-%m-%d')}. Your knowledge source is the Sanity Context MCP tools (call initial_context first). "
            "You have NO web search in this setup: for anything not in the base, say its values are unknown and give conditions. "
            "The APP INSTRUCTIONS below are your working instructions and take priority over the generic text returned by "
            "initial_context: you MUST compute with the base's laws and run its rules. Answer in the language of the user's last message.\n"
            "MODE: direct answer. Do not ask questions; turn unknowns into explicit conditions.\n\n# APP INSTRUCTIONS\n"
            + open(os.path.join(HERE, "prompt_use_v31.md")).read())

def chat(messages, tools):
    body = {"model": MODEL, "stream": False, "messages": messages, "tools": tools, "max_tokens": int(os.environ.get("MAX_TOKENS", 8192))}
    r = urllib.request.Request(NEM, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=1800))

async def agent_turn(sess, tools, messages, trace, t0):
    calls = 0
    while True:
        d = chat(messages, tools); msg = d["choices"][0]["message"]
        tcs = msg.get("tool_calls") or []
        messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": tcs} if tcs else {})})
        if not tcs:
            trace.append({"kind": "final", "finish_reason": d["choices"][0].get("finish_reason"), "content_len": len(msg.get("content") or ""),
                          "reasoning_tail": (msg.get("reasoning_content") or "")[-1500:], "usage": d.get("usage")})
            return msg.get("content") or ""
        if calls >= MAX_TOOL_CALLS:  # budget used: force the final answer without tools
            messages.pop()
            messages.append({"role": "user", "content": f"You have used all {MAX_TOOL_CALLS} tool calls for this answer. "
                             "Do not call tools. Write the final answer now from what you already retrieved" + ("." if PLAIN else ", ending with the ```check block.")})
            d = chat(messages, [])
            m0 = d["choices"][0]; final = m0["message"].get("content") or ""
            trace.append({"kind": "final", "finish_reason": m0.get("finish_reason"), "content_len": len(final),
                          "reasoning_tail": (m0["message"].get("reasoning_content") or "")[-1500:], "usage": d.get("usage")})
            messages.append({"role": "assistant", "content": final})
            return final
        for tc in tcs:
            calls += 1; name = tc["function"]["name"]
            try: args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError: args = {}
            try:
                r = await sess.call_tool(name, args)
                out = "\n".join(getattr(c, "text", "") for c in r.content)
            except Exception as e: out = f"ERROR: {e}"
            trace.append({"kind": "base", "tool": name, "args": args, "result": out[:20000], "t": round(time.time() - t0, 1)})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": out[:CLIP]})

async def run_scenario(sc):
    s = {"id": uuid.uuid4().hex[:12], "created": time.time(), "messages": []}; situation = {}
    hdr = {"Authorization": f"Bearer {tok('SANITY_CONTEXT_TOKEN')}"}
    async with streamablehttp_client(MCP_URL, headers=hdr) as (r, w, _):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            tools = [{"type": "function", "function": {"name": t.name, "description": (t.description or "")[:1500],
                      "parameters": t.inputSchema}} for t in (await sess.list_tools()).tools]
            for text in sc["turns"]:
                s["messages"].append({"role": "user", "text": text, "t": time.time()})
                hist = "".join(("User: " if m["role"] == "user" else "Assistant: ") + m["text"] + "\n\n" for m in s["messages"][:-1])
                sit = ("Stored situation (validated by the app from earlier turns):\n" + json.dumps(situation) + "\n\n") if situation else ""
                messages = [{"role": "system", "content": preface()},
                            {"role": "user", "content": sit + (("Conversation so far:\n\n" + hist) if hist else "") + "User: " + text}]
                msg = {"role": "assistant", "text": "", "trace": [], "status": "running", "started": time.time(),
                       "mode": {"base": True, "web": False, "db": "kb-plain" if PLAIN else "v31real", "win": "direct", "model": MODEL, "effort": "default"}}
                t0 = time.time(); ans = await agent_turn(sess, tools, messages, msg["trace"], t0)
                msg["validator"] = []; block = None; visible = ans
                for rnd in range(0 if PLAIN else ROUNDS + 1):
                    visible, block, errs = answer_check.check(ans, msg["trace"], situation)
                    msg["validator"].append({"round": rnd, "errors": errs})
                    if not errs or rnd == ROUNDS: break
                    messages.append({"role": "user", "content": "The app's validator (code, checking your answer against the base) found these problems:\n- "
                                     + "\n- ".join(errs) + "\n\nWrite the FULL corrected answer for the person (not a diff), with the ```check block at the end. Use the tools as needed."})
                    ans = await agent_turn(sess, tools, messages, msg["trace"], t0)
                if block and isinstance(block.get("situation"), dict): situation = block["situation"]
                msg.update(text=visible, check=block, status="done", sec=round(time.time() - t0, 1))
                s["messages"].append(msg)
    s["situation"] = situation
    json.dump(s, open(os.path.join(SESS, s["id"] + ".json"), "w"), ensure_ascii=False, indent=1)
    return s["id"]

async def main():
    tag = sys.argv[1]; reps = int(sys.argv[2]) if len(sys.argv) > 2 else 1; ids = sys.argv[3:]
    scs = [x for x in json.load(open(os.path.join(HERE, "acceptance", "scenarios.json")))["scenarios"] if not ids or x["id"] in ids]
    out = {}
    for sc in scs:
        for _ in range(reps):
            t = time.time()
            try: sid = await run_scenario(sc)
            except Exception as e: print(sc["id"], "FAILED", repr(e)[:300], flush=True); continue
            out.setdefault(sc["id"], []).append(sid); print(sc["id"], sid, f"{time.time() - t:.0f}s", flush=True)
            json.dump({"model": MODEL, "sessions": out}, open(os.path.join(RES, f"{tag}.json"), "w"), indent=1)

if __name__ == "__main__":
    asyncio.run(main())
