"""
app.py — Streamlit BI analyst demo for the AtScale semantic layer.

A user types a natural-language BI question; Claude (claude-sonnet-4-6) works
with the 16 mqo-mcp-server tools to build a Multidimensional Query Object, run
it against the live cluster, and emit a Vega-Lite chart that renders inline.
The conversation is refinable ("break that down by month", "add a filter", ...).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import anthropic
import streamlit as st

from mcp_bridge import MODEL_PATH, McpBridge, McpError

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 12

# Sampled from the TPC-DS 100-NLQ failure-mode corpus; bundled so the demo is
# self-contained and does not depend on the mcp-tuner repo at runtime.
NLQ_PATH = Path(__file__).parent / "tpcds_nlq.json"
NUM_SUGGESTIONS = 3


@st.cache_data
def _load_nlq() -> list[str]:
    """Load the bundled TPC-DS natural-language questions (cached for the process)."""
    try:
        questions = json.loads(NLQ_PATH.read_text())
    except Exception:  # noqa: BLE001 — missing/corrupt file degrades gracefully to no chips
        return []
    return [q for q in questions if isinstance(q, str) and q.strip()]


def _sample_questions(k: int = NUM_SUGGESTIONS) -> list[str]:
    """A fresh random mix of k questions from the corpus."""
    pool = _load_nlq()
    return random.sample(pool, min(k, len(pool))) if pool else []


def _render_suggestions() -> None:
    """Render clickable example-question chips that seed the input on click.

    The chosen question is stashed in ``_pending_q`` and consumed by ``main``
    on the next rerun, so a click behaves exactly like typing + submitting.
    """
    if "sample_qs" not in st.session_state:
        st.session_state.sample_qs = _sample_questions()
    samples = st.session_state.sample_qs
    if not samples:
        return
    st.caption("Try one of these — or type your own below:")
    for i, question in enumerate(samples):
        if st.button(question, key=f"suggest_{i}", use_container_width=True):
            st.session_state._pending_q = question
            # Keep the same chips on screen — re-sampling here makes the button
            # the user just clicked appear to change to a different question,
            # which is disconcerting. The set is sampled once per session.
            st.rerun()

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

GOVERNED DATASET HANDLES (read this — it is how this server works)
query_multidimensional does NOT hand you the rows to do math on. It executes the
query on the AtScale cluster, stores the result on the server, and returns a
GOVERNED HANDLE:
  - "summary": a typed column inventory — each column has "name" (the exact,
    fully-qualified identifier, e.g. "sold_date_dimensions.[Sold Calendar Year]"),
    "role" ("Dimension" or "Measure"), and server-computed stats.
  - "handle": an opaque id (e.g. "hdl_…") naming the stored result.
  - "capabilities": the operations available on this handle.
  - "rows": present ONLY for small results; for anything larger the rows stay on
    the server and are omitted. DO NOT rely on rows, and NEVER compute a total,
    ranking, average, or filter yourself — the server owns the numbers. You
    orchestrate handles; you never recompute.

THE PIPELINE (follow this for every question)
  1. (First question only) optionally call describe_model once to ground yourself.
  2. query_multidimensional with the right MQO → you get back {{summary, handle, capabilities}}.
  3. To visualize, read summary.columns: pick the Dimension column as x and the
     Measure column(s) as y, then call:
        dataset_chart(handle=<handle id>, chart_type="bar"|"line"|"area"|"point",
                      x_col="<exact column name from summary>",
                      y_cols=["<exact measure column name from summary>"])
     It returns a Vega-Lite v5 spec the UI renders automatically. Use the EXACT
     "name" strings from summary.columns — they are fully-qualified.
  4. ALWAYS finish a data turn by producing a chart via dataset_chart.

REFINEMENT (server-side, on the handle — never recompute yourself)
When the user refines, operate on the current handle with the dataset_* tools.
Each returns a NEW handle + summary; then chart the new handle with dataset_chart:
  - "top 10" / "bottom 5"        → dataset_top_n(handle, n, measure, dir="top"|"bottom")
  - "filter to 2001" / "> N"      → dataset_filter(handle, predicate)
  - "sort by revenue"             → dataset_sort(handle, keys)
  - "sum/avg by region"           → dataset_aggregate(handle, group_by, agg, measure)
  - "pivot" / "compare" / "drill"  → dataset_pivot / dataset_compare / dataset_drill
To change the MEASURE, the dimension level, or the time grain, issue a fresh
query_multidimensional with the modified MQO (you get a new handle), then chart it.

STYLE
Be concise. Let the chart speak — one or two sentences of insight is plenty. \
Always end a data turn by producing a chart via dataset_chart so the user sees \
a visualization. Never print raw numbers you computed yourself — every figure \
must come from the server (a summary stat or a dataset_* result).\
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

    _render_suggestions()

    typed = st.chat_input("Ask a BI question…")
    # A clicked suggestion (queued on the previous run) takes precedence.
    prompt = st.session_state.pop("_pending_q", None) or typed
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

    # Rotate the example chips and refresh the sidebar backend indicator.
    st.session_state.sample_qs = _sample_questions()
    st.rerun()


if __name__ == "__main__":
    main()
