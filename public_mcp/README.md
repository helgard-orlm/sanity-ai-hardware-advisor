# Public "bring your own agent" endpoint

Live: https://hw-advisor.helgardorlm.tech — MCP URL `https://hw-advisor.helgardorlm.tech/mcp` (streamable HTTP, no login).

Anyone can connect their own agent (ChatGPT developer mode, Claude, Claude Code, Codex, Cursor). Their model and
subscription do the reasoning; this small stdlib-only server:

- forwards MCP calls to the real **Sanity Context MCP** for project `onwa0wvs`, dataset `v2` (embeddings on),
  adding the access token server-side;
- prepends the advisor instructions (`prompt_public.md`) to `initial_context`;
- adds the tool **`check_answer`**: the same validator as the app (`../v2/answer_check.py`) — recomputes every
  calculation with the `law.formula` stored in Sanity, requires a verdict for every `solutionPath`, rejects
  substitute products and prices without date/region/source;
- rate-limits per visitor and per day; past the daily cap `groq_query` falls back to the public dataset API.

Run: `SANITY_CONTEXT_TOKEN=… PORT=9890 python3 server.py` (copy `../v2/answer_check.py` next to it).

Agents that can only open links get the same tools as plain HTTPS: `/api/context`, `/api/query?q=`, `/api/schema?type=`,
`/api/check` (POST, or GET via `/api/part?draft=&n=&text=` pieces + `/api/check?draft=`). See `llms.txt`, `setup.md` and `SKILL.md`
(skill file for Claude Code / Codex).

**Known limit:** `check_answer` checks numbers, completeness, sources and identity. It does not check whether a verdict
makes sense. In one outside test an agent marked "MoE experts in RAM" as *yes* for a dense model, and the check passed.
