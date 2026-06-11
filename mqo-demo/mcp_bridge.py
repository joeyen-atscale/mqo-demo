"""
mcp_bridge.py — a minimal stdio JSON-RPC client for the mqo-mcp-server binary.

Spawns the binary as a subprocess, performs the MCP handshake (initialize →
notifications/initialized), and exposes list_tools() / call_tool(). One request
maps to one response, newline-delimited JSON, strictly sequential.

Server stderr is teed to a log file so failures are not swallowed silently.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

# ── Live cluster configuration (from the demo brief) ───────────────────────────

BINARY = "/Users/jsy/Documents/projects/target/release/mqo-mcp-server"
CATALOG = "/Users/jsy/Documents/projects/mqo-mcp-server/fixtures/tpcds_catalog.json"
ENDPOINT = "mcp-aws.atscaleinternal.com:15432"
XMLA_URL = "https://mcp-aws.atscaleinternal.com/v1/xmla"
OIDC_TOKEN_URL = (
    "https://mcp-aws.atscaleinternal.com/auth/realms/atscale/protocol/"
    "openid-connect/token"
)
OIDC_CLIENT_ID = "atscale-mcp"
OIDC_REALM = "atscale"  # derived from the realm segment of OIDC_TOKEN_URL
OIDC_SECRET_ENV = "ATSCALE_OIDC_SECRET"

# The live binder resolves MQO models by their short name (as returned by
# list_models), NOT the fully-qualified atscale_catalogs.<schema>.<model> path —
# the latter has no XMLA catalog/cube mapping and fails with xmla_coords_not_found.
MODEL_PATH = "tpcds_benchmark_model"

STDERR_LOG = Path("/tmp/mqo-mcp-server.stderr.log")


class McpError(Exception):
    """Raised when the server returns isError:true or a JSON-RPC error."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


def server_args() -> list[str]:
    return [
        BINARY,
        "--catalog", CATALOG,
        "--endpoint", ENDPOINT,
        "--xmla-url", XMLA_URL,
        "--oidc-token-url", OIDC_TOKEN_URL,
        "--oidc-client-id", OIDC_CLIENT_ID,
        "--oidc-realm", OIDC_REALM,
        "--oidc-client-secret-env", OIDC_SECRET_ENV,
    ]


class McpBridge:
    """A sequential stdio JSON-RPC client around the mqo-mcp-server binary."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._lock = threading.Lock()
        self._stderr_fh = None
        self._stderr_thread: threading.Thread | None = None
        self.server_info: dict[str, Any] = {}

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.is_alive():
            return

        env = os.environ.copy()
        env.setdefault(OIDC_SECRET_ENV, "atscale")

        self._stderr_fh = open(STDERR_LOG, "ab", buffering=0)

        self.proc = subprocess.Popen(
            server_args(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,
        )

        # Pump the subprocess stderr to the log file in the background so it is
        # never swallowed and never blocks the pipe.
        def _pump() -> None:
            assert self.proc and self.proc.stderr
            for chunk in iter(lambda: self.proc.stderr.readline(), b""):
                try:
                    if self._stderr_fh:
                        self._stderr_fh.write(chunk)
                except Exception:
                    break

        self._stderr_thread = threading.Thread(target=_pump, daemon=True)
        self._stderr_thread.start()

        # Give the process a moment; if it died instantly, surface it.
        time.sleep(0.1)
        if self.proc.poll() is not None:
            raise McpError(
                "ServerExited",
                f"server exited immediately (code {self.proc.returncode}); "
                f"see {STDERR_LOG}",
            )

        self._handshake()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self._stderr_fh:
            try:
                self._stderr_fh.close()
            except Exception:
                pass
            self._stderr_fh = None
        self.proc = None

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # ── JSON-RPC plumbing ───────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _write(self, payload: dict[str, Any]) -> None:
        if not self.is_alive():
            raise McpError("ServerDead", "the MCP server subprocess is not running")
        assert self.proc and self.proc.stdin
        line = json.dumps(payload) + "\n"
        self.proc.stdin.write(line.encode("utf-8"))
        self.proc.stdin.flush()

    def _read_response(self) -> dict[str, Any]:
        """Read newline-delimited JSON lines until a non-notification arrives."""
        assert self.proc and self.proc.stdout
        while True:
            raw = self.proc.stdout.readline()
            if raw == b"":
                code = self.proc.poll()
                raise McpError(
                    "ServerDead",
                    f"server closed stdout (exit code {code}); see {STDERR_LOG}",
                )
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # Not JSON (stray log line on stdout) — skip it.
                continue
            # Responses have an id; server-originated notifications do not.
            if "id" in msg or "error" in msg:
                return msg
            # Ignore notifications addressed to us.

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            req_id = self._next_id()
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params or {},
                }
            )
            resp = self._read_response()

        if "error" in resp:
            err = resp["error"]
            raise McpError(
                str(err.get("code", "jsonrpc_error")),
                err.get("message", json.dumps(err)),
            )
        return resp.get("result", {})

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._write(
                {"jsonrpc": "2.0", "method": method, "params": params or {}}
            )

    # ── MCP protocol ─────────────────────────────────────────────────────────────

    def _handshake(self) -> None:
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mqo-demo", "version": "0.1.0"},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return result.get("tools", [])

    # Chart tools whose inputs need the live DAX rows normalized to clean,
    # human-readable column labels so the profiler/emitter can classify and
    # reference fields (live rows arrive with XML-mangled keys like
    # `Sold_date_dimensions_x005b_...` that don't match the bound's unique_names).
    _CHART_TOOLS = {"recommend_chart", "build_vega_spec", "build_bi_asset"}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool. Returns structuredContent (preferred) or the text content.

        Raises McpError when the response carries isError:true.
        """
        if name in self._CHART_TOOLS:
            arguments = _normalize_chart_arguments(name, arguments)

        result = self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )

        if result.get("isError"):
            code, message = _extract_error_detail(result)
            raise McpError(code, message)

        if "structuredContent" in result:
            return result["structuredContent"]

        # Fall back to the unstructured text content array.
        content = result.get("content", [])
        for block in content:
            if block.get("type") == "text":
                text = block.get("text", "")
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return text
        return result


# ── Live-DAX row normalization ─────────────────────────────────────────────────


def _decode_xml_name(s: str) -> str:
    """Undo SSAS/XMLA name-mangling: _xHHHH_ → the corresponding character."""
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), s)


def _clean_label(raw_key: str) -> str:
    """Turn a (possibly XML-mangled) column key into a friendly label.

    Prefers the contents of the last [...] segment (the level/measure name);
    falls back to the decoded string with separators trimmed.
    """
    decoded = _decode_xml_name(raw_key)
    bracketed = re.findall(r"\[([^\]]+)\]", decoded)
    if bracketed:
        return bracketed[-1].strip()
    return decoded.strip("._ ")


def _label_from_unique_name(unique_name: str) -> str:
    """Friendly label for a bound unique_name (`hier.[Level]` or `model.measure`)."""
    bracketed = re.findall(r"\[([^\]]+)\]", unique_name)
    if bracketed:
        return bracketed[-1].strip()
    # e.g. tpcds_benchmark_model.total_store_sales → "total store sales" → Title
    tail = unique_name.rsplit(".", 1)[-1]
    return tail.replace("_", " ").strip()


def _normalize_response(response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (normalized_rows, clean_bound) from a query_multidimensional payload.

    Row keys are remapped to clean labels; the bound is reduced to
    {measures: [labels], dimensions: [labels]} so the profiler classifies columns
    by role (dimension vs measure) rather than by value type — important because
    year levels are numeric and would otherwise look like measures.
    """
    rows = response.get("rows") or response.get("page") or []
    bound = response.get("bound") or {}

    if not rows:
        return [], {"measures": [], "dimensions": []}

    keys = list(rows[0].keys())
    label_for = {k: _clean_label(k) for k in keys}

    # Build the clean bound from the bound's unique_names so dim/measure roles
    # are authoritative.
    dim_labels = [
        _label_from_unique_name(d.get("unique_name", ""))
        for d in bound.get("dimensions", [])
        if d.get("unique_name")
    ]
    meas_labels = [
        _label_from_unique_name(m.get("unique_name", ""))
        for m in bound.get("measures", [])
        if m.get("unique_name")
    ]

    # Fallback when the bound is empty/odd: classify by value type.
    known = set(label_for.values())
    if not dim_labels and not meas_labels:
        for k in keys:
            lbl = label_for[k]
            if isinstance(rows[0][k], (int, float)):
                meas_labels.append(lbl)
            else:
                dim_labels.append(lbl)
    else:
        # Keep only labels that actually appear as columns; append any stragglers.
        dim_labels = [d for d in dim_labels if d in known]
        meas_labels = [m for m in meas_labels if m in known]
        accounted = set(dim_labels) | set(meas_labels)
        for k in keys:
            lbl = label_for[k]
            if lbl not in accounted:
                (meas_labels if isinstance(rows[0][k], (int, float)) else dim_labels).append(lbl)
                accounted.add(lbl)

    new_rows = [{label_for[k]: r.get(k) for k in keys} for r in rows]
    clean_bound = {"measures": meas_labels, "dimensions": dim_labels}
    return new_rows, clean_bound


def _normalize_chart_arguments(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Rewrite chart-tool arguments to use normalized rows + a clean bound.

    Each tool accepts a different argument shape:
      - recommend_chart / build_bi_asset: `response` OR `rows`+`bound`
      - build_vega_spec:                  `response` OR `recommendation`+`rows`

    So for build_vega_spec we normalize the rows *inside* the response (keeping
    the response shape), and for the others we expand `response` into the
    `rows`+`bound` form the profiler wants. Either way the row keys end up as
    clean labels that match what recommend_chart referenced.
    """
    args = dict(arguments)

    if tool == "build_vega_spec":
        if isinstance(args.get("response"), dict):
            rows, bound = _normalize_response(args["response"])
            resp = dict(args["response"])
            resp["rows"] = rows
            resp["bound"] = bound
            resp.pop("page", None)  # avoid a stale mangled page shadowing rows
            args["response"] = resp
        elif isinstance(args.get("rows"), list) and args["rows"]:
            synth = {"rows": args["rows"], "bound": {}}
            rows, _ = _normalize_response(synth)
            args["rows"] = rows
        return args

    # recommend_chart / build_bi_asset → emit rows + clean bound
    if isinstance(args.get("response"), dict):
        rows, bound = _normalize_response(args["response"])
        args.pop("response", None)
        args["rows"] = rows
        args["bound"] = bound
        return args

    if isinstance(args.get("rows"), list) and args["rows"]:
        synth = {"rows": args["rows"], "bound": args.get("bound", {})}
        rows, bound = _normalize_response(synth)
        args["rows"] = rows
        if bound.get("measures") or bound.get("dimensions"):
            args["bound"] = bound

    return args


def _extract_error_detail(result: dict[str, Any]) -> tuple[str, str]:
    """Return (code, message) from an isError tool result.

    Handles both the flat shape ({"error": "...", "detail": "..."}) and the
    enveloped shape ({"error": {"code": "...", "detail": {...}}}) the server
    emits for infrastructure errors.
    """
    payload: Any = result.get("structuredContent")
    if not isinstance(payload, dict):
        payload = None
        for block in result.get("content", []):
            if block.get("type") == "text":
                try:
                    parsed = json.loads(block.get("text", ""))
                    payload = parsed if isinstance(parsed, dict) else {"detail": parsed}
                except (json.JSONDecodeError, TypeError):
                    payload = {"detail": block.get("text", "")}
                break
    if not isinstance(payload, dict):
        return ("ToolError", "unknown tool error")

    # Unwrap the {"error": {...}} envelope when present.
    inner = payload.get("error")
    if isinstance(inner, dict):
        code = str(inner.get("code", "ToolError"))
        message = _flatten_detail(inner.get("detail")) or json.dumps(inner)
        return (code, message)

    code = str(payload.get("error") or payload.get("code") or "ToolError")
    message = _flatten_detail(payload.get("detail")) or payload.get("message") or json.dumps(payload)
    return (code, str(message))


def _flatten_detail(detail: Any) -> str:
    """Turn a string-or-nested-dict 'detail' into a human-readable message."""
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        # Common nesting: {"detail": "...", "model": "..."}.
        if isinstance(detail.get("detail"), str):
            return detail["detail"]
        return json.dumps(detail)
    return str(detail)
