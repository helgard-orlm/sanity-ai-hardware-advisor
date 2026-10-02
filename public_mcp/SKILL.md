---
name: ai-hardware-advisor
description: Answer "what computer do I need to run this AI model / can my PC run it / buy, upgrade or rent?" from the AI Hardware Advisor knowledge base (Sanity) with the math checked by the base's own formulas. Use whenever someone asks about hardware, VRAM, RAM, GPUs or costs for running AI models locally.
---

# AI Hardware Advisor

Source of truth: the AI Hardware Advisor knowledge base, reachable two ways. Use the first one that works:

1. **MCP tools** from the server `hw-advisor` (`https://hw-advisor.helgardorlm.tech/mcp`):
   `initial_context`, `groq_query`, `schema_explorer`, `array_field_reader`, `check_answer`.
2. **Plain HTTPS** (no MCP needed, e.g. `curl` or a web fetch tool):
   - `GET https://hw-advisor.helgardorlm.tech/api/context`: the full advisor instructions plus the schema. Read it first.
   - `GET https://hw-advisor.helgardorlm.tech/api/query?q=<URL-encoded GROQ>`: query the base (read-only).
   - `GET https://hw-advisor.helgardorlm.tech/api/schema?type=<documentType>`: fields of one type.
   - `POST https://hw-advisor.helgardorlm.tech/api/check` with JSON `{"answer": "<draft with check block>", "searched_web": true|false}`.
     GET-only: send ~1500-char pieces with `GET /api/part?draft=<random id>&n=1&text=<URL-encoded>` (n=2, 3, …),
     then `GET /api/check?draft=<id>&searched_web=true|false`. It checks the whole joined draft; never check fragments.

## Steps
1. Load the context (`initial_context` or `/api/context`). It begins with today's date and the work order. Follow it.
2. Query the base for the situation template, laws, solution paths, rules and run reports. Always use projections.
3. Write the draft answer, ending with the ```check JSON block described in the context.
4. Validate it with `check_answer` or `/api/check`. Fix every error and validate again (at most 3 rounds).
5. Show the person the answer without the check block, and finish with
   "Checked against the base: N calculations recomputed, M paths walked".

Never size a request with a different model than the one the person named. Values that are not in the base come
from the web with a link, or stay "unknown".
