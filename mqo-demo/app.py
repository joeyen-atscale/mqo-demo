"""
app.py — Streamlit BI analyst demo for the AtScale semantic layer.

A user types a natural-language BI question; Claude (claude-sonnet-4-6) works
with the 16 mqo-mcp-server tools to build a Multidimensional Query Object, run
it against the live cluster, and emit a Vega-Lite chart that renders inline.
The conversation is refinable ("break that down by month", "add a filter", ...).
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
import streamlit as st

from mcp_bridge import MODEL_PATH, McpBridge, McpError

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 12

SYSTEM_PROMPT = f"""\
You are a BI analyst assistant for AtScale, demonstrating natural-language \
analytics over a governed semantic layer. You answer business questions by \
driving a set of MCP tools that query AtScale's Universal Semantic Layer and \
produce charts — you never write SQL.

THE MODEL
The semantic model is TPC-DS benchmark data. Its fully-qualified model path is:
    {MODEL_PATH}
Always use this exact string for the "model" field of any MQO.

KEY MEASURES (use the unique_name verbatim):
  - Total Store Sales
  - Store Net Paid Amount
  - Store Net Profit
  - Catalog Net Paid Amount
  - Store Quantity Sold
  - Store Customer Count

KEY TIME DIMENSIONS (hierarchy "sold_date_dimensions"):
  - level "Sold Calendar Year"
  - level "Sold Quarter of Year"
  - level "Sold Calendar Month"

THE MQO (Multidimensional Query Object)
query_multidimensional takes an object {{"mqo": <MQO>}}. An MQO looks like:
{{
  "model": "{MODEL_PATH}",
  "measures": [{{"unique_name": "Total Store Sales"}}],
  "dimensions": [{{"hierarchy": "sold_date_dimensions", "level": "Sold Calendar Year"}}],
  "filters": [],
  "time_intelligence": [],
  "order": null,
  "limit": 100,
  "non_empty": true
}}

THE PIPELINE (follow this for every question)
  1. (First question only) optionally call list_models / describe_model once to \
ground yourself. Do NOT call list_models again on later turns — you already know the model.
  2. query_multidimensional with the right MQO. The response contains "rows" and \
"bound" (and possibly "page"/"cursor_id" for large results).
  3. recommend_chart — pass {{"rows": <rows>, "bound": <bound>}} from the query \
response so the profiler can classify the columns and pick a mark.
  4. build_vega_spec — ALWAYS finish here. Pass {{"recommendation": <rec>, "rows": \
<rows>}} (or {{"response": <full query response>}}). It returns a complete \
Vega-Lite v5 spec that the UI renders automatically.

You may also use build_bi_asset to do profile→recommend→emit in one call (it \
returns a "vega_spec"); compose_dashboard to lay out multiple assets.

REFINEMENT
When the user refines ("break it down by month", "add region", "just 2001", \
"sort descending", "show profit instead"), modify the MQO accordingly — add or \
swap a dimension level, add a filter, change the measure, set order/limit — then \
re-run query_multidimensional → recommend_chart → build_vega_spec.

STYLE
Be concise. Let the chart speak — one or two sentences of insight is plenty. \
Always end a data turn by producing a chart via build_vega_spec so the user sees \
a visualization.\
"""


# ── Session state / bridge bootstrap ───────────────────────────────────────────


def get_bridge() -> McpBridge:
    bridge: McpBridge | None = st.session_state.get("bridge")
    if bridge is None or not bridge.is_alive():
        bridge = McpBridge()
        bridge.start()
        st.session_state.bridge = bridge
        # Cache the Anthropic-format tools once per connection.
        st.session_state.tools = _to_anthropic_tools(bridge.list_tools())
    return bridge


def _to_anthropic_tools(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool dicts to Anthropic tool dicts (inputSchema → input_schema)."""
    out: list[dict[str, Any]] = []
    for t in mcp_tools:
        out.append(
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {"type": "object"}),
            }
        )
    return out


def get_client() -> anthropic.Anthropic:
    if "anthropic" not in st.session_state:
        st.session_state.anthropic = anthropic.Anthropic()
    return st.session_state.anthropic


# ── Vega-Lite detection ─────────────────────────────────────────────────────────


def extract_vega_spec(result: Any) -> dict[str, Any] | None:
    """Return a Vega-Lite spec from a tool result, or None."""
    if not isinstance(result, dict):
        return None
    # build_vega_spec / compose_dashboard return the spec directly.
    schema = result.get("$schema", "")
    if isinstance(schema, str) and "vega-lite" in schema:
        return result
    # build_bi_asset returns {vega_spec: <spec>}.
    spec = result.get("vega_spec")
    if isinstance(spec, dict):
        inner_schema = spec.get("$schema", "")
        if isinstance(inner_schema, str) and "vega-lite" in inner_schema:
            return spec
        # Accept even if $schema missing but it has mark+encoding.
        if "mark" in spec and "encoding" in spec:
            return spec
    # compose_dashboard concat spec.
    concat = result.get("vega_concat_spec")
    if isinstance(concat, dict):
        return concat
    return None


# ── Agentic tool loop ───────────────────────────────────────────────────────────


def run_turn(user_text: str) -> dict[str, Any]:
    """Run one user turn: drive Claude + tools to a final answer and chart.

    Returns {"text": str, "specs": [vega specs], "backend": str|None}.
    Appends the full turn (user + assistant + tool results) to the API history.
    """
    client = get_client()
    bridge = get_bridge()
    tools = st.session_state.tools

    history: list[dict[str, Any]] = st.session_state.api_messages
    history.append({"role": "user", "content": user_text})

    collected_specs: list[dict[str, Any]] = []
    backend_used: str | None = None
    last_mqo: dict[str, Any] | None = None
    final_text_parts: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=history,
        )

        # Record assistant turn verbatim (preserves tool_use blocks).
        history.append({"role": "assistant", "content": response.content})

        # Gather any final text in this assistant message.
        for block in response.content:
            if block.type == "text" and block.text.strip():
                final_text_parts.append(block.text.strip())

        if response.stop_reason != "tool_use":
            break

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = bridge.call_tool(block.name, block.input)
                # Track which backend a query used.
                if isinstance(result, dict) and result.get("backend"):
                    backend_used = result["backend"]
                # Capture the MQO from the most recent query.
                if block.name == "query_multidimensional":
                    last_mqo = block.input
                # Capture any chart spec produced.
                spec = extract_vega_spec(result)
                if spec is not None:
                    collected_specs.append(spec)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            except McpError as e:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(
                            {"error": e.code, "detail": e.detail}
                        ),
                        "is_error": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(
                            {"error": "unexpected_error", "detail": str(e)}
                        ),
                        "is_error": True,
                    }
                )

        history.append({"role": "user", "content": tool_results})

    return {
        "text": "\n\n".join(final_text_parts).strip() or "(no text response)",
        "specs": collected_specs,
        "backend": backend_used,
        "last_mqo": last_mqo,
    }


# ── UI ──────────────────────────────────────────────────────────────────────────


def render_message(msg: dict[str, Any]) -> None:
    with st.chat_message(msg["role"]):
        if msg.get("text"):
            st.markdown(msg["text"])
        for spec in msg.get("specs", []):
            try:
                st.vega_lite_chart(spec, use_container_width=True)
            except Exception as e:  # noqa: BLE001
                st.warning(f"Could not render chart: {e}")
                st.json(spec)
        if msg.get("error"):
            st.error(msg["error"])


def main() -> None:
    st.set_page_config(page_title="AtScale BI Analyst Demo", page_icon="📊", layout="wide")

    if "chat" not in st.session_state:
        st.session_state.chat = []          # display history
    if "api_messages" not in st.session_state:
        st.session_state.api_messages = []  # Anthropic API history
    if "last_backend" not in st.session_state:
        st.session_state.last_backend = None
    if "last_mqo" not in st.session_state:
        st.session_state.last_mqo = None

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Server")
        bridge_alive = False
        server_name = "—"
        connect_error: str | None = None
        try:
            bridge = get_bridge()
            bridge_alive = bridge.is_alive()
            server_name = bridge.server_info.get("name", "mqo-mcp-server")
        except (McpError, Exception) as e:  # noqa: BLE001
            connect_error = str(e)

        if bridge_alive:
            st.success("● Connected")
            st.caption(f"server: `{server_name}`")
            st.caption(f"tools: {len(st.session_state.get('tools', []))}")
        else:
            st.error("● Disconnected")
            if connect_error:
                st.caption(connect_error)

        st.divider()
        st.caption("Model (semantic layer)")
        st.code(MODEL_PATH, language=None)
        st.caption("LLM")
        st.code(MODEL, language=None)
        st.caption("Last query backend")
        st.code(st.session_state.last_backend or "—", language=None)

        st.divider()
        st.caption("Last query")
        if st.session_state.last_mqo:
            st.json(st.session_state.last_mqo, expanded=True)
        else:
            st.caption("—")

        st.divider()
        if st.button("Reconnect", use_container_width=True):
            old = st.session_state.get("bridge")
            if old:
                try:
                    old.stop()
                except Exception:
                    pass
            st.session_state.pop("bridge", None)
            st.session_state.pop("tools", None)
            st.rerun()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.chat = []
            st.session_state.api_messages = []
            st.session_state.last_backend = None
            st.session_state.last_mqo = None
            st.rerun()

    # ── Main ─────────────────────────────────────────────────────────────────
    st.title("📊 AtScale BI Analyst")
    st.caption(
        "Ask a business question in plain English — e.g. "
        "*“Show total store sales by year”* — then refine it conversationally."
    )

    for msg in st.session_state.chat:
        render_message(msg)

    prompt = st.chat_input("Ask a BI question…")
    if not prompt:
        return

    user_msg = {"role": "user", "text": prompt, "specs": []}
    st.session_state.chat.append(user_msg)
    render_message(user_msg)

    with st.chat_message("assistant"):
        with st.spinner("Querying the semantic layer…"):
            try:
                result = run_turn(prompt)
            except McpError as e:
                err_msg = {
                    "role": "assistant",
                    "text": "",
                    "specs": [],
                    "error": f"**[{e.code}]** {e.detail}",
                }
                st.session_state.chat.append(err_msg)
                st.error(err_msg["error"])
                return
            except Exception as e:  # noqa: BLE001
                err_msg = {
                    "role": "assistant",
                    "text": "",
                    "specs": [],
                    "error": f"Unexpected error: {e}",
                }
                st.session_state.chat.append(err_msg)
                st.error(err_msg["error"])
                return

        if result["backend"]:
            st.session_state.last_backend = result["backend"]
        if result["last_mqo"]:
            st.session_state.last_mqo = result["last_mqo"]

        assistant_msg = {
            "role": "assistant",
            "text": result["text"],
            "specs": result["specs"],
        }
        st.session_state.chat.append(assistant_msg)
        if assistant_msg["text"]:
            st.markdown(assistant_msg["text"])
        for spec in assistant_msg["specs"]:
            try:
                st.vega_lite_chart(spec, use_container_width=True)
            except Exception as e:  # noqa: BLE001
                st.warning(f"Could not render chart: {e}")
                st.json(spec)

    # Refresh the sidebar backend indicator.
    st.rerun()


if __name__ == "__main__":
    main()
