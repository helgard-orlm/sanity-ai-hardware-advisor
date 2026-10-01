# AI hardware advisor on Sanity Context MCP

An agent that answers "what computer do I need to run *this* AI model?" — including "don't buy, rent" and
"you already have enough". It reads a Sanity dataset of **criteria** (laws, rules, solution paths, run reports,
reference hardware), not a product catalog, and code recomputes its math from the laws stored in Sanity.

- Sanity project `onwa0wvs`, public dataset `v2` (200 documents), embeddings enabled
- Studio: https://hw-for-ai-lab-v2.sanity.studio
- Agent connection: Sanity Context MCP `https://api.sanity.io/v2026-02-27/context/mcp/onwa0wvs/v2`
- Second entry: Knowledge Base `kbW7wsbtJQkl` (Context MCP in KB mode, 138 core documents)
- **Replay of real runs** (no model on the page, every tool call / validator round / answer as recorded): https://helgard-orlm.github.io/sanity-ai-hardware-advisor/
- Results: blind grader 47/78 (v2) → 53/78 (v3) → **59/78 (v3.1 via Sanity Context MCP)**, 9 scenarios × 3 — `v2/acceptance/results/`

## Layout

| path | what |
|---|---|
| `v2/schemaTypes/index.ts`, `v2/schema.json` | schema: aiModel, gpu, cpu, system, law, rule, solutionPath, runReport, offer, cloudOffer, useCase, situationTemplate, software, failureCase, source |
| `v2/prompt_fill.md`, `v2/fill_run.py`, `v2/mcp_fill.py` | the base was filled by a model from an empty schema through a write-MCP with schema validation |
| `v2/coverage.py` | checks the base itself: every law variable / rule path is a real schema field, laws pass property tests (direction of change) |
| `v2/prompt_use_v31.md` | app instructions for the advisor (all paths, rules as search checklist, hidden check block) |
| `v2/answer_check.py` | validator: recomputes every calculation from `law.formula`, checks required fields and dated prices, sends the answer back (≤2 rounds) |
| `probe/server.py`, `probe/index.html` | chat page; runs the advisor via Codex CLI with Sanity Context MCP attached |
| `v2/acceptance/` | 9 scenarios written before the changes, runner, blind grader with a frozen checklist |
| `v2/mcp_read.py`, `v2/groq_local.mjs`, `v2/text_kb.py` | control arms: local snapshot reader, plain-text base |
| `v2/nem_agent.py` | the same loop for a local model behind an OpenAI-compatible chat API |

## Run

Tokens go to `~/.config/sanity_live/env` (`SANITY_CONTEXT_TOKEN=…`, `SANITY_WRITE_TOKEN=…`) or environment variables.
Never commit them.

```
python3 probe/server.py                       # http://127.0.0.1:8930
cd v2/acceptance
DB=v31real python3 run.py mytag luna 3        # 9 scenarios × 3
python3 grade.py mytag                        # blind grading → results/mytag.graded.json
```
