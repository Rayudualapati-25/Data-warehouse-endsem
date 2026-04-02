import json
import os
import re
from typing import Any, Dict, List

from utils.env_loader import load_environments
from utils.hf_client import hf_generate


def _extract_json_blob(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    inline = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if inline:
        return json.loads(inline.group(0))

    return json.loads(text)


def _build_evidence_map(analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    evidence: Dict[str, Dict[str, Any]] = {}
    rows = analysis.get("rows", [])
    intent = analysis.get("intent")

    if rows and isinstance(rows[0], dict) and "snapshot_type" in rows[0]:
        data = rows[0].get("data", {})
        if intent == "trend_analysis":
            trend = data.get("trend", {})
            evidence["trend_direction"] = {"source_path": "rows[0].data.trend.direction", "source_value": trend.get("direction")}
            evidence["trend_slope_per_month"] = {
                "source_path": "rows[0].data.trend.slope_per_month",
                "source_value": trend.get("slope_per_month"),
            }
            evidence["trend_r2"] = {"source_path": "rows[0].data.trend.r2", "source_value": trend.get("r2")}
        elif intent == "customer_segmentation":
            clustering = data.get("clustering", {})
            evidence["cluster_count"] = {"source_path": "rows[0].data.clustering.k", "source_value": clustering.get("k")}
            evidence["silhouette_score"] = {
                "source_path": "rows[0].data.clustering.silhouette_score",
                "source_value": clustering.get("silhouette_score"),
            }
            clusters = clustering.get("clusters", [])
            if clusters:
                largest = max(clusters, key=lambda c: c.get("size", 0))
                evidence["largest_segment_label"] = {
                    "source_path": "rows[0].data.clustering.clusters[max_size].label",
                    "source_value": largest.get("label"),
                }
                evidence["largest_segment_size"] = {
                    "source_path": "rows[0].data.clustering.clusters[max_size].size",
                    "source_value": largest.get("size"),
                }
    elif rows:
        first = rows[0]
        for key, value in first.items():
            evidence_key = f"first_row_{key}"
            evidence[evidence_key] = {"source_path": f"rows[0].{key}", "source_value": value}
        evidence["row_count"] = {"source_path": "rows.length", "source_value": len(rows)}

    return evidence


def _call_hf_for_insights(
    analysis: Dict[str, Any],
    evidence_map: Dict[str, Dict[str, Any]],
    trace_id: str | None = None,
    prompt_version: str | None = None,
) -> Dict[str, Any]:
    load_environments()
    model = os.getenv("INSIGHT_MODEL") or None

    resolved_prompt_version = prompt_version or os.getenv("INSIGHT_PROMPT_VERSION", "v1")

    prompt = (
        "You generate business insights from evidence. Never invent numbers.\n"
        f"Prompt version: {resolved_prompt_version}\n"
        f"Trace id: {trace_id or 'none'}\n"
        "Return JSON only with keys: key_findings, risk_flags, recommended_actions, confidence, assumptions.\n"
        "key_findings items must have: finding, evidence_key, unit.\n"
        "Use only evidence_key values provided.\n"
        "confidence must be number between 0 and 1.\n"
        f"Intent: {analysis.get('intent')}\n"
        f"Question: {analysis.get('question')}\n"
        f"Evidence keys: {json.dumps({k: v['source_value'] for k, v in evidence_map.items()})}\n"
    )

    try:
        text = hf_generate(prompt, model_override=model, temperature=0.1)
    except Exception as exc:
        raise RuntimeError(f"HF insight request failed: {exc}") from exc

    return _extract_json_blob(text)


def generate_llm_sections(
    analysis: Dict[str, Any],
    trace_id: str | None = None,
    prompt_version: str | None = None,
) -> Dict[str, Any]:
    evidence_map = _build_evidence_map(analysis)
    if not evidence_map:
        raise RuntimeError("No evidence available for LLM insights")

    generated = _call_hf_for_insights(
        analysis,
        evidence_map,
        trace_id=trace_id,
        prompt_version=prompt_version,
    )
    key_findings = generated.get("key_findings")
    risk_flags = generated.get("risk_flags")
    recommended_actions = generated.get("recommended_actions")
    confidence = generated.get("confidence")
    assumptions = generated.get("assumptions")

    if not isinstance(key_findings, list):
        raise RuntimeError("key_findings must be a list")
    if not isinstance(risk_flags, list):
        raise RuntimeError("risk_flags must be a list")
    if not isinstance(recommended_actions, list):
        raise RuntimeError("recommended_actions must be a list")
    if not isinstance(assumptions, list):
        raise RuntimeError("assumptions must be a list")
    if not isinstance(confidence, (int, float)):
        raise RuntimeError("confidence must be numeric")

    findings_out: List[Dict[str, Any]] = []
    trace_out: List[Dict[str, Any]] = []
    for item in key_findings:
        if not isinstance(item, dict):
            raise RuntimeError("Each key_findings item must be an object")
        finding = item.get("finding")
        evidence_key = item.get("evidence_key")
        unit = item.get("unit")
        if not isinstance(finding, str) or not isinstance(evidence_key, str):
            raise RuntimeError("Each finding must include string finding and evidence_key")
        if evidence_key not in evidence_map:
            raise RuntimeError(f"Invalid evidence_key in finding: {evidence_key}")
        source = evidence_map[evidence_key]
        findings_out.append({"finding": finding, "value": source["source_value"], "unit": unit})
        trace_out.append(
            {
                "claim": finding,
                "source_path": source["source_path"],
                "source_value": source["source_value"],
            }
        )

    return {
        "key_findings": findings_out,
        "risk_flags": [str(x) for x in risk_flags],
        "recommended_actions": [str(x) for x in recommended_actions],
        "traceability": trace_out,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "assumptions": [str(x) for x in assumptions],
    }
