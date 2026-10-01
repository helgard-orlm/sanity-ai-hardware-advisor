"""Architect check R16 — does the SCHEMA cover what the base's own laws and rules use?
Every path in law.variables[].takeFrom, rule.check.left/right and rule.appliesWhen must be a real field
(type.field or type.list.field) or a situationTemplate key; every law formula must be one Python expression
over exactly its variable names. Run before filling and after every fill pass.  python3 coverage.py [dataset]"""
import ast, json, os, re, sys, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); DS = sys.argv[1] if len(sys.argv) > 1 else "v2"
S = json.load(open(os.path.join(HERE, "schema.json")))
DOCS = {t["name"]: t for t in S if t["type"] == "document" and not t["name"].startswith("sanity.")}
INLINE = {t["name"]: t["value"] for t in S if t["type"] == "type"}

def g(q):
    u = f"https://onwa0wvs.api.sanity.io/v2025-09-01/data/query/{DS}?" + urllib.parse.urlencode({"query": q})
    return json.load(urllib.request.urlopen(u, timeout=30))["result"]

def attrs(node):
    """field map of an object-ish schema node (follows inline types, arrays, unions of objects)."""
    k = node.get("type")
    if k == "inline": return attrs(INLINE.get(node["name"], {}))
    if k == "array": return attrs(node.get("of", {}))
    if k == "union": return {n: v for o in node.get("of", []) for n, v in attrs(o).items()}
    if k in ("object", "document"): return {n: v["value"] for n, v in node.get("attributes", {}).items() if not n.startswith("_")}
    return {}

def path_ok(p, situation_keys):
    p = p.strip()
    if p.startswith("constant"): return re.fullmatch(r"constant\s+-?[\d.]+(e-?\d+)?", p) is not None
    parts = p.split(".")
    if parts[0] == "situation": return len(parts) == 2 and parts[1] in situation_keys
    if parts[0] not in DOCS: return False
    node = DOCS[parts[0]]
    for f in parts[1:]:
        a = attrs(node)
        if f not in a: return False
        node = a[f]
    return True

def is_path(s):  # literal vs path on the right side of a rule
    return bool(re.fullmatch(r"[a-zA-Z]+(\.[a-zA-Z]+)+", s or "")) and s.split(".")[0] in set(DOCS) | {"situation"}

# Architect-written PROPERTY tests for laws: not exact numbers, but directions any correct formula must have.
# (law id, variable, direction when that variable grows: +1 result grows, -1 result falls)
PROPS = {
    "law-weights-memory": [("bits", +1)],
    "law-own-vs-rent-breakeven": [("electricityPrice", +1), ("averageWatts", +1), ("cloudHourly", -1), ("hardwarePrice", +1)],
}
# a usage-hours variable must exist in the breakeven law (renting is paid per hour USED, not 24 h)
NEEDS_VAR = {"law-own-vs-rent-breakeven": ["hours"]}

def law_properties():
    errs = []
    laws = {d["_id"]: d for d in g('*[_type=="law"]{_id, formula, variables}')}
    for lid, props in PROPS.items():
        d = laws.get(lid)
        if not d: continue
        names = [v["name"] for v in d.get("variables") or []]
        base = {n: 10.0 for n in names}
        try:
            f = lambda env: eval(compile(ast.parse(d["formula"], mode="eval"), lid, "eval"), {"__builtins__": {}}, env)
            r0 = f(base)
            for var, sign in props:
                hit = [n for n in names if n.lower() == var.lower()]
                if not hit: continue
                r1 = f(dict(base, **{hit[0]: 20.0}))
                if (r1 - r0) * sign <= 0:
                    errs.append(f"{lid}: when {hit[0]} grows the result should {'grow' if sign > 0 else 'fall'}, but the formula does the opposite (check signs: e.g. own electricity reduces the saving vs renting, so it must be SUBTRACTED from the monthly cloud cost)")
        except Exception as e: errs.append(f"{lid}: formula cannot be evaluated: {e}")
    for lid, parts in NEEDS_VAR.items():
        d = laws.get(lid)
        if d and not any(p in v["name"].lower() for v in d.get("variables") or [] for p in parts):
            errs.append(f"{lid}: needs a usage-hours-per-day variable (rent is paid only for the hours used; never assume 24 h/day)")
    return errs

def main():
    sit = {i["key"] for d in g('*[_type=="situationTemplate"]') for i in d.get("items", [])}
    errs, n = [], 0
    for law in g('*[_type=="law"]{_id, formula, variables}'):
        names = [v.get("name") for v in law.get("variables") or []]
        try:
            used = {x.id for x in ast.walk(ast.parse(law.get("formula") or "", mode="eval")) if isinstance(x, ast.Name)}
            if used != set(names): errs.append(f"{law['_id']}: formula names {sorted(used)} != variables {sorted(names)}")
        except SyntaxError: errs.append(f"{law['_id']}: formula is not one Python expression: {law.get('formula')!r}")
        for v in law.get("variables") or []:
            n += 1
            if not path_ok(v.get("takeFrom") or "", sit): errs.append(f"{law['_id']}: variable {v.get('name')} takeFrom {v.get('takeFrom')!r} is not a field of the schema")
    for r in g('*[_type=="rule"]{_id, check, appliesWhen}'):
        c = r.get("check") or {}
        sides = [c.get("left")] + ([c.get("right")] if is_path(c.get("right")) else [])
        if r.get("appliesWhen"): sides.append(r["appliesWhen"].split()[0])
        for s in sides:
            n += 1
            if not path_ok(s or "", sit): errs.append(f"{r['_id']}: path {s!r} is not a field of the schema")
    errs += law_properties()
    print(f"coverage: {n} paths checked, {len(errs)} problems")
    for e in errs: print(" -", e)
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
