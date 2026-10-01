"""MCP server for the FILLER model: read + validated write into the v2 dataset.
Tools: initial_context / schema_explorer / groq_query / create_document / patch_document.
Validation (our "architect" guard): known type, known fields (recursive), id without dots,
status "confirmed" forbidden, sources required, references as plain ids. Every call is logged."""
import json, os, re, sys, urllib.error, urllib.parse, urllib.request, uuid
from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); from secrets_env import tok
P, V = "onwa0wvs", "v2025-09-01"
DS = os.environ.get("SANITY_DATASET", "v2")
LOG = os.environ.get("MCP_LOG")
TOKEN = tok("SANITY_WRITE_TOKEN")
SCHEMA = {t["name"]: t for t in json.load(open(os.path.join(HERE, "schema.json"))) if t["type"] == "document" and not t["name"].startswith("sanity.")}
NO_SOURCES = {"source", "situationTemplate", "derivedConcept"}
mcp = FastMCP("sanity-fill")

def _log(tool, args, out):
    if LOG:
        with open(LOG, "a") as f: f.write(json.dumps({"tool": tool, "args": args, "out": out[:3000]}, ensure_ascii=False) + "\n")

def _api(path, body=None, params=None):
    url = f"https://{P}.api.sanity.io/{V}/data/{path}/{DS}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e: return {"error": e.read().decode()[:1500]}

# ---- schema-driven normalisation + validation ----

INLINE = {t["name"]: t["value"] for t in json.load(open(os.path.join(HERE, "schema.json"))) if t["type"] == "type"}

def _ref(value, path, errs):
    if isinstance(value, dict) and "_ref" in value: rid = value["_ref"]
    elif isinstance(value, str): rid = value
    else: errs.append(f"{path}: reference must be a document id string"); return value
    return {"_type": "reference", "_ref": rid}

def _is_ref(spec):
    if spec.get("type") == "inline": return spec["name"].endswith(".reference")
    if spec.get("type") == "union": return all(_is_ref(o) for o in spec.get("of", []))
    if spec.get("type") == "object": return "rest" in spec and _is_ref(spec["rest"])
    return False

def _norm(value, spec, path, errs):
    """spec = schema.json node. Turns plain ids into references, adds _key to array items, rejects unknown fields/values."""
    k = spec.get("type")
    if _is_ref(spec): return _ref(value, path, errs)
    if k == "inline": return _norm(value, INLINE.get(spec["name"], {}), path, errs)
    if k == "union":
        lits = [o["value"] for o in spec.get("of", []) if "value" in o]
        if lits and value not in lits: errs.append(f"{path}: {value!r} not in {lits}")
        return value
    if k == "array":
        if not isinstance(value, list): errs.append(f"{path}: must be a list [ ... ]" + (" of objects {fields:[...], source:\"<source _id>\", confidence, note}" if path.endswith("fieldSources") else "")); return value
        out = [_norm(v, spec.get("of", {}), f"{path}[{i}]", errs) for i, v in enumerate(value)]
        return [dict(x, _key=x.get("_key") or uuid.uuid4().hex[:12]) if isinstance(x, dict) else x for x in out]
    if k == "object":
        a = {n: v["value"] for n, v in spec.get("attributes", {}).items()}
        if not isinstance(value, dict): errs.append(f"{path}: must be an object with fields {[n for n in a if not n.startswith('_')]}"); return value
        out = {}
        for fk, fv in value.items():
            if fk.startswith("_"): out[fk] = fv; continue
            if fk not in a: errs.append(f"{path}.{fk}: no such field (allowed: {[n for n in a if not n.startswith('_')]})"); continue
            out[fk] = _norm(fv, a[fk], f"{path}.{fk}", errs)
        return out
    if k == "number" and not isinstance(value, (int, float)): errs.append(f"{path}: must be a number, got {value!r}")
    if k == "boolean" and not isinstance(value, bool): errs.append(f"{path}: must be true/false")
    return value

def _validate(doc, partial=False):
    errs = []
    t = doc.get("_type")
    if t not in SCHEMA: return None, [f"unknown _type {t!r}; types: {sorted(SCHEMA)}"]
    if "_id" in doc and not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,120}", doc["_id"]):
        errs.append("_id: lowercase letters, digits and dashes only (a dot makes the document private)")
    if doc.get("status") == "confirmed": errs.append("status: 'confirmed' is set only by a human")
    attrs = SCHEMA[t]["attributes"]
    out = {"_type": t}
    if "_id" in doc: out["_id"] = doc["_id"]
    for k, v in doc.items():
        if k in ("_type", "_id"): continue
        if k.startswith("_"): continue
        if k not in attrs: errs.append(f"{k}: no such field on {t} (allowed: {[x for x in attrs if not x.startswith('_')]})"); continue
        out[k] = _norm(v, attrs[k]["value"], k, errs)
    # paths in rules/laws must name real schema fields (v1 defect: psu/os/user types that did not exist)
    paths = []
    if t == "rule":
        c = doc.get("check") or {}
        paths += [("check.left", c.get("left")), ("check.right", c.get("right"))]
        aw = str(doc.get("appliesWhen") or "").split()
        if aw: paths.append(("appliesWhen", aw[0]))
    if t == "law":
        paths += [(f"variables[{i}].takeFrom", v.get("takeFrom")) for i, v in enumerate(doc.get("variables") or []) if isinstance(v, dict)]
    for where, p in paths:
        m = re.fullmatch(r"([A-Za-z]+)\.([A-Za-z]+)(?:\.[A-Za-z]+)*", str(p or ""))
        if not m or m.group(1) == "situation": continue
        typ, fld = m.group(1), m.group(2)
        if typ not in SCHEMA: errs.append(f"{where}: '{p}' — no document type '{typ}' (types: {sorted(SCHEMA)} or situation.<key>)")
        elif fld not in SCHEMA[typ]["attributes"]: errs.append(f"{where}: '{p}' — {typ} has no field '{fld}'; if it is needed, write a derivedConcept 'schema lacks field'")
    if t == "aiModel" and all(isinstance(doc.get(k), (int, float)) for k in ("numLayers", "numKvHeads", "headDim", "kvBytesPerToken")):
        law = 2 * doc["numLayers"] * doc["numKvHeads"] * doc["headDim"] * 2  # K and V, fp16 = 2 bytes
        note = json.dumps(doc.get("fieldSources") or "", ensure_ascii=False).lower()
        if abs(doc["kvBytesPerToken"] - law) / law > 0.05 and not any(w in note for w in ("mla", "hybrid", "mamba", "sliding")):
            errs.append(f"kvBytesPerToken {doc['kvBytesPerToken']} != 2 (K,V) * numLayers * numKvHeads * headDim * 2 bytes = {law}. "
                        "If the architecture differs (MLA, hybrid/Mamba, sliding window), explain it in fieldSources.note with a source.")
    if t == "law" and doc.get("formula") is not None:
        import ast
        f = str(doc["formula"])
        try:
            names = {n.id for n in ast.walk(ast.parse(f, mode="eval")) if isinstance(n, ast.Name)}
            declared = {v.get("name") for v in doc.get("variables") or [] if isinstance(v, dict)}
            if not partial or doc.get("variables") is not None:
                if names - declared: errs.append(f"formula uses {sorted(names - declared)} not declared in variables[].name {sorted(declared)}")
        except SyntaxError:
            errs.append("formula: must be ONE Python expression (no '=' or ';'); two results = two laws")
    for i, v in enumerate(doc.get("variables") or []) if t == "law" else []:
        tf = str((v or {}).get("takeFrom") or "")
        if tf.startswith("constant") and not re.fullmatch(r"constant -?[0-9.]+(e-?[0-9]+)?", tf):
            errs.append(f"variables[{i}].takeFrom: constant must be a number only, e.g. 'constant 1.2' (got {tf!r}); a value that depends on the model is a path, not a constant")
    if not partial and t not in NO_SOURCES and not doc.get("sources"):
        errs.append("sources: at least one source reference is required (create the source document first)")
    url = str(doc.get("url") or "")
    if t == "source" and url and (not re.match(r"https?://\S+\.\S+", url) or "..." in url):
        errs.append("url: not a full URL; if you did not open the page, leave url empty and set kind 'unverified'")
    return out, errs

# ---- tools ----

@mcp.tool()
def initial_context() -> str:
    """Your task (fill prompt) + compact schema + current counts. Call first."""
    counts = _api("query", params={"query": "{" + ",".join(f'"{n}":count(*[_type=="{n}"])' for n in SCHEMA) + "}"}).get("result", {})
    lines = []
    for n, t in SCHEMA.items():
        lines.append(f"- {n} [{counts.get(n, '?')}]: " + ", ".join(k for k in t["attributes"] if not k.startswith("_")))
    out = open(os.path.join(HERE, "prompt_fill.md")).read() + "\n\n# Schema (type [count]: fields) — call schema_explorer for descriptions\n" + "\n".join(lines)
    _log("initial_context", {}, out); return out

@mcp.tool()
def schema_explorer(type: str) -> str:
    """Field list with descriptions and allowed values for one document type."""
    src = open(os.path.join(HERE, "schemaTypes", "index.ts")).read()
    m = re.search(rf"export const {re.escape(type)} = defineType\(\{{(.*?)\n\}}\)", src, re.S)
    out = m.group(1) if m else json.dumps({"error": f"no type {type}", "types": sorted(SCHEMA)})
    _log("schema_explorer", {"type": type}, out); return out

@mcp.tool()
def groq_query(query: str) -> str:
    """Run a GROQ query against the dataset, e.g. *[_type=="gpu"]{_id,name}. Use it to avoid duplicates."""
    r = _api("query", params={"query": query})
    out = json.dumps({"result": r.get("result"), "error": r.get("error")}, ensure_ascii=False)
    _log("groq_query", {"query": query}, out); return out

@mcp.tool()
def create_document(document: dict) -> str:
    """Create or replace one document. Give _type, a readable _id (lowercase, dashes, no dots) and fields.
    References: give the target document _id as a plain string (or list of strings)."""
    doc, errs = _validate(document)
    if errs: out = json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)
    else:
        doc.setdefault("_id", f'{doc["_type"].lower()}-{uuid.uuid4().hex[:8]}')
        r = _api("mutate", {"mutations": [{"createOrReplace": doc}]}, {"returnIds": "true"})
        out = json.dumps({"ok": "error" not in r, "_id": doc["_id"], "error": r.get("error")}, ensure_ascii=False)
    _log("create_document", {"document": document}, out); return out

@mcp.tool()
def patch_document(id: str, type: str, set: dict) -> str:
    """Set some fields on an existing document (same validation as create)."""
    doc, errs = _validate({"_type": type, **set}, partial=True)
    if errs: out = json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)
    else:
        doc.pop("_type")
        r = _api("mutate", {"mutations": [{"patch": {"id": id, "set": doc}}]})
        out = json.dumps({"ok": "error" not in r, "error": r.get("error")}, ensure_ascii=False)
    _log("patch_document", {"id": id, "set": set}, out); return out

if __name__ == "__main__":
    mcp.run()
