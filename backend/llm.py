"""
LLM integration for "Ask Your Data" and rich AI insights.
Supports any OpenAI-compatible API (OpenAI, Grok, Azure, Together, local vLLM, Ollama via OpenAI shim, etc.)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from analyzer import DataAnalyzer


SYSTEM_PROMPT = """You are an expert data analyst assistant. You help users understand their CSV datasets.

You will receive:
1. A structured summary of the dataset (shape, columns, dtypes, missing values, basic stats, correlations, outliers).
2. The user's question.

Rules:
- Answer ONLY based on the provided data summary. Do not invent numbers.
- Be concise, clear, and use markdown formatting.
- If the question cannot be answered from the summary, say so and suggest what extra analysis would help.
- When relevant, recommend charts or next analysis steps.
- Never execute code; only reason over the provided statistics.
"""


def build_data_context(analyzer: DataAnalyzer) -> str:
    """Create a rich text context that the LLM can reason over."""
    overview = analyzer.overview()
    describe = analyzer.describe()
    insights = analyzer.rule_based_insights()

    lines = [
        f"Filename: {overview['filename']}",
        f"Shape: {overview['rows']:,} rows × {overview['columns']} columns",
        f"Memory: {overview['memory_mb']} MB",
        f"Numeric columns: {', '.join(overview['numeric_columns']) or 'None'}",
        f"Categorical columns: {', '.join(overview['categorical_columns']) or 'None'}",
        "",
        "=== Column Details ===",
    ]
    for col in overview["column_info"]:
        lines.append(
            f"- {col['name']}: dtype={col['dtype']}, nulls={col['nulls']} ({col['null_pct']}%), unique={col['unique']}"
        )

    if "numeric" in describe:
        lines.append("\n=== Numeric Summary (describe) ===")
        lines.append(json.dumps(describe["numeric"], indent=2))

    if "categorical" in describe:
        lines.append("\n=== Categorical Summary ===")
        lines.append(json.dumps(describe["categorical"], indent=2))

    # Top correlations
    try:
        corr = analyzer.correlation()
        lines.append("\n=== Top Correlations ===")
        for p in corr["pairs"][:10]:
            lines.append(f"- {p['feature_a']} ↔ {p['feature_b']}: {p['correlation']:.3f}")
    except Exception:
        pass

    # Outlier quick scan
    lines.append("\n=== Quick Outlier Scan (IQR) ===")
    for col in overview["numeric_columns"][:6]:
        try:
            o = analyzer.outliers_iqr(col)
            if o["outlier_count"] > 0:
                lines.append(
                    f"- {col}: {o['outlier_count']} outliers ({o['outlier_pct']}%) "
                    f"outside [{o['lower_bound']}, {o['upper_bound']}]"
                )
        except Exception:
            pass

    lines.append("\n=== Rule-based Insights ===")
    for ins in insights:
        lines.append(f"[{ins['type'].upper()}] {ins['title']}: {ins['text']}")

    return "\n".join(lines)


def ask_llm(
    analyzer: DataAnalyzer,
    question: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    Send the user question + data context to an OpenAI-compatible LLM.
    """
    if not api_key or not api_key.strip():
        return {
            "success": False,
            "answer": "Please provide a valid API key in the settings.",
        }

    client_kwargs = {"api_key": api_key.strip()}
    if base_url:
        client_kwargs["base_url"] = base_url.strip()

    try:
        client = OpenAI(**client_kwargs)
        context = build_data_context(analyzer)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"DATASET CONTEXT:\n{context}\n\nUSER QUESTION:\n{question}",
            },
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=600,
        )
        answer = response.choices[0].message.content or "No response generated."
        return {
            "success": True,
            "answer": answer,
            "model": model,
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                "completion_tokens": getattr(response.usage, "completion_tokens", None),
            },
        }
    except Exception as e:
        return {
            "success": False,
            "answer": f"LLM error: {str(e)}",
        }


def generate_llm_insights(
    analyzer: DataAnalyzer,
    api_key: str,
    base_url: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """Ask the LLM to produce a rich narrative insight report."""
    question = (
        "Write a clear, professional data analysis summary for a business audience. "
        "Cover: data quality, key distributions, notable outliers, important correlations, "
        "potential data issues, and 3-5 recommended next analysis steps. "
        "Use markdown with headings and bullet points. Keep it under 600 words."
    )
    return ask_llm(analyzer, question, api_key, base_url, model, temperature=0.3)
