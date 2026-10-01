"""Filler run: Luna (gpt-5.6-luna via codex, web search on) fills dataset v2 through mcp_fill.py.
Stages run in order (later stages reference earlier documents). Pilot sizes: enough to test, not full.
Usage: python3 fill_run.py [stage ...]   — default all. Logs: runs/<stage>.{mcp.jsonl,out.md,err.log}"""
import datetime, os, subprocess, sys, time
TODAY = datetime.date.today().isoformat()

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CH = os.path.join(ROOT, "luna_home"); CWD = os.path.join(ROOT, "luna_cwd"); RUNS = os.path.join(HERE, "runs")

STAGES = {
    "s1": "Stage 1 of 4. Create: the situationTemplate (one document), the laws (at least the six listed), "
          "and the eight useCases listed in the work order. Leave useCase.candidateModels empty for now.",
    "s2": "Stage 2 of 4. Create about 20 aiModels covering all existing useCases (query them first), from small "
          "(1-8B) to very large open MoE models, with real variants and file sizes; and the software runtimes they "
          "need (about 8). Then patch each useCase.candidateModels.",
    "s3": "Stage 3 of 4. Create about 16 gpus (NVIDIA, AMD, Intel; 8 GB to 32 GB and above; current and popular "
          "used), the cpus needed, and about 6 whole systems (Mac with unified memory, AMD unified-memory mini-PC, "
          "typical office SFF PC, a gaming laptop, a workstation).",
    "s4": "Stage 4 of 4. Create about 15 rules (only real paths), about 10 runReports from published benchmarks or "
          "clear user reports for models and cards already in the base, about 6 cloudOffers (API for the large "
          "models + hourly GPU rent), up to 4 failureCases, and offers for about 10 cards in regions US and UA.",
    "fix": "Review pass from the architect. The validator got stricter; fix these findings in existing documents "
           "(query first, patch or recreate with the same _id):\n"
           "1. Every law: formula must be ONE Python expression using exactly variables[].name; takeFrom = real path or "
           "'constant <number>'. Bits come from aiModel.variants.bits, never 'constant 4'. Split 'MoE memory versus speed' "
           "into two laws (memory from paramsTotalB; speed ceiling from paramsActiveB). The speed-ceiling law must say in "
           "validity that MoE uses active params. The KV law must use aiModel.numLayers, numKvHeads, headDim (or "
           "aiModel.kvBytesPerToken) and situation keys for context and concurrent users.\n"
           "2. New aiModel fields numLayers, numKvHeads, headDim, kvBytesPerToken: fill them for every aiModel from its "
           "config.json / model card (open it).\n"
           "3. Sources: AI-generated summaries (deepwiki etc.) must be kind 'reported'; where possible replace them with "
           "the official repo/paper and re-point references.\n"
           "4. Every law needs a workedExample with real numbers for a model that exists in the base.\n"
           "5. Do NOT add new models, cards or systems: the catalog is a set of reference examples, not a complete list. "
           "Finish items 1-4 for documents already in the base (skip those already fixed: query first).",
    "kvfix": "Architect check found: kvBytesPerToken is exactly HALF of 2 (K and V) * numLayers * numKvHeads * headDim "
             "* 2 bytes for 11 of 14 models. Re-check every aiModel: patch kvBytesPerToken together with numLayers, "
             "numKvHeads, headDim (the validator now checks consistency). Models with MLA (DeepSeek-V2/V3 family, Kimi-K2) "
             "or other non-standard attention: open the paper/config, write the real per-token KV size and explain in "
             "fieldSources.note with the source. Do not add new models.",
    "edits2": "Architect review after real user dialogues. Fix gaps in CRITERIA and reference examples, not in coverage:\n"
              "1. CHEAPEST PATH FOR LARGE MoE. The advisor offered only a 4xH200 server for a ~320B MoE and missed "
              "high-memory machines. Add reference systems with LARGE unified or system memory: Apple Mac Studio with the "
              "largest unified memory currently sold, an AMD unified-memory system with 128 GB, and a CPU server/workstation "
              "class with 384-768 GB RAM (server CPUs with many memory channels). Fill memBandwidthGBs for each.\n"
              "2. COMMUNITY QUANTIZED VARIANTS. For every aiModel above 30B total params, look up widely used community "
              "quantizations (GGUF Q4_K_M / Q8, MLX 4-bit) and add them to variants with real file sizes (open the page). "
              "Official-only variants hide the cheap path.\n"
              "3. Add a rule: large MoE models whose quantized weights exceed VRAM can run from system/unified memory; "
              "speed ceiling = memBandwidthGBs of that memory / active-params bytes per token (use existing laws). "
              "Severity 'degrades', consequence says it is slow but far cheaper than GPU servers.\n"
              "4. REFRESH TO TODAY. Reference examples must reflect the current generation as of today. For each useCase, "
              "check whether its candidateModels are still current; where a newer model of the same class and size has "
              "replaced one, REPLACE the example (create the new aiModel with releaseDate, re-point candidateModels) rather "
              "than adding more. Same for the gpu list: make sure each vendor's current generation is represented, "
              "replacing stale entries only where the old one is no longer sold new (keep popular used cards).\n"
              "Keep the catalog about the same size; finish with the report.",
    "v3": "Architect pass v3. Two jobs, in this order.\n"
          "A. COVERAGE DEFECTS found by the architect's code check (coverage.py). Fix them in place:\n"
          "  1. law-kv-cache-context takes contextTokens from situation.typicalContextTokens, but the situationTemplate has "
          "no such key. Patch the situationTemplate: add item typicalContextTokens (number, priority 2, plain question, why = "
          "KV cache law, defaultIfUnknown = a stated default). Also add usageFrequency (string, priority 1: how often the "
          "model runs - daily hours / a few times a month; why = own vs rent decision).\n"
          "  2. rule-ram-model-offload and rule-unified-memory use aiModel.variants.fileSizeGb; the real field is "
          "aiModel.variants.fileGb. Patch both rules.\n"
          "  3. Add ONE law 'own vs rent breakeven': months until buying costs less than renting/API, from a hardware price, "
          "a monthly cloud cost and monthly electricity. Real variables only (situation keys, cloudOffer fields, offer.price), "
          "worked example with numbers from offers and cloudOffers already in the base.\n"
          "B. SOLUTION PATHS. Create exactly one solutionPath per pathClass (11 documents, ids solution-path-<pathClass>). "
          "Read schema_explorer(solutionPath) first. fitsWhen / failsWhen with numbers (e.g. cpu-ram-offload-moe fits when a "
          "MoE model's total weights exceed any affordable VRAM but active params are small; speed ceiling = system memory "
          "bandwidth / active bytes per token). Link decidingLaws, decidingRules, software and examples ONLY to documents "
          "that already exist (query first). If a path needs a runtime that is missing from the base (for example a runtime "
          "that keeps MoE experts in system RAM and attention on the GPU), you MAY create that one software document with "
          "sources. Do not add models, cards or systems.\n"
          "Finish with the report: what you created/patched, and every place where you were unsure.",
    "v3fix": "The architect's code check (coverage.py, property tests of laws) rejected law-own-vs-rent-breakeven:\n"
             "- when electricityPrice or averageWatts grows, breakeven months must GROW (own electricity reduces the monthly saving "
             "vs renting, so it is SUBTRACTED from the monthly cloud cost, not added);\n"
             "- renting is paid only for the hours actually used: the law needs a variable for usage hours per day (never 24 h/day).\n"
             "Fix: add situationTemplate item usageHoursPerDay (number, priority 2, plain question, why = own vs rent + electricity, "
             "defaultIfUnknown stated). Patch the law: breakeven months = hardwarePrice / (monthly cloud cost for the used hours - "
             "monthly electricity of the owned machine for the same hours); say in validity that if the denominator is <= 0 buying "
             "never pays off. Recompute workedExample with real numbers from the base (e.g. 3 h/day). Patch "
             "law-electricity-monthly-cost the same way if it assumes 24 h without a variable. Do not create other documents.",
}

def run(stage):
    os.makedirs(RUNS, exist_ok=True)
    log, out, err = (f"{RUNS}/{stage}.{x}" for x in ("mcp.jsonl", "out.md", "err.log"))
    cfg = ["-c", 'mcp_servers.fill.command="python3"',
           "-c", f'mcp_servers.fill.args=["{HERE}/mcp_fill.py"]',
           "-c", f'mcp_servers.fill.env={{MCP_LOG="{log}", SANITY_DATASET="v2"}}',
           "-c", 'mcp_servers.fill.default_tools_approval_mode="approve"',
           "-c", 'mcp_servers.fill.tool_timeout_sec=120']
    prompt = (f"Today is {TODAY}. " "You have a Sanity knowledge base connected via the MCP server \"fill\". Call initial_context first: "
              "it contains your full task and the schema. Use web search to find sources. Do not use shell or files.\n\n"
              + STAGES[stage] + "\nFinish with the short report described in the task.")
    t = time.time()
    p = subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", "gpt-5.6-luna",
                        *cfg, "-o", out, "-"], input=prompt, capture_output=True, text=True, cwd=CWD,
                       env=dict(os.environ, CODEX_HOME=CH), timeout=5400)
    open(err, "w").write(p.stderr[-30000:])
    print(f"{stage}: rc={p.returncode} {round(time.time() - t)}s", flush=True)
    return p.returncode

if __name__ == "__main__":
    for s in sys.argv[1:] or list(STAGES):
        if run(s) != 0: sys.exit(1)
