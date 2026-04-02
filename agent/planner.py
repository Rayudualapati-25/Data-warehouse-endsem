import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from utils.env_loader import load_environments
from utils.hf_client import hf_generate


@dataclass
class Plan:
    question: str
    requires_mining: bool
    intent: str
    planner_source: str
    task_type: str = "sql_retrieval"
    entity_scope: str = "all"
    entity_dimension: Optional[str] = None
    n: Optional[int] = None
    metric: Optional[str] = None
    time_grain: Optional[str] = None
    compare_against: Optional[str] = None


_VALID_INTENTS = {
    "country_revenue",
    "top_customers",
    "top_products",
    "monthly_revenue",
    "trend_analysis",
    "customer_segmentation",
    "generic_sales_summary",
}

_VALID_TASK_TYPES = {
    "sql_retrieval",
    "trend_analysis",
    "segmentation",
}

_VALID_ENTITY_SCOPES = {
    "all",
    "top_n",
}

_VALID_TIME_GRAINS = {
    "day",
    "week",
    "month",
    "quarter",
    "year",
}

_VALID_COMPARE = {
    "none",
    "global",
    "previous_period",
}


def _extract_json_blob(text: str) -> Dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    inline = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if inline:
        return json.loads(inline.group(0))

    return json.loads(text)


def _metadata_context(metadata: dict | None) -> str:
    if not metadata:
        return "No dataset metadata provided."

    tables = metadata.get("tables", [])
    entities = metadata.get("entities", [])[:8]
    measures = metadata.get("measures", [])[:8]
    time_columns = metadata.get("time_columns", [])[:8]
    relationships = metadata.get("relationships", [])[:12]

    table_names = [t.get("table_name") for t in tables[:30]]
    entity_labels = [f"{e.get('table')}.{e.get('column')}" for e in entities]
    measure_labels = [f"{m.get('table')}.{m.get('column')}" for m in measures]
    time_labels = [f"{t.get('table')}.{t.get('column')}" for t in time_columns]
    return (
        f"Tables: {table_names}\n"
        f"Entity candidates: {entity_labels}\n"
        f"Measure candidates: {measure_labels}\n"
        f"Time candidates: {time_labels}\n"
        f"Relationships sample: {relationships}"
    )


def _infer_top_n(question: str) -> Optional[int]:
    m = re.search(r"\btop\s+(\d+)\b", question.lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _normalize_plan(parsed: Dict[str, Any], question: str) -> Plan:
    intent = str(parsed.get("intent", "")).strip()
    if intent not in _VALID_INTENTS:
        raise RuntimeError(f"LLM returned invalid intent: {intent}")

    requires_mining = bool(parsed.get("requires_mining", False))

    task_type = str(parsed.get("task_type", "")).strip() or "sql_retrieval"
    if task_type not in _VALID_TASK_TYPES:
        if intent == "trend_analysis":
            task_type = "trend_analysis"
        elif intent == "customer_segmentation":
            task_type = "segmentation"
        else:
            task_type = "sql_retrieval"

    entity_scope = str(parsed.get("entity_scope", "")).strip() or "all"
    if entity_scope not in _VALID_ENTITY_SCOPES:
        entity_scope = "top_n" if _infer_top_n(question) else "all"

    n_value = parsed.get("n")
    n: Optional[int] = None
    if n_value is not None:
        try:
            n = int(n_value)
        except (TypeError, ValueError):
            n = None
    if entity_scope == "top_n" and (n is None or n <= 0):
        n = _infer_top_n(question) or 5

    metric = parsed.get("metric")
    metric = str(metric).strip() if metric is not None else None
    if metric == "":
        metric = None

    entity_dimension = parsed.get("entity_dimension")
    entity_dimension = str(entity_dimension).strip() if entity_dimension is not None else None
    if entity_dimension == "":
        entity_dimension = None

    time_grain = parsed.get("time_grain")
    time_grain = str(time_grain).strip().lower() if time_grain is not None else None
    if time_grain not in _VALID_TIME_GRAINS:
        time_grain = "month" if task_type == "trend_analysis" else None

    compare_against = parsed.get("compare_against")
    compare_against = str(compare_against).strip().lower() if compare_against is not None else None
    if compare_against not in _VALID_COMPARE:
        compare_against = "global" if task_type == "trend_analysis" else "none"

    return Plan(
        question=question,
        requires_mining=requires_mining,
        intent=intent,
        planner_source="huggingface",
        task_type=task_type,
        entity_scope=entity_scope,
        entity_dimension=entity_dimension,
        n=n,
        metric=metric,
        time_grain=time_grain,
        compare_against=compare_against,
    )


def build_plan(
    question: str,
    dataset_metadata: dict | None = None,
    trace_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> Plan:
    load_environments()
    planner_enabled = os.getenv("HF_PLANNER_ENABLED", "1")
    if planner_enabled.strip().lower() in {"0", "false", "no"}:
        raise RuntimeError("HF planner is disabled via HF_PLANNER_ENABLED")

    resolved_prompt_version = prompt_version or os.getenv("PLANNER_PROMPT_VERSION", "v1")

    prompt = (
        "You are a planner for a schema-aware SQL analytics system.\n"
        f"Prompt version: {resolved_prompt_version}\n"
        f"Trace id: {trace_id or 'none'}\n"
        "Return JSON only with keys:\n"
        "intent, requires_mining, task_type, entity_scope, entity_dimension, n, metric, time_grain, compare_against.\n"
        "Allowed intent values: country_revenue, top_customers, top_products, monthly_revenue, trend_analysis, customer_segmentation, generic_sales_summary.\n"
        "Allowed task_type values: sql_retrieval, trend_analysis, segmentation.\n"
        "Allowed entity_scope values: all, top_n.\n"
        "Allowed time_grain values: day, week, month, quarter, year.\n"
        "Allowed compare_against values: none, global, previous_period.\n"
        "Use dataset metadata context and avoid unsupported domain assumptions.\n"
        f"Question: {question}\n"
        f"Dataset metadata context:\n{_metadata_context(dataset_metadata)}"
    )

    planner_model = os.getenv("PLANNER_MODEL") or None

    try:
        text = hf_generate(prompt, model_override=planner_model, temperature=0.01)
    except Exception as exc:
        raise RuntimeError(f"HF planner request failed: {exc}") from exc

    parsed = _extract_json_blob(text)
    return _normalize_plan(parsed, question=question)
