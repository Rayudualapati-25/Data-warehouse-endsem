import json
import os
import re
from typing import Any, Dict, Optional

from agent.executor import validate_sql
from agent.planner import Plan
from utils.env_loader import load_environments
from utils.hf_client import hf_generate


def _extract_json_blob(text: str) -> Dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    inline = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if inline:
        return json.loads(inline.group(0))

    return json.loads(text)


def _metadata_context(metadata: Dict[str, Any] | None) -> str:
    if not metadata:
        return "No dataset metadata provided."
    tables = metadata.get("tables", [])
    entities = metadata.get("entities", [])[:10]
    measures = metadata.get("measures", [])[:10]
    time_cols = metadata.get("time_columns", [])[:10]
    relationships = metadata.get("relationships", [])[:20]

    table_names = [t.get("table_name") for t in tables[:40]]
    entity_names = [f"{e.get('table')}.{e.get('column')}" for e in entities]
    measure_names = [f"{m.get('table')}.{m.get('column')}" for m in measures]
    time_names = [f"{t.get('table')}.{t.get('column')}" for t in time_cols]
    return (
        f"Allowed tables: {table_names}\n"
        f"Entity candidates: {entity_names}\n"
        f"Measure candidates: {measure_names}\n"
        f"Time candidates: {time_names}\n"
        f"Relationships: {relationships}"
    )


def _allowed_table_set(metadata: Dict[str, Any] | None) -> set[str]:
    if not metadata:
        return set()
    return {str(t.get("table_name", "")).strip() for t in metadata.get("tables", []) if t.get("table_name")}


def _allowed_columns_map(metadata: Dict[str, Any] | None) -> Dict[str, set[str]]:
    if not metadata:
        return {}
    out: Dict[str, set[str]] = {}
    for t in metadata.get("tables", []):
        table_name = str(t.get("table_name", "")).strip()
        if not table_name:
            continue
        cols = {
            str(c.get("column_name", "")).strip()
            for c in t.get("columns", [])
            if c.get("column_name")
        }
        out[table_name] = cols
    return out


def _extract_tables_from_sql(sql: str) -> set[str]:
    pattern = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_\.]*)", flags=re.IGNORECASE)
    tables = set()
    for match in pattern.findall(sql):
        token = match.strip().strip('"')
        token = token.split(".")[-1]
        tables.add(token)
    return tables


def _assert_allowlisted_tables(sql: str, metadata: Dict[str, Any] | None) -> None:
    allowed = _allowed_table_set(metadata)
    if not allowed:
        return
    used = _extract_tables_from_sql(sql)
    disallowed = sorted([table for table in used if table not in allowed])
    if disallowed:
        raise RuntimeError(f"Generated SQL uses non-allowlisted table(s): {disallowed}")


def _extract_table_aliases(sql: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    pattern = re.compile(
        r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_\.]*)\s*(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*)?",
        flags=re.IGNORECASE,
    )
    for table_token, alias_token in pattern.findall(sql):
        table = table_token.strip().strip('"').split(".")[-1]
        if not table:
            continue
        aliases[table] = table
        if alias_token:
            alias = alias_token.strip().strip('"')
            aliases[alias] = table
    return aliases


def _extract_dotted_columns(sql: str) -> list[tuple[str, str]]:
    # Matches alias.column or table.column references.
    pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\b")
    return [(left, right) for left, right in pattern.findall(sql)]


def _assert_allowlisted_columns(sql: str, metadata: Dict[str, Any] | None) -> None:
    allowed_cols = _allowed_columns_map(metadata)
    if not allowed_cols:
        return
    aliases = _extract_table_aliases(sql)
    disallowed: list[str] = []
    for left, col in _extract_dotted_columns(sql):
        table = aliases.get(left, left)
        if table not in allowed_cols:
            disallowed.append(f"{left}.{col} (unknown table)")
            continue
        if col not in allowed_cols[table]:
            disallowed.append(f"{left}.{col} (column not in allowlist for {table})")
    if disallowed:
        raise RuntimeError(f"Generated SQL uses non-allowlisted column reference(s): {disallowed}")


def _plan_context(plan: Plan) -> str:
    return json.dumps(
        {
            "task_type": plan.task_type,
            "intent": plan.intent,
            "entity_scope": plan.entity_scope,
            "entity_dimension": plan.entity_dimension,
            "n": plan.n,
            "metric": plan.metric,
            "time_grain": plan.time_grain,
            "compare_against": plan.compare_against,
            "requires_mining": plan.requires_mining,
        }
    )


def _call_hf_sql(prompt: str) -> Dict[str, Any]:
    load_environments()
    model = os.getenv("SQL_MODEL") or None

    try:
        text = hf_generate(prompt, model_override=model, temperature=0.01)
    except Exception as exc:
        raise RuntimeError(f"HF SQL generator request failed: {exc}") from exc

    return _extract_json_blob(text)


def generate_sql_from_plan(
    question: str,
    plan: Plan,
    dataset_metadata: Dict[str, Any] | None,
    previous_sql: Optional[str] = None,
    error_message: Optional[str] = None,
    trace_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> str:
    mode = "repair" if previous_sql or error_message else "initial"
    resolved_prompt_version = prompt_version or os.getenv("SQL_PROMPT_VERSION", "v1")
    prompt = (
        "You are a schema-aware SQL generator.\n"
        f"Prompt version: {resolved_prompt_version}\n"
        f"Trace id: {trace_id or 'none'}\n"
        "Return JSON only: {\"sql\":\"...\"}.\n"
        "Rules:\n"
        "- SQL must be SELECT/CTE only.\n"
        "- Single statement only.\n"
        "- Use only allowlisted tables from metadata context.\n"
        "- Add deterministic ordering when top_n is requested.\n"
        f"Mode: {mode}\n"
        f"Question: {question}\n"
        f"Structured plan: {_plan_context(plan)}\n"
        f"Dataset metadata context:\n{_metadata_context(dataset_metadata)}\n"
    )
    if previous_sql:
        prompt += f"Previous SQL:\n{previous_sql}\n"
    if error_message:
        prompt += f"Database/runtime error:\n{error_message}\n"

    parsed = _call_hf_sql(prompt)
    sql = str(parsed.get("sql", "")).strip()
    if not sql:
        raise RuntimeError("SQL generator response missing `sql`")

    safe_sql = validate_sql(sql)
    _assert_allowlisted_tables(safe_sql, dataset_metadata)
    _assert_allowlisted_columns(safe_sql, dataset_metadata)
    return safe_sql


def classify_sql_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "does not exist" in text and "column" in text:
        return "missing_column"
    if "does not exist" in text and "table" in text:
        return "missing_table"
    if "ambiguous" in text:
        return "ambiguous_reference"
    if "syntax error" in text:
        return "syntax_error"
    if "operator does not exist" in text or "type" in text:
        return "type_mismatch"
    if "timeout" in text:
        return "timeout"
    return "execution_error"
