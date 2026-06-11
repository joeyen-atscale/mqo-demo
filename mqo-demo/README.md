# mqo-demo — Live Streamlit BI Analyst for AtScale MQO MCP Server

**TL;DR:** Type a plain-English BI question, get a governed Vega-Lite chart in under 15 seconds.  
`mqo-demo` wraps the `mqo-mcp-server` binary in a Streamlit chat UI driven by `claude-sonnet-4-6`.  
It demonstrates the full MQO → semantic layer → DAX → chart pipeline in a live, interactive setting.

Verified working 2026-06-11: 16 tools connected, full DAX pipeline (6 year-rows) → VL5 bar chart.

---

## Install

**Prerequisites**

- Python 3.10+
- Prebuilt `mqo-mcp-server` binary at `../target/release/mqo-mcp-server` (workspace artifact)
- `ANTHROPIC_API_KEY` in your environment
- `ATSCALE_OIDC_SECRET` in your environment (defaults to `atscale` if unset)

```bash
# From the mqo-demo directory:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Start**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ATSCALE_OIDC_SECRET="atscale"   # or your secret
./start.sh
```

`start.sh` prefers `.venv/bin/streamlit` if the venv exists, otherwise falls back to `streamlit` on `PATH`.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI + Claude `claude-sonnet-4-6` tool-use loop (max 12 iterations) |
| `mcp_bridge.py` | stdio JSON-RPC bridge — spawns server subprocess, handles MCP handshake, decodes XMLA column keys |
| `requirements.txt` | `anthropic>=0.28.0`, `streamlit>=1.35.0` |
| `start.sh` | Venv-preferring launcher; sets env var defaults |

---

## Acceptance Tests

| # | Test | Expected |
|---|---|---|
| AC-1 | Run `./start.sh` with `ANTHROPIC_API_KEY` + `ATSCALE_OIDC_SECRET=atscale` set | Streamlit starts; sidebar shows **● Connected** with **16 tools** |
| AC-2 | Type "Show total store sales by year" | Bar chart of **6 data points** renders within **15 seconds** |
| AC-3 | After a chart, type "break it down by quarter instead" | Updated quarterly chart renders — no page reload |
| AC-4 | Make a query with the backend unreachable | Error message with failure reason appears — no Python traceback |
| AC-5 | After a successful query | Sidebar shows `backend: dax` and the active model path |
| AC-6 | Run with no `ANTHROPIC_API_KEY` | First message shows "API key not configured" — no traceback |
| AC-7 | Server returns a valid Vega-Lite v5 spec | `st.vega_lite_chart()` renders it inline in the chat thread |
| AC-8 | Click **Reconnect** in the sidebar | New bridge subprocess spawns; tool list refreshes to 16 |

**Golden number:** "Total Store Sales by year" MUST return 6 rows totaling **10,169,858,384.28**.

---

## Architecture

```
User (browser) ──► Streamlit app.py
                        │
                        ▼
              Anthropic claude-sonnet-4-6
              (tool-use loop, max 12 iter)
                        │  tool_use blocks
                        ▼
                  mcp_bridge.py
                  (stdio JSON-RPC)
                        │
                        ▼
            mqo-mcp-server (Rust binary)
                        │
                        ▼
        AtScale XMLA / DAX → tpcds_benchmark_model
```

The bridge decodes XML-mangled XMLA column keys (`_x005b_`→`[`, `_x0020_`→space) and classifies dimension/measure roles from the response `bound` field (not value type).

---

## Notes

- This is a **demo / POC only** — no authentication, no multi-user isolation.
- Not a Rust crate; `/autobuilder` and the 7-receipt gate do not apply.
- Server stderr is teed to `/tmp/mqo-mcp-server.stderr.log` for post-hoc diagnosis.
- `MODEL_PATH = "tpcds_benchmark_model"` (short form) — the FQ path fails with `xmla_coords_not_found`.
