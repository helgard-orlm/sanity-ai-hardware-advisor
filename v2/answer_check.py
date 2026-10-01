"""Architect's answer validator (v3). Code, not a model: checks the `check` block at the end of an answer against
the base and the trace of the turn. Risks closed: R2 every solutionPath walked, R3 no substitution / not in base
without search, R4 priority-1 keys stated, R5 known keys not dropped between turns.
check(text, trace, stored) -> (visible_text, block_or_None, errors[])"""
import json, os, re, time, urllib.parse, urllib.request
DS = os.environ.get("SANITY_DATASET", "v2"); _CACHE = {}

def groq(q):
    u = f"https://onwa0wvs.api.sanity.io/v2025-09-01/data/query/{DS}?" + urllib.parse.urlencode({"query": q})
    return json.load(urllib.request.urlopen(u, timeout=30))["result"]

def base_facts():
    if _CACHE.get("t", 0) > time.time() - 300: return _CACHE
    rule_fields = {}
    for r in groq('*[_type=="rule"]{check, appliesWhen}'):
        for side in [(r.get("check") or {}).get("left"), (r.get("check") or {}).get("right"), (r.get("appliesWhen") or "").split(" ")[0]]:
            if side and re.fullmatch(r"(gpu|cpu|system|aiModel|software)\.[A-Za-z.]+", side):
                t, f = side.split(".", 1); rule_fields.setdefault(t, set()).add(f)
    _CACHE.update(t=time.time(), rule_fields=rule_fields,
                  laws={d["_id"]: d for d in groq('*[_type=="law"]{_id, formula, variables}')},
                  paths={d["_id"] for d in groq('*[_type=="solutionPath"]{_id}')},
                  p1={i["key"] for d in groq('*[_type=="situationTemplate"]') for i in d.get("items", []) if i.get("priority") == 1})
    return _CACHE

def parse_amount(raw):
    """'41 268,06' / '41,268.06' / '0,99' / '2,000' / '1.234,5' -> float (European and US formats)."""
    r = re.sub(r"[\s\u00a0\u202f]", "", raw or "")
    if "," in r and "." in r:
        r = r.replace(".", "").replace(",", ".") if r.rfind(",") > r.rfind(".") else r.replace(",", "")
    elif "," in r:
        head, _, tail = r.rpartition(",")
        r = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    try: return float(r)
    except ValueError: return None

def norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())

BLOCK = re.compile(r"```check\s*(\{.*?\})\s*```", re.S)

def check(text, trace, stored=None):
    errs = []; stored = stored or {}
    m = BLOCK.search(text or "")
    visible = BLOCK.sub("", text or "").rstrip()
    if not m:
        return visible, None, ["The answer has no ```check block at the end. Add it exactly as described in the instructions."]
    try: b = json.loads(m.group(1))
    except ValueError as e: return visible, None, [f"The ```check block is not valid JSON ({e}). Rewrite it."]
    f = base_facts()
    # R2 — every path walked
    got = {p.get("id") for p in b.get("paths") or [] if isinstance(p, dict)}
    miss = sorted(f["paths"] - got)
    if miss: errs.append(f"You did not walk these solution paths: {miss}. Give each a verdict yes/no/maybe with one reason in numbers, in the answer and in the block.")
    for p in b.get("paths") or []:
        if isinstance(p, dict) and p.get("verdict") not in ("yes", "no", "maybe"): errs.append(f"Path {p.get('id')}: verdict must be yes/no/maybe.")
    # R3 — entities: exact base document or searched on the web
    web_calls = sum(1 for t in trace or [] if t.get("kind") == "web")
    ids = [e.get("baseId") for e in b.get("entities") or [] if isinstance(e, dict) and e.get("baseId")]
    names = {d["_id"]: d.get("name") or d.get("title") for d in (groq(f'*[_id in {json.dumps(ids)}]{{_id, name, title}}') if ids else [])}
    for e in b.get("entities") or []:
        if not isinstance(e, dict): continue
        n, bid = e.get("name", ""), e.get("baseId")
        if bid:
            if bid not in names: errs.append(f"Entity {n!r}: baseId {bid!r} does not exist in the base.")
            else:
                a, c = norm(n), norm(names[bid])
                if a and c and a not in c and c not in a:
                    errs.append(f"Entity {n!r} is mapped to base document {bid!r} named {names[bid]!r} — that is a DIFFERENT thing. "
                                f"Do not size with a substitute: look {n!r} up on the web by its type's checklist, or say its values are unknown.")
        else:
            if not e.get("web"): errs.append(f"Entity {n!r} is not in the base and has no web source. Search the web for it (official page / model card) or say its values are unknown.")
            elif web_calls == 0: errs.append(f"Entity {n!r} lists web sources but no web search happened in this turn. Actually search, or remove the claim.")
    # R6 — an entity NOT in the base must carry every field the base's rules test for its kind (the rules are the search checklist)
    for e in b.get("entities") or []:
        if isinstance(e, dict) and not e.get("baseId") and e.get("kind") in f["rule_fields"]:
            facts = e.get("facts") or {}
            def has(d, path):  # "variants.fileGb" is found inside a list of variants too
                head, _, rest = path.partition(".")
                v = d.get(head) if isinstance(d, dict) else None
                if v is None: return path in d if isinstance(d, dict) else False
                if not rest: return True
                items = v if isinstance(v, list) else [v]
                return any(isinstance(i, dict) and has(i, rest) for i in items) or v == "unknown"
            miss = sorted(x for x in f["rule_fields"][e["kind"]] if not has(facts, x))
            if miss: errs.append(f"Entity {e.get('name')!r} ({e['kind']}) is not in the base, and the base's rules test these fields of a {e['kind']}: {miss}. "
                                 f"Look them up (web) and put them in entities[].facts with the value, or \"unknown\" if not found after searching; then run those rules in the answer.")
    # R9 — calculations are recomputed by code; key laws must actually be applied
    import ast
    calcs = [c for c in b.get("calculations") or [] if isinstance(c, dict)]
    used = set()
    for c in calcs:
        law = f["laws"].get(c.get("law"))
        if not law: errs.append(f"Calculation uses law {c.get('law')!r} which is not in the base."); continue
        used.add(law["_id"]); names = [v["name"] for v in law.get("variables") or []]
        ins = c.get("inputs") or {}
        miss = [n for n in names if n not in ins]
        if miss: errs.append(f"Calculation with {law['_id']}: inputs missing {miss} (formula: {law['formula']})."); continue
        try:
            val = eval(compile(ast.parse(law["formula"], mode="eval"), "law", "eval"), {"__builtins__": {}}, {n: float(ins[n]) for n in names})
            res = float(c.get("result"))
            if abs(val - res) > 0.03 * max(abs(val), 1e-9): errs.append(f"Calculation with {law['_id']}: with your inputs the formula gives {val:.4g}, you wrote {res:.4g}. Fix the number in the answer too.")
        except Exception as ex: errs.append(f"Calculation with {law['_id']}: cannot evaluate ({ex}); inputs must be numbers.")
    sized = [e for e in b.get("entities") or [] if isinstance(e, dict) and e.get("kind") == "aiModel"]
    if sized and not used & {"law-weights-memory", "law-moe-memory-vs-speed"}:
        errs.append("You size AI models but show no weights-memory calculation: add a calculation with law-weights-memory (params x bits / 8) for the model(s) you size.")
    cloud_ok = [p for p in b.get("paths") or [] if isinstance(p, dict) and str(p.get("id", "")).startswith("solution-path-cloud") and p.get("verdict") in ("yes", "maybe")]
    freq = (b.get("situation") or {}).get("usageFrequency") or {}
    if cloud_ok and isinstance(freq, dict) and freq.get("status") == "known" and "law-own-vs-rent-breakeven" in f["laws"] and "law-own-vs-rent-breakeven" not in used:
        errs.append("A cloud path is yes/maybe but there is no own-vs-rent calculation: add a calculation with law-own-vs-rent-breakeven (use the person's hours; state assumptions) and give the months or a multi-year total in the answer.")
    # prices — every money amount in the answer is a listed price (date+region+source) or a calculation input/result
    known = []
    for pz in b.get("prices") or []:
        if isinstance(pz, dict):
            if not (pz.get("date") and pz.get("region") and pz.get("source")): errs.append(f"Price for {pz.get('item')!r} needs date, region and source.")
            try: known.append(float(pz.get("amount")))
            except (TypeError, ValueError): pass
    for v in (b.get("situation") or {}).values():  # the person's own figures (budget...) are not prices
        try: known.append(float(v.get("value")))
        except (TypeError, ValueError, AttributeError): pass
    for c in calcs:
        for v in list((c.get("inputs") or {}).values()) + [c.get("result")]:
            try: known.append(float(v))
            except (TypeError, ValueError): pass
    for m2 in re.finditer(r"(?:[$€£]\s?([\d][\d,. \u00a0\u202f]*\d|\d)|\b([\d][\d,. \u00a0\u202f]*\d|\d)\s?(?:USD|EUR|UAH|PLN|zł|грн|\$|€))", visible):
        amt = parse_amount(m2.group(1) or m2.group(2))
        if amt is None: continue
        if amt < 1 or any(abs(amt - k) <= 0.02 * max(k, 1) for k in known): continue
        errs.append(f"Money amount {m2.group(0).strip()!r} in the answer has no entry in prices (item, amount, currency, region, date, source) and is not a calculation input/result.")
    # R4 — priority-1 keys stated
    sit = b.get("situation") or {}
    for k in sorted(f["p1"] - set(sit)): errs.append(f"Situation key {k!r} (priority 1) is missing: state it as known, assumed (with the value) or unknown.")
    for k, v in sit.items():
        if isinstance(v, dict) and v.get("status") == "assumed" and v.get("value") in (None, ""): errs.append(f"Situation key {k!r} is 'assumed' but has no value: write what you assumed.")
    # R5 — do not drop what was known
    for k, v in stored.items():
        if isinstance(v, dict) and v.get("status") == "known":
            nv = sit.get(k)
            if not isinstance(nv, dict) or nv.get("status") != "known":
                errs.append(f"Situation key {k!r} was known from earlier turns ({v.get('value')!r}) and is now dropped. Keep it, or say the person changed it.")
    return visible, b, errs
