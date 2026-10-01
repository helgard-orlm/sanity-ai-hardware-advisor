"""READ-ONLY MCP for the ANSWERING model over dataset v2 — same tool names as Sanity Context MCP
(initial_context / schema_explorer / groq_query). initial_context = prompt_use.md + schema + counts.
Stand-in until a second Context MCP endpoint is created for dataset v2 in Sanity Manage."""
import json, os, re, urllib.error, urllib.parse, urllib.request
from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__))
P, V, DS = "onwa0wvs", "v2025-09-01", os.environ.get("SANITY_DATASET", "v2")
LOG = os.environ.get("MCP_LOG")
SNAP = os.environ.get("SNAPSHOT")  # NDJSON export → answer from a frozen "before" state via local groq-js
SCHEMA_JSON = os.environ.get("SCHEMA_JSON", "schema.json"); SCHEMA_TS = os.environ.get("SCHEMA_TS", "index.ts")
SCHEMA = {t["name"]: t for t in json.load(open(os.path.join(HERE, SCHEMA_JSON))) if t["type"] == "document" and not t["name"].startswith("sanity.")}
mcp = FastMCP("sanity-context")

def _log(tool, args, out):
    if LOG:
        with open(LOG, "a") as f: f.write(json.dumps({"tool": tool, "args": args, "out": out[:4000]}, ensure_ascii=False) + "\n")

def groq(q):
    if SNAP:
        import subprocess
        p = subprocess.run(["node", os.path.join(HERE, "groq_local.mjs"), SNAP], input=q, capture_output=True, text=True, timeout=60, cwd=HERE)
        try: return json.loads(p.stdout)
        except ValueError: return {"error": (p.stdout + p.stderr)[:1500]}
    url = f"https://{P}.api.sanity.io/{V}/data/query/{DS}?" + urllib.parse.urlencode({"query": q})
    try: return json.load(urllib.request.urlopen(url, timeout=30))
    except urllib.error.HTTPError as e: return {"error": e.read().decode()[:1500]}

@mcp.tool()
def initial_context() -> str:
    """Instructions for answering + compressed schema + document counts. Call first."""
    counts = groq("{" + ",".join(f'"{n}":count(*[_type=="{n}"])' for n in SCHEMA) + "}").get("result", {})
    out = (open(os.path.join(HERE, os.environ.get("PROMPT_USE", "prompt_use.md"))).read() + "\n\n# Schema (type [count]: fields)\n" +
           "\n".join(f"- {n} [{counts.get(n, '?')}]: " + ", ".join(k for k in t["attributes"] if not k.startswith("_")) for n, t in SCHEMA.items()))
    _log("initial_context", {}, out); return out

@mcp.tool()
def schema_explorer(type: str) -> str:
    """Field descriptions and allowed values for one document type."""
    src = open(os.path.join(HERE, "schemaTypes", SCHEMA_TS)).read()
    m = re.search(rf"export const {re.escape(type)} = defineType\(\{{(.*?)\n\}}\)", src, re.S)
    out = m.group(1) if m else json.dumps({"error": f"no type {type}", "types": sorted(SCHEMA)})
    _log("schema_explorer", {"type": type}, out); return out

@mcp.tool()
def groq_query(query: str) -> str:
    """Run a GROQ query (read-only). References: use -> to follow, e.g. *[_type=="runReport"]{..., model->{name}, gpu->{name}}."""
    r = groq(query); res = r.get("result")
    out = json.dumps({"result": res, "meta": {"resultCount": len(res) if isinstance(res, list) else None, "error": r.get("error")}}, ensure_ascii=False)
    _log("groq_query", {"query": query}, out); return out

if __name__ == "__main__":
    mcp.run()
